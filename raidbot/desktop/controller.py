from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, Signal, Slot

from raidbot.desktop.storage import DesktopStorage
from raidbot.desktop.worker import DesktopBotWorker


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


class DesktopController(QObject):
    botStateChanged = Signal(str)
    connectionStateChanged = Signal(str)
    statsChanged = Signal(object)
    activityAdded = Signal(object)
    errorRaised = Signal(str)
    _workerEventReceived = Signal(object)
    _submissionFailed = Signal(str)

    def __init__(
        self,
        *,
        storage: DesktopStorage,
        config=None,
        worker_factory: Callable[..., DesktopBotWorker] = DesktopBotWorker,
        runner_factory: Callable[[], Any] = AsyncWorkerRunner,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.storage = storage
        self.config = config if config is not None else self._load_config()
        self.worker_factory = worker_factory
        self.runner_factory = runner_factory
        self._worker: DesktopBotWorker | Any | None = None
        self._runner: AsyncWorkerRunner | Any | None = None
        self._workerEventReceived.connect(self._handle_worker_event)
        self._submissionFailed.connect(self.errorRaised.emit)

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

    def _load_config(self):
        if hasattr(self.storage, "is_first_run") and self.storage.is_first_run():
            return None
        if hasattr(self.storage, "load_config"):
            return self.storage.load_config()
        return None

    def _receive_worker_event(self, event: dict[str, Any]) -> None:
        self._workerEventReceived.emit(event)

    def _submit_to_runner(self, job: Callable[[], Any]) -> None:
        future = self._runner.submit(job)
        if future is None or not hasattr(future, "add_done_callback"):
            return
        future.add_done_callback(self._handle_submission_future)

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
