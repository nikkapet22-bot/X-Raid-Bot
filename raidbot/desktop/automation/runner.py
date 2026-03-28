from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

from .input import validate_click_target
from .matching import TemplateMatcher
from .models import AutomationSequence, AutomationStep, MatchResult
from .templates import load_template_image
from .windowing import WindowInfo, WindowManager, choose_window_for_rule


@dataclass(eq=True)
class RunResult:
    status: str
    failure_reason: str | None = None
    window_handle: int | None = None
    step_index: int | None = None
    match: MatchResult | None = None


class SequenceRunner:
    def __init__(
        self,
        *,
        window_manager: WindowManager,
        capture: Any,
        matcher: TemplateMatcher,
        input_driver: Any,
        template_loader: Callable[[Any], Any] = load_template_image,
        now: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        emit_event: Callable[[dict[str, Any]], None] | None = None,
        scan_interval_seconds: float = 0.05,
        click_confirmation_seconds: float = 2.0,
    ) -> None:
        self.window_manager = window_manager
        self.capture = capture
        self.matcher = matcher
        self.input_driver = input_driver
        self.template_loader = template_loader
        self.now = now
        self.sleep = sleep
        self.emit_event = emit_event or (lambda _event: None)
        self.scan_interval_seconds = scan_interval_seconds
        self.click_confirmation_seconds = click_confirmation_seconds
        self._stop_requested = False

    def request_stop(self) -> None:
        self._stop_requested = True

    def run_sequence(
        self,
        sequence: AutomationSequence,
        *,
        selected_window: WindowInfo | None,
    ) -> RunResult:
        self._stop_requested = False
        window = self._resolve_window(sequence, selected_window)
        if isinstance(window, RunResult):
            return window
        self.emit_event({"type": "run_started", "sequence_id": sequence.id})
        self.emit_event({"type": "target_window_acquired", "handle": window.handle})

        for step_index, step in enumerate(sequence.steps):
            step_result = self._run_step(window, step, step_index)
            if step_result is not None:
                if step_result.status == "failed":
                    self.emit_event(
                        {
                            "type": "step_failed",
                            "step_index": step_index,
                            "reason": step_result.failure_reason,
                        }
                    )
                elif step_result.status == "stopped":
                    self.emit_event({"type": "run_stopped"})
                return step_result

        result = RunResult(status="completed", window_handle=window.handle)
        self.emit_event({"type": "run_completed", "window_handle": window.handle})
        return result

    def dry_run_step(
        self,
        sequence: AutomationSequence,
        step_index: int,
        *,
        selected_window: WindowInfo | None,
    ) -> RunResult:
        window = self._resolve_window(sequence, selected_window)
        if isinstance(window, RunResult):
            return window
        window = self._refresh_active_window(window, step_index)
        if isinstance(window, RunResult):
            return window
        step = sequence.steps[step_index]
        template = self.template_loader(step.template_path)
        frame = self.capture.capture(window.bounds)
        match = self.matcher.find_best_match(frame, template, threshold=step.match_threshold)
        if match is None:
            return RunResult(
                status="failed",
                failure_reason="match_not_found",
                window_handle=window.handle,
                step_index=step_index,
            )
        self.emit_event(
            {
                "type": "dry_run_match_found",
                "step_index": step_index,
                "score": match.score,
                "window_handle": window.handle,
            }
        )
        return RunResult(
            status="dry_run_match_found",
            window_handle=window.handle,
            step_index=step_index,
            match=match,
        )

    def _resolve_window(
        self,
        sequence: AutomationSequence,
        selected_window: WindowInfo | None,
    ) -> WindowInfo | RunResult:
        candidate = selected_window
        if candidate is None:
            if not sequence.target_window_rule:
                return RunResult(status="failed", failure_reason="target_window_not_found")
            candidate = choose_window_for_rule(
                self.window_manager.list_chrome_windows(),
                sequence.target_window_rule,
            )
            if candidate is None:
                return RunResult(status="failed", failure_reason="target_window_not_found")
        outcome = self.window_manager.ensure_interactable_window(candidate)
        if not outcome.success or outcome.window is None:
            return RunResult(status="failed", failure_reason=outcome.reason or "window_not_focusable")
        return outcome.window

    def _refresh_active_window(
        self,
        window: WindowInfo,
        step_index: int,
    ) -> WindowInfo | RunResult:
        current_window = self._find_window_by_handle(window.handle)
        if current_window is None:
            return RunResult(
                status="failed",
                failure_reason="target_window_not_found",
                window_handle=window.handle,
                step_index=step_index,
            )
        outcome = self.window_manager.ensure_interactable_window(current_window)
        if not outcome.success or outcome.window is None:
            return RunResult(
                status="failed",
                failure_reason=outcome.reason or "window_not_focusable",
                window_handle=current_window.handle,
                step_index=step_index,
            )
        return outcome.window

    def _find_window_by_handle(self, handle: int) -> WindowInfo | None:
        for candidate in self.window_manager.list_chrome_windows():
            if candidate.handle == handle:
                return candidate
        return None

    def _run_step(
        self,
        window: WindowInfo,
        step: AutomationStep,
        step_index: int,
    ) -> RunResult | None:
        template = self.template_loader(step.template_path)
        click_attempts = 0

        for scroll_attempt in range(step.max_scroll_attempts + 1):
            self.emit_event({"type": "step_search_started", "step_index": step_index})
            deadline = self.now() + step.max_search_seconds
            while True:
                if self._stop_requested:
                    return RunResult(
                        status="stopped",
                        failure_reason="stopped",
                        window_handle=window.handle,
                        step_index=step_index,
                    )
                window = self._refresh_active_window(window, step_index)
                if isinstance(window, RunResult):
                    return window
                frame = self.capture.capture(window.bounds)
                match = self.matcher.find_best_match(frame, template, threshold=step.match_threshold)
                if match is not None:
                    self.emit_event(
                        {
                            "type": "step_found",
                            "step_index": step_index,
                            "score": match.score,
                            "center": (match.center_x, match.center_y),
                        }
                    )
                    while click_attempts < step.max_click_attempts:
                        window = self._refresh_active_window(window, step_index)
                        if isinstance(window, RunResult):
                            return window
                        left, top, _right, _bottom = window.bounds
                        point = (
                            left + match.center_x + step.click_offset_x,
                            top + match.center_y + step.click_offset_y,
                        )
                        if not validate_click_target(window.bounds, point):
                            return RunResult(
                                status="failed",
                                failure_reason="invalid_click_target",
                                window_handle=window.handle,
                                step_index=step_index,
                            )
                        self.input_driver.move_click(point, delay_seconds=0.5)
                        click_attempts += 1
                        self.emit_event(
                            {
                                "type": "step_clicked",
                                "step_index": step_index,
                                "point": point,
                            }
                        )
                        confirmation = self._confirm_ui_changed_after_click(
                            window,
                            step,
                            step_index,
                            template,
                            match,
                        )
                        if isinstance(confirmation, RunResult):
                            if confirmation.status == "completed":
                                self.emit_event(
                                    {
                                        "type": "step_succeeded",
                                        "step_index": step_index,
                                        "window_handle": window.handle,
                                    }
                                )
                                return None
                            return confirmation
                        if self._step_succeeded(match, confirmation):
                            self.emit_event(
                                {
                                    "type": "step_succeeded",
                                    "step_index": step_index,
                                    "window_handle": window.handle,
                                }
                            )
                            return None
                        if click_attempts >= step.max_click_attempts:
                            return RunResult(
                                status="failed",
                                failure_reason="ui_did_not_change",
                                window_handle=window.handle,
                                step_index=step_index,
                            )
                        match = confirmation
                    break
                if self.now() >= deadline:
                    break
                self.sleep(self.scan_interval_seconds)

            if scroll_attempt < step.max_scroll_attempts:
                self.input_driver.scroll(step.scroll_amount)
                self.emit_event(
                    {
                        "type": "step_scrolled",
                        "step_index": step_index,
                        "amount": step.scroll_amount,
                    }
                )

        return RunResult(
            status="failed",
            failure_reason="match_not_found",
            window_handle=window.handle,
            step_index=step_index,
        )

    def _step_succeeded(self, previous_match: MatchResult, next_match: MatchResult | None) -> bool:
        if next_match is None:
            return True
        return self._has_material_shift(previous_match, next_match)

    def _confirm_ui_changed_after_click(
        self,
        window: WindowInfo,
        step: AutomationStep,
        step_index: int,
        template: Any,
        clicked_match: MatchResult,
    ) -> RunResult | MatchResult | None:
        deadline = self.now() + self.click_confirmation_seconds
        settle_seconds = min(step.post_click_settle_ms / 1000, max(0.0, deadline - self.now()))
        if settle_seconds > 0:
            self.sleep(settle_seconds)
        while True:
            if self._stop_requested:
                return RunResult(
                    status="stopped",
                    failure_reason="stopped",
                    window_handle=window.handle,
                    step_index=step_index,
                )
            window = self._refresh_active_window(window, step_index)
            if isinstance(window, RunResult):
                return window
            frame = self.capture.capture(window.bounds)
            next_match = self.matcher.find_best_match(
                frame,
                template,
                threshold=step.match_threshold,
            )
            if self._step_succeeded(clicked_match, next_match):
                return RunResult(
                    status="completed",
                    window_handle=window.handle,
                    step_index=step_index,
                )
            if self.now() >= deadline:
                return next_match
            sleep_seconds = min(self.scan_interval_seconds, max(0.0, deadline - self.now()))
            if sleep_seconds <= 0:
                return next_match
            self.sleep(sleep_seconds)

    def _has_material_shift(self, previous_match: MatchResult, next_match: MatchResult) -> bool:
        min_dimension = min(previous_match.width, previous_match.height)
        threshold = max(10.0, 0.25 * float(min_dimension))
        delta_x = next_match.center_x - previous_match.center_x
        delta_y = next_match.center_y - previous_match.center_y
        distance = (delta_x**2 + delta_y**2) ** 0.5
        return distance > threshold
