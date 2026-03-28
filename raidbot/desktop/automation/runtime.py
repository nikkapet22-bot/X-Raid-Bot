from __future__ import annotations

from collections.abc import Callable
from typing import Any

_MISSING_SELECTED_WINDOW = object()


class AutomationRuntime:
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
        runner = self._build_runner()
        self._active_runner = runner
        return runner.run_sequence(sequence, selected_window=selected_window)

    def dry_run_step(self, sequence, step_index: int, selected_window_handle: int | None):
        selected_window = self._selected_window(selected_window_handle)
        if selected_window is _MISSING_SELECTED_WINDOW:
            return self._run_result(status="failed", failure_reason="target_window_not_found")
        runner = self._build_runner()
        self._active_runner = runner
        return runner.dry_run_step(
            sequence,
            step_index,
            selected_window=selected_window,
        )

    def request_stop(self) -> None:
        if self._active_runner is not None and hasattr(self._active_runner, "request_stop"):
            self._active_runner.request_stop()

    def _build_runner(self):
        return self.sequence_runner_factory(
            window_manager=self.window_manager,
            capture=self.capture_factory(),
            matcher=self.matcher_factory(),
            input_driver=self.input_driver_factory(),
            emit_event=self.emit_event,
        )

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
