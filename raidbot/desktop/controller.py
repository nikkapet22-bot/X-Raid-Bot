from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Signal, Slot

from raidbot.desktop.storage import DesktopStorage
from raidbot.desktop.worker import DesktopBotWorker

_MISSING_SELECTED_WINDOW = object()


class AsyncWorkerRunner:
    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._started = threading.Event()

    def start(self, job: Callable[[], Any] | Any) -> None:
        if self.is_running():
            return

        self._started.clear()

        def target() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._loop = loop
            self._started.set()
            try:
                loop.run_until_complete(_resolve_job(job))
            finally:
                loop.close()
                self._loop = None

        self._thread = threading.Thread(target=target, daemon=True)
        self._thread.start()
        self._started.wait()

    def submit(self, job: Callable[[], Any] | Any):
        if self._loop is None:
            return
        return asyncio.run_coroutine_threadsafe(_resolve_job(job), self._loop)

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def wait_until_stopped(self, timeout: float | None = None) -> bool:
        thread = self._thread
        if thread is None:
            return True
        thread.join(timeout)
        if thread.is_alive():
            return False
        self._thread = None
        return True


async def _resolve_job(job: Callable[[], Any] | Any) -> Any:
    result = job() if callable(job) else job
    if asyncio.iscoroutine(result):
        return await result
    return result


class _AutomationRuntime:
    def __init__(
        self,
        *,
        emit_event: Callable[[dict[str, Any]], None],
        window_manager_factory=None,
        capture_factory=None,
        matcher_factory=None,
        input_driver_factory=None,
        sequence_runner_factory=None,
    ) -> None:
        from raidbot.desktop.automation.capture import WindowCapture
        from raidbot.desktop.automation.input import InputDriver
        from raidbot.desktop.automation.matching import TemplateMatcher
        from raidbot.desktop.automation.runner import SequenceRunner
        from raidbot.desktop.automation.windowing import WindowManager

        self.emit_event = emit_event
        self.window_manager = (window_manager_factory or WindowManager)()
        self.capture_factory = capture_factory or WindowCapture
        self.matcher_factory = matcher_factory or TemplateMatcher
        self.input_driver_factory = input_driver_factory or InputDriver
        self.sequence_runner_factory = sequence_runner_factory or SequenceRunner
        self._active_runner = None

    def list_target_windows(self) -> list[Any]:
        return self.window_manager.list_chrome_windows()

    def run_sequence(self, sequence, selected_window_handle: int | None):
        selected_window = self._selected_window(selected_window_handle)
        if selected_window is _MISSING_SELECTED_WINDOW:
            return self._run_result(status="failed", failure_reason="target_window_not_found")
        runner = self.sequence_runner_factory(
            window_manager=self.window_manager,
            capture=self.capture_factory(),
            matcher=self.matcher_factory(),
            input_driver=self.input_driver_factory(),
            emit_event=self.emit_event,
        )
        self._active_runner = runner
        return runner.run_sequence(sequence, selected_window=selected_window)

    def dry_run_step(self, sequence, step_index: int, selected_window_handle: int | None):
        selected_window = self._selected_window(selected_window_handle)
        if selected_window is _MISSING_SELECTED_WINDOW:
            return self._run_result(status="failed", failure_reason="target_window_not_found")
        runner = self.sequence_runner_factory(
            window_manager=self.window_manager,
            capture=self.capture_factory(),
            matcher=self.matcher_factory(),
            input_driver=self.input_driver_factory(),
            emit_event=self.emit_event,
        )
        self._active_runner = runner
        return runner.dry_run_step(
            sequence,
            step_index,
            selected_window=selected_window,
        )

    def request_stop(self) -> None:
        if self._active_runner is not None and hasattr(self._active_runner, "request_stop"):
            self._active_runner.request_stop()

    def _selected_window(self, selected_window_handle: int | None):
        if selected_window_handle is None:
            return None
        for window in self.list_target_windows():
            if getattr(window, "handle", None) == selected_window_handle:
                return window
        return _MISSING_SELECTED_WINDOW

    def _run_result(self, *, status: str, failure_reason: str | None = None):
        from raidbot.desktop.automation.runner import RunResult

        return RunResult(status=status, failure_reason=failure_reason)


class DesktopController(QObject):
    botStateChanged = Signal(str)
    connectionStateChanged = Signal(str)
    statsChanged = Signal(object)
    activityAdded = Signal(object)
    errorRaised = Signal(str)
    automationSequencesChanged = Signal(object)
    automationRunEvent = Signal(object)
    automationRunStateChanged = Signal(str)
    _workerEventReceived = Signal(object)
    _submissionFailed = Signal(str)
    _automationEventReceived = Signal(object)
    _automationResultReceived = Signal(object)

    def __init__(
        self,
        *,
        storage: DesktopStorage,
        config=None,
        worker_factory: Callable[..., DesktopBotWorker] = DesktopBotWorker,
        runner_factory: Callable[[], Any] = AsyncWorkerRunner,
        automation_runtime_probe: Callable[[], tuple[bool, str | None]] | None = None,
        automation_runtime_factory: Callable[[Callable[[dict[str, Any]], None]], Any] | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.storage = storage
        self.config = config if config is not None else self._load_config()
        self.worker_factory = worker_factory
        self.runner_factory = runner_factory
        self.automation_runtime_probe = automation_runtime_probe or self._probe_automation_runtime
        self.automation_runtime_factory = (
            automation_runtime_factory or self._default_automation_runtime_factory
        )
        self._worker: DesktopBotWorker | Any | None = None
        self._runner: AsyncWorkerRunner | Any | None = None
        self._automation_runtime: Any | None = None
        self._automation_runner: AsyncWorkerRunner | Any | None = None
        self._automation_sequences = self._load_automation_sequences()
        self._automation_run_state = "idle"
        self._workerEventReceived.connect(self._handle_worker_event)
        self._submissionFailed.connect(self.errorRaised.emit)
        self._automationEventReceived.connect(self._handle_automation_event)
        self._automationResultReceived.connect(self._handle_automation_result)

    def start_bot(self) -> None:
        if self.config is None:
            self.errorRaised.emit("No desktop configuration is available")
            return

        if self._runner is not None and self._runner.is_running():
            return

        self._worker = self.worker_factory(
            config=self.config,
            storage=self.storage,
            emit_event=self._receive_worker_event,
        )
        self._runner = self.runner_factory()
        self._runner.start(lambda: self._worker.run())

    def stop_bot(self) -> None:
        if self._worker is None or self._runner is None or not self._runner.is_running():
            return
        self._submit_to_runner(lambda: self._worker.stop())

    def stop_bot_and_wait(self) -> bool:
        if self._worker is None or self._runner is None or not self._runner.is_running():
            return True

        future = self._runner.submit(lambda: self._worker.stop())
        if future is None or not hasattr(future, "result"):
            return True

        try:
            future.result()
        except Exception as exc:
            self._submissionFailed.emit(str(exc))
            return False
        if hasattr(self._runner, "wait_until_stopped"):
            return bool(self._runner.wait_until_stopped())
        return not self._runner.is_running()

    def is_bot_active(self) -> bool:
        return self._runner is not None and self._runner.is_running()

    def apply_config(self, config) -> None:
        self.storage.save_config(config)
        self.config = config
        if self._worker is None or self._runner is None or not self._runner.is_running():
            return
        self._submit_to_runner(lambda: self._worker.apply_config(config))

    def list_automation_sequences(self) -> list[Any]:
        return list(self._automation_sequences)

    def save_automation_sequence(self, sequence: Any) -> None:
        updated = [item for item in self._automation_sequences if getattr(item, "id", None) != sequence.id]
        updated.append(sequence)
        self._automation_sequences = updated
        self._save_automation_sequences()
        self.automationSequencesChanged.emit(self.list_automation_sequences())

    def delete_automation_sequence(self, sequence_id: str) -> None:
        updated = [item for item in self._automation_sequences if getattr(item, "id", None) != sequence_id]
        self._automation_sequences = updated
        self._save_automation_sequences()
        self.automationSequencesChanged.emit(self.list_automation_sequences())

    def list_target_windows(self) -> list[Any]:
        runtime = self._load_automation_runtime(emit_error=False)
        if runtime is None:
            return []
        return runtime.list_target_windows()

    def start_automation_run(self, sequence_id: str, selected_window_handle: int | None) -> None:
        sequence = self._find_automation_sequence(sequence_id)
        if sequence is None:
            self.errorRaised.emit(f"Unknown automation sequence: {sequence_id}")
            return
        runtime = self._load_automation_runtime()
        if runtime is None:
            return
        if self._automation_runner is not None and self._automation_runner.is_running():
            return
        self._automation_runner = self.runner_factory()
        self._set_automation_run_state("running")
        self._automation_runner.start(
            lambda: self._run_automation_sequence(runtime, sequence, selected_window_handle)
        )

    def dry_run_automation_step(
        self,
        sequence_id: str,
        step_index: int,
        selected_window_handle: int | None,
    ) -> None:
        sequence = self._find_automation_sequence(sequence_id)
        if sequence is None:
            self.errorRaised.emit(f"Unknown automation sequence: {sequence_id}")
            return
        runtime = self._load_automation_runtime()
        if runtime is None:
            return
        if self._automation_runner is not None and self._automation_runner.is_running():
            return
        self._automation_runner = self.runner_factory()
        self._set_automation_run_state("running")
        self._automation_runner.start(
            lambda: self._run_automation_dry_run(
                runtime,
                sequence,
                step_index,
                selected_window_handle,
            )
        )

    def stop_automation_run(self) -> None:
        if (
            self._automation_runtime is None
            or self._automation_runner is None
            or not self._automation_runner.is_running()
        ):
            return
        self._submit_to_specific_runner(self._automation_runner, self._automation_runtime.request_stop)

    def _load_config(self):
        if hasattr(self.storage, "is_first_run") and self.storage.is_first_run():
            return None
        if hasattr(self.storage, "load_config"):
            return self.storage.load_config()
        return None

    def _receive_worker_event(self, event: dict[str, Any]) -> None:
        self._workerEventReceived.emit(event)

    def _submit_to_runner(self, job: Callable[[], Any]) -> None:
        future = self._submit_to_specific_runner(self._runner, job)

    def _submit_to_specific_runner(self, runner: Any, job: Callable[[], Any]):
        future = runner.submit(job)
        if future is None:
            return future
        if hasattr(future, "done") and future.done():
            self._handle_submission_future(future)
            return future
        if hasattr(future, "add_done_callback"):
            future.add_done_callback(self._handle_submission_future)
        return future

    def _handle_submission_future(self, future) -> None:
        try:
            future.result()
        except Exception as exc:
            self._submissionFailed.emit(str(exc))

    @Slot(object)
    def _handle_worker_event(self, event: dict[str, Any]) -> None:
        event_type = event.get("type")
        if event_type == "bot_state_changed":
            self.botStateChanged.emit(str(event.get("state", "")))
        elif event_type == "connection_state_changed":
            self.connectionStateChanged.emit(str(event.get("state", "")))
        elif event_type == "stats_changed":
            self.statsChanged.emit(event.get("state"))
        elif event_type == "activity_added":
            self.activityAdded.emit(event.get("entry"))
        elif event_type == "error":
            self.errorRaised.emit(str(event.get("message", "")))

    def _load_automation_sequences(self) -> list[Any]:
        storage = self._load_automation_storage()
        if storage is None:
            return []
        return storage.load_sequences()

    def _save_automation_sequences(self) -> None:
        storage = self._load_automation_storage()
        if storage is None:
            return
        storage.save_sequences(self._automation_sequences)

    def _load_automation_storage(self):
        try:
            from raidbot.desktop.automation.storage import AutomationStorage
        except Exception:
            return None
        base_dir = getattr(self.storage, "base_dir", Path("."))
        return AutomationStorage(base_dir)

    def _probe_automation_runtime(self) -> tuple[bool, str | None]:
        from raidbot.desktop.automation.platform import automation_runtime_available

        return automation_runtime_available()

    def _default_automation_runtime_factory(self, emit_event):
        return _AutomationRuntime(emit_event=emit_event)

    def _load_automation_runtime(self, *, emit_error: bool = True):
        if self._automation_runtime is not None:
            return self._automation_runtime
        available, reason = self.automation_runtime_probe()
        if not available:
            if emit_error and reason:
                self.errorRaised.emit(reason)
            return None
        self._automation_runtime = self.automation_runtime_factory(self._receive_automation_event)
        return self._automation_runtime

    def _find_automation_sequence(self, sequence_id: str):
        for sequence in self._automation_sequences:
            if getattr(sequence, "id", None) == sequence_id:
                return sequence
        return None

    def _receive_automation_event(self, event: dict[str, Any]) -> None:
        self._automationEventReceived.emit(event)

    def _run_automation_sequence(self, runtime, sequence, selected_window_handle: int | None) -> None:
        try:
            result = runtime.run_sequence(sequence, selected_window_handle)
        except Exception as exc:
            self._submissionFailed.emit(str(exc))
            from raidbot.desktop.automation.runner import RunResult

            result = RunResult(status="failed", failure_reason="runtime_error")
        self._automationResultReceived.emit(result)

    def _run_automation_dry_run(
        self,
        runtime,
        sequence,
        step_index: int,
        selected_window_handle: int | None,
    ) -> None:
        try:
            result = runtime.dry_run_step(sequence, step_index, selected_window_handle)
        except Exception as exc:
            self._submissionFailed.emit(str(exc))
            from raidbot.desktop.automation.runner import RunResult

            result = RunResult(status="failed", failure_reason="runtime_error")
        self._automationResultReceived.emit(result)

    def _set_automation_run_state(self, state: str) -> None:
        if self._automation_run_state == state:
            return
        self._automation_run_state = state
        self.automationRunStateChanged.emit(state)

    @Slot(object)
    def _handle_automation_event(self, event: dict[str, Any]) -> None:
        self.automationRunEvent.emit(event)

    @Slot(object)
    def _handle_automation_result(self, result) -> None:
        if result is not None:
            status = getattr(result, "status", None)
            failure_reason = getattr(result, "failure_reason", None)
            if status == "failed":
                if failure_reason in {"target_window_not_found", "window_not_focusable"}:
                    self._automationEventReceived.emit(
                        {"type": "target_window_lost", "reason": failure_reason}
                    )
                else:
                    self._automationEventReceived.emit(
                        {"type": "step_failed", "reason": failure_reason}
                    )
            elif status == "stopped":
                self._automationEventReceived.emit({"type": "run_stopped"})
            elif status == "dry_run_match_found":
                match = getattr(result, "match", None)
                self._automationEventReceived.emit(
                    {
                        "type": "dry_run_match_found",
                        "step_index": getattr(result, "step_index", None),
                        "window_handle": getattr(result, "window_handle", None),
                        "score": getattr(match, "score", None),
                    }
                )
        self._set_automation_run_state("idle")
