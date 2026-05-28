from __future__ import annotations

import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable

from .input import InputStopRequested, validate_click_target
from .matching import TemplateMatcher
from .models import AutomationSequence, AutomationStep, MatchResult
from .templates import load_template_image
from .windowing import WindowInfo, WindowManager, choose_window_for_rule

_SLOT_1_FINISH_SCROLL_ATTEMPTS = 4
_SLOT_1_FINISH_SEARCH_SECONDS = 1.0
_SLOT_1_REPLY_COMPOSER_SETTLE_SECONDS = 0.5
_SLOT_1_TEXT_TO_IMAGE_DELAY_SECONDS = 1.0
_SLOT_1_FINISH_POST_CLICK_DELAY_SECONDS = 2.0
_SLOT_1_REPLY_SUBMIT_RECHECK_SECONDS = 0.0
_SLOT_1_REPLY_SUBMIT_RETRY_DELAY_SECONDS = 2.0
_SLOT_1_RETRY_HOVER_RESET_DELAY_SECONDS = 0.1
_SLOT_1_RETRY_HOVER_RESET_OFFSET_PIXELS = 60
_SLOT_1_FINISH_AFTER_TEXT_SETTLE_SECONDS = 1.0
_SLOT_1_FINISH_AFTER_TEXT_SEARCH_SECONDS = 0.0
_SLOT_1_FINISH_AFTER_TEXT_SCROLL_SETTLE_SECONDS = 0.2
_SLOT_1_FINISH_AFTER_TEXT_ESCAPE_DELAY_SECONDS = 0.25
_SCROLL_SETTLE_SECONDS = 0.5
_MOVE_CLICK_DELAY_SECONDS = 0.25
_SLOT_1_FINISH_CLICK_DELAY_SECONDS = 0.5


@dataclass(eq=True)
class RunResult:
    status: str
    failure_reason: str | None = None
    window_handle: int | None = None
    step_index: int | None = None
    match: MatchResult | None = None
    step_phase: str | None = None


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
        click_confirmation_seconds: float = 1.5,
        require_interactable_window: bool = True,
        move_cursor_before_scroll: bool = False,
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
        self.require_interactable_window = require_interactable_window
        self.move_cursor_before_scroll = move_cursor_before_scroll
        self._stop_requested = False
        if hasattr(self.input_driver, "set_stop_check"):
            self.input_driver.set_stop_check(lambda: self._stop_requested)

    def request_stop(self) -> None:
        self._stop_requested = True

    def run_sequence(
        self,
        sequence: AutomationSequence,
        *,
        selected_window: WindowInfo | None,
        start_step_index: int = 0,
        start_step_phase: str | None = None,
    ) -> RunResult:
        self._stop_requested = False
        window = self._resolve_window(sequence, selected_window)
        if isinstance(window, RunResult):
            return window
        self.emit_event({"type": "run_started", "sequence_id": sequence.id})
        self.emit_event({"type": "target_window_acquired", "handle": window.handle})

        slot_1_recovery_pending = (
            start_step_index > 0
            and self._is_slot_1_preset_step(sequence.steps[start_step_index - 1])
        )
        for step_index, step in enumerate(
            sequence.steps[start_step_index:],
            start=start_step_index,
        ):
            allow_slot_1_recovery_scroll = (
                slot_1_recovery_pending and not self._is_slot_1_preset_step(step)
            )
            step_result = self._run_step(
                window,
                step,
                step_index,
                resume_phase=(start_step_phase if step_index == start_step_index else None),
                allow_slot_1_recovery_scroll=allow_slot_1_recovery_scroll,
            )
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
            if self._stop_requested:
                self.emit_event({"type": "run_stopped"})
                return RunResult(
                    status="stopped",
                    failure_reason="stopped",
                    window_handle=window.handle,
                    step_index=step_index + 1,
                )
            slot_1_recovery_pending = self._is_slot_1_preset_step(step)

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
        if not self.require_interactable_window:
            return candidate
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
        if not self.require_interactable_window:
            return current_window
        outcome = self.window_manager.ensure_interactable_window(current_window)
        if not outcome.success or outcome.window is None:
            return RunResult(
                status="failed",
                failure_reason=outcome.reason or "window_not_focusable",
                window_handle=current_window.handle,
                step_index=step_index,
            )
        return outcome.window

    def _refresh_window_bounds(
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
        return current_window

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
        *,
        resume_phase: str | None = None,
        allow_slot_1_recovery_scroll: bool = False,
    ) -> RunResult | None:
        template = self.template_loader(step.template_path)
        if allow_slot_1_recovery_scroll:
            location = self._find_match_for_template(
                window,
                step,
                step_index,
                template,
                allow_slot_1_recovery_scroll=True,
            )
        else:
            location = self._find_match_for_template(window, step, step_index, template)
        if isinstance(location, RunResult):
            return location
        window, frame, match = location
        if self._is_slot_1_preset_step(step):
            return self._run_slot_1_preset_step(
                window,
                step,
                step_index,
                frame,
                match,
                resume_phase=resume_phase,
            )
        click_attempts = 0
        pre_confirm_clicks = max(1, min(step.pre_confirm_clicks, step.max_click_attempts))
        while click_attempts < step.max_click_attempts:
            window = self._refresh_active_window(window, step_index)
            if isinstance(window, RunResult):
                return window
            point = self._resolve_click_point(window, step, step_index, match)
            if isinstance(point, RunResult):
                return point
            stopped_result = self._try_input_action(
                lambda: self.input_driver.move_click(
                    point, delay_seconds=_MOVE_CLICK_DELAY_SECONDS
                ),
                window,
                step_index,
            )
            if stopped_result is not None:
                return stopped_result
            click_attempts += 1
            self.emit_event(
                {
                    "type": "step_clicked",
                    "step_index": step_index,
                    "point": point,
                }
            )
            if click_attempts < pre_confirm_clicks:
                inter_click_delay_seconds = max(0.0, step.inter_click_delay_ms / 1000)
                if inter_click_delay_seconds > 0:
                    stopped_result = self._sleep_or_stop(
                        inter_click_delay_seconds,
                        window,
                        step_index,
                    )
                    if stopped_result is not None:
                        return stopped_result
                continue
            confirmation = self._confirm_ui_changed_after_click(
                window,
                step,
                step_index,
                template,
                match,
                frame,
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

        return RunResult(
            status="failed",
            failure_reason="ui_did_not_change",
            window_handle=window.handle,
            step_index=step_index,
        )

    def _find_match_for_template(
        self,
        window: WindowInfo,
        step: AutomationStep,
        step_index: int,
        template: Any,
        *,
        allow_slot_1_recovery_scroll: bool = False,
    ) -> RunResult | tuple[WindowInfo, Any, MatchResult]:
        recovery_scroll_pending = bool(allow_slot_1_recovery_scroll)
        for scroll_attempt in range(step.max_scroll_attempts + 1):
            current_view = self._search_current_view(window, step, step_index, template)
            if isinstance(current_view, RunResult):
                return current_view
            if current_view is not None:
                return current_view

            if recovery_scroll_pending:
                recovery_scroll_pending = False
                recovered_window = self._scroll_and_settle(
                    window,
                    step,
                    step_index,
                    amount=abs(step.scroll_amount) or 120,
                    event_type="slot1_post_reply_scroll_up_performed",
                )
                if isinstance(recovered_window, RunResult):
                    return recovered_window
                window = recovered_window
                current_view = self._search_current_view(
                    window,
                    step,
                    step_index,
                    template,
                )
                if isinstance(current_view, RunResult):
                    return current_view
                if current_view is not None:
                    return current_view

            if scroll_attempt < step.max_scroll_attempts:
                scrolled_window = self._scroll_and_settle(
                    window,
                    step,
                    step_index,
                    amount=step.scroll_amount,
                    event_type="step_scrolled",
                )
                if isinstance(scrolled_window, RunResult):
                    return scrolled_window
                window = scrolled_window

        return RunResult(
            status="failed",
            failure_reason="match_not_found",
            window_handle=window.handle,
            step_index=step_index,
        )

    def _search_current_view(
        self,
        window: WindowInfo,
        step: AutomationStep,
        step_index: int,
        template: Any,
    ) -> RunResult | tuple[WindowInfo, Any, MatchResult] | None:
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
            window = self._refresh_window_bounds(window, step_index)
            if isinstance(window, RunResult):
                return window
            frame = self.capture.capture(window.bounds)
            match = self.matcher.find_best_match(
                frame,
                template,
                threshold=step.match_threshold,
            )
            if match is not None:
                self.emit_event(
                    {
                        "type": "step_found",
                        "step_index": step_index,
                        "score": match.score,
                        "center": (match.center_x, match.center_y),
                    }
                )
                return window, frame, match
            if self.now() >= deadline:
                return None
            self.sleep(self.scan_interval_seconds)

    def _scroll_and_settle(
        self,
        window: WindowInfo,
        step: AutomationStep,
        step_index: int,
        *,
        amount: int,
        event_type: str,
    ) -> WindowInfo | RunResult:
        window = self._refresh_active_window(window, step_index)
        if isinstance(window, RunResult):
            return window
        if self.move_cursor_before_scroll:
            left, top, right, bottom = window.bounds
            stopped_result = self._try_input_action(
                lambda: self.input_driver.move_cursor(
                    ((left + right) // 2, (top + bottom) // 2)
                ),
                window,
                step_index,
            )
            if stopped_result is not None:
                return stopped_result
        stopped_result = self._try_input_action(
            lambda: self.input_driver.scroll(amount),
            window,
            step_index,
        )
        if stopped_result is not None:
            return stopped_result
        self.emit_event(
            {
                "type": event_type,
                "step_index": step_index,
                "amount": amount,
            }
        )
        stopped_result = self._sleep_or_stop(
            _SCROLL_SETTLE_SECONDS,
            window,
            step_index,
        )
        if stopped_result is not None:
            return stopped_result
        return window

    def _resolve_click_point(
        self,
        window: WindowInfo,
        step: AutomationStep,
        step_index: int,
        match: MatchResult,
    ) -> RunResult | tuple[int, int]:
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
        return point

    def _resolve_hover_reset_point(
        self,
        window: WindowInfo,
        match: MatchResult,
    ) -> tuple[int, int]:
        left, top, right, bottom = window.bounds
        button_left = left + match.top_left_x
        button_top = top + match.top_left_y
        button_right = button_left + max(1, match.width) - 1
        button_bottom = button_top + max(1, match.height) - 1
        target_y = max(top, min(bottom - 1, top + match.center_y))
        reset_offset = max(_SLOT_1_RETRY_HOVER_RESET_OFFSET_PIXELS, match.width)

        reset_left_x = max(left, button_left - reset_offset)
        if reset_left_x < button_left:
            return (reset_left_x, target_y)

        reset_right_x = min(right - 1, button_right + reset_offset)
        if reset_right_x > button_right:
            return (reset_right_x, target_y)

        reset_up_y = max(top, button_top - reset_offset)
        target_x = max(left, min(right - 1, left + match.center_x))
        if reset_up_y < button_top:
            return (target_x, reset_up_y)

        reset_down_y = min(bottom - 1, button_bottom + reset_offset)
        if reset_down_y > button_bottom:
            return (target_x, reset_down_y)

        return (target_x, target_y)

    def _is_slot_1_preset_step(self, step: AutomationStep) -> bool:
        return (
            step.name == "slot_1_r"
            and (
                step.preset_text is not None
                or step.preset_image_path is not None
                or step.finish_template_path is not None
            )
        )

    def _run_slot_1_preset_step(
        self,
        window: WindowInfo,
        step: AutomationStep,
        step_index: int,
        _frame: Any,
        match: MatchResult,
        *,
        resume_phase: str | None = None,
    ) -> RunResult | None:
        slot_1_resume_phase = resume_phase or ""
        skip_open_click = slot_1_resume_phase in {
            "slot1_after_open_click",
            "slot1_after_text",
            "slot1_after_image",
            "slot1_before_finish_search",
        }
        skip_text_paste = slot_1_resume_phase in {
            "slot1_after_text",
            "slot1_after_image",
            "slot1_before_finish_search",
        }
        skip_image_paste = slot_1_resume_phase in {
            "slot1_after_image",
            "slot1_before_finish_search",
        }
        window = self._refresh_active_window(window, step_index)
        if isinstance(window, RunResult):
            return window
        if not skip_open_click:
            point = self._resolve_click_point(window, step, step_index, match)
            if isinstance(point, RunResult):
                return point
            stopped_result = self._try_input_action(
                lambda: self.input_driver.move_click(
                    point, delay_seconds=_MOVE_CLICK_DELAY_SECONDS
                ),
                window,
                step_index,
            )
            if stopped_result is not None:
                return stopped_result
            self.emit_event(
                {
                    "type": "step_clicked",
                    "step_index": step_index,
                    "point": point,
                }
            )
        if self._stop_requested:
            return self._stopped_result(
                window,
                step_index,
                step_phase="slot1_after_open_click",
            )
        pasted_image = False
        if step.preset_text is not None and not skip_text_paste:
            stopped_result = self._sleep_or_stop(
                _SLOT_1_REPLY_COMPOSER_SETTLE_SECONDS,
                window,
                step_index,
                step_phase="slot1_after_open_click",
            )
            if stopped_result is not None:
                return stopped_result
            self._emit_slot_1_event(
                "slot1_text_paste_started",
                step_index,
                text_length=len(step.preset_text),
                window_handle=window.handle,
            )
            try:
                stopped_result = self._try_input_action(
                    lambda: self.input_driver.paste_text(step.preset_text),
                    window,
                    step_index,
                    step_phase="slot1_after_open_click",
                )
            except Exception as exc:
                self._emit_slot_1_event(
                    "slot1_text_paste_failed",
                    step_index,
                    error_type=type(exc).__name__,
                    error=str(exc),
                    window_handle=window.handle,
                )
                raise
            if stopped_result is not None:
                self._emit_slot_1_event(
                    "slot1_text_paste_stopped",
                    step_index,
                    reason=stopped_result.failure_reason,
                    window_handle=window.handle,
                )
                return stopped_result
            self._emit_slot_1_event(
                "slot1_text_paste_succeeded",
                step_index,
                text_length=len(step.preset_text),
                window_handle=window.handle,
            )
        if step.preset_text is not None and (skip_text_paste or self._stop_requested):
            if self._stop_requested:
                return self._stopped_result(
                    window,
                    step_index,
                    step_phase="slot1_after_text",
                )
        has_image_to_paste = (
            step.preset_image_path is not None
            and Path(step.preset_image_path).exists()
            and not skip_image_paste
        )
        prepared_finish_location: (
            RunResult | tuple[WindowInfo, Any, MatchResult] | None
        ) = None
        if (
            step.preset_text is not None
            and not skip_image_paste
            and not has_image_to_paste
        ):
            prepared_finish_location = self._prepare_slot_1_finish_after_text(
                window,
                step,
                step_index,
            )
            if isinstance(prepared_finish_location, RunResult):
                return prepared_finish_location
        if has_image_to_paste:
            stopped_result = self._sleep_or_stop(
                _SLOT_1_TEXT_TO_IMAGE_DELAY_SECONDS,
                window,
                step_index,
                step_phase="slot1_after_text",
            )
            if stopped_result is not None:
                return stopped_result
            self._emit_slot_1_event(
                "slot1_image_paste_started",
                step_index,
                image_path=str(step.preset_image_path),
                window_handle=window.handle,
            )
            try:
                stopped_result = self._try_input_action(
                    lambda: self.input_driver.paste_image_file(Path(step.preset_image_path)),
                    window,
                    step_index,
                    step_phase="slot1_after_text",
                )
            except Exception as exc:
                self._emit_slot_1_event(
                    "slot1_image_paste_failed",
                    step_index,
                    image_path=str(step.preset_image_path),
                    error_type=type(exc).__name__,
                    error=str(exc),
                    window_handle=window.handle,
                )
                raise
            if stopped_result is not None:
                self._emit_slot_1_event(
                    "slot1_image_paste_stopped",
                    step_index,
                    image_path=str(step.preset_image_path),
                    reason=stopped_result.failure_reason,
                    window_handle=window.handle,
                )
                return stopped_result
            self._emit_slot_1_event(
                "slot1_image_paste_succeeded",
                step_index,
                image_path=str(step.preset_image_path),
                window_handle=window.handle,
            )
            stopped_result = self._sleep_or_stop(
                1.0,
                window,
                step_index,
                step_phase="slot1_after_image",
            )
            if stopped_result is not None:
                return stopped_result
            pasted_image = True
            prepared_finish_location = self._prepare_slot_1_finish_after_image(
                window,
                step,
                step_index,
            )
            if isinstance(prepared_finish_location, RunResult):
                return prepared_finish_location
        elif step.preset_image_path is not None and skip_image_paste:
            pasted_image = True
        if step.preset_text is not None and not pasted_image and not skip_image_paste:
            stopped_result = self._sleep_or_stop(
                _SLOT_1_TEXT_TO_IMAGE_DELAY_SECONDS,
                window,
                step_index,
                step_phase="slot1_after_text",
            )
            if stopped_result is not None:
                return stopped_result
        if self._stop_requested:
            return self._stopped_result(
                window,
                step_index,
                step_phase="slot1_before_finish_search",
            )
        finish_template_path = step.finish_template_path
        if finish_template_path is None or not Path(finish_template_path).exists():
            return RunResult(
                status="failed",
                failure_reason="finish_template_missing",
                window_handle=window.handle,
                step_index=step_index,
            )
        finish_template = self.template_loader(finish_template_path)
        finish_search_step = replace(
            step,
            max_search_seconds=_SLOT_1_FINISH_SEARCH_SECONDS,
            max_scroll_attempts=max(
                step.max_scroll_attempts,
                _SLOT_1_FINISH_SCROLL_ATTEMPTS,
            ),
        )
        finish_location = prepared_finish_location
        if finish_location is None:
            self._emit_slot_1_event(
                "slot1_finish_search_started",
                step_index,
                phase="final",
                window_handle=window.handle,
            )
            finish_location = self._find_match_for_template(
                window,
                finish_search_step,
                step_index,
                finish_template,
            )
            if not isinstance(finish_location, RunResult):
                found_window, _found_frame, found_match = finish_location
                self._emit_slot_1_event(
                    "slot1_finish_search_found",
                    step_index,
                    phase="final",
                    score=found_match.score,
                    center=[found_match.center_x, found_match.center_y],
                    window_handle=found_window.handle,
                )
            elif finish_location.failure_reason == "match_not_found":
                self._emit_slot_1_event(
                    "slot1_finish_search_not_found",
                    step_index,
                    phase="final",
                    window_handle=finish_location.window_handle,
                )
            else:
                self._emit_slot_1_event(
                    "slot1_finish_search_failed",
                    step_index,
                    phase="final",
                    reason=finish_location.failure_reason,
                    window_handle=finish_location.window_handle,
                )
        if isinstance(finish_location, RunResult):
            return finish_location
        finish_window, finish_frame, finish_match = finish_location
        finish_window = self._refresh_active_window(finish_window, step_index)
        if isinstance(finish_window, RunResult):
            return finish_window
        finish_point = self._resolve_click_point(
            finish_window,
            step,
            step_index,
            finish_match,
        )
        if isinstance(finish_point, RunResult):
            return finish_point
        self._emit_slot_1_event(
            "slot1_finish_click_started",
            step_index,
            point=finish_point,
            window_handle=finish_window.handle,
        )
        stopped_result = self._try_input_action(
            lambda: self.input_driver.move_click(
                finish_point, delay_seconds=_SLOT_1_FINISH_CLICK_DELAY_SECONDS
            ),
            finish_window,
            step_index,
            step_phase="slot1_before_finish_search",
        )
        if stopped_result is not None:
            return stopped_result
        self._emit_slot_1_event(
            "slot1_finish_click_succeeded",
            step_index,
            point=finish_point,
            window_handle=finish_window.handle,
        )
        self.emit_event(
            {
                "type": "step_clicked",
                "step_index": step_index,
                "point": finish_point,
            }
        )
        immediate_retry = self._reclick_slot_1_finish_if_still_visible(
            finish_window,
            step,
            step_index,
            finish_template,
            finish_frame,
            finish_match,
        )
        if isinstance(immediate_retry, RunResult):
            return immediate_retry
        finish_window, finish_frame, finish_match, _finish_reclicked = immediate_retry
        stopped_result = self._sleep_or_stop(
            step.finish_delay_seconds
            if step.finish_delay_seconds is not None
            else _SLOT_1_FINISH_POST_CLICK_DELAY_SECONDS,
            finish_window,
            step_index,
            stop_after_completion=True,
        )
        if stopped_result is not None:
            return stopped_result
        confirmation = self._confirm_ui_changed_after_click(
            finish_window,
            step,
            step_index,
            finish_template,
            finish_match,
            finish_frame,
        )
        if isinstance(confirmation, RunResult):
            if confirmation.status == "completed":
                submission_check = self._verify_slot_1_reply_submission(
                    finish_window,
                    step,
                    step_index,
                    finish_template,
                    finish_frame,
                    finish_match,
                )
                if submission_check is not None:
                    return submission_check
                self.emit_event(
                    {
                        "type": "step_succeeded",
                        "step_index": step_index,
                        "window_handle": finish_window.handle,
                    }
                )
                return None
            return confirmation
        if self._step_succeeded(finish_match, confirmation):
            submission_check = self._verify_slot_1_reply_submission(
                finish_window,
                step,
                step_index,
                finish_template,
                finish_frame,
                finish_match,
            )
            if submission_check is not None:
                return submission_check
            self.emit_event(
                {
                    "type": "step_succeeded",
                    "step_index": step_index,
                    "window_handle": finish_window.handle,
                }
            )
            return None
        self._emit_slot_1_event(
            "slot1_finish_click_confirmation_failed",
            step_index,
            point=finish_point,
            score=finish_match.score,
            center=[finish_match.center_x, finish_match.center_y],
            window_handle=finish_window.handle,
        )
        return RunResult(
            status="failed",
            failure_reason="ui_did_not_change",
            window_handle=finish_window.handle,
            step_index=step_index,
        )

    def _prepare_slot_1_finish_after_text(
        self,
        window: WindowInfo,
        step: AutomationStep,
        step_index: int,
    ) -> RunResult | tuple[WindowInfo, Any, MatchResult] | None:
        finish_template_path = step.finish_template_path
        if finish_template_path is None or not Path(finish_template_path).exists():
            return None
        finish_template = self.template_loader(finish_template_path)
        stopped_result = self._sleep_or_stop(
            _SLOT_1_FINISH_AFTER_TEXT_SETTLE_SECONDS,
            window,
            step_index,
            step_phase="slot1_after_text",
        )
        if stopped_result is not None:
            return stopped_result
        finish_probe_step = replace(
            step,
            max_search_seconds=_SLOT_1_FINISH_AFTER_TEXT_SEARCH_SECONDS,
            max_scroll_attempts=0,
        )
        dismissed_obstruction = self._dismiss_slot_1_obstruction_if_visible(
            window,
            step,
            step_index,
        )
        if isinstance(dismissed_obstruction, RunResult):
            return dismissed_obstruction
        if dismissed_obstruction:
            finish_location = self._find_match_for_template(
                window,
                finish_probe_step,
                step_index,
                finish_template,
            )
            if not isinstance(finish_location, RunResult):
                return finish_location
            if finish_location.failure_reason != "match_not_found":
                return finish_location
        first_obstruction_found = bool(dismissed_obstruction)
        finish_location = self._find_match_for_template(
            window,
            finish_probe_step,
            step_index,
            finish_template,
        )
        if not isinstance(finish_location, RunResult):
            return finish_location
        if finish_location.failure_reason != "match_not_found":
            return finish_location
        if not first_obstruction_found:
            dismissed_obstruction = self._dismiss_slot_1_obstruction_if_visible(
                window,
                step,
                step_index,
            )
            if isinstance(dismissed_obstruction, RunResult):
                return dismissed_obstruction
            if dismissed_obstruction:
                finish_location = self._find_match_for_template(
                    window,
                    finish_probe_step,
                    step_index,
                    finish_template,
                )
                if not isinstance(finish_location, RunResult):
                    return finish_location
                if finish_location.failure_reason != "match_not_found":
                    return finish_location
        window = self._refresh_active_window(window, step_index)
        if isinstance(window, RunResult):
            return window
        stopped_result = self._try_input_action(
            lambda: self.input_driver.scroll(step.scroll_amount),
            window,
            step_index,
            step_phase="slot1_after_text",
        )
        if stopped_result is not None:
            return stopped_result
        self.emit_event(
            {
                "type": "slot1_finish_hidden_scroll_performed",
                "step_index": step_index,
                "window_handle": window.handle,
                "amount": step.scroll_amount,
            }
        )
        stopped_result = self._sleep_or_stop(
            _SLOT_1_FINISH_AFTER_TEXT_SCROLL_SETTLE_SECONDS,
            window,
            step_index,
            step_phase="slot1_after_text",
        )
        if stopped_result is not None:
            return stopped_result
        dismissed_obstruction = self._dismiss_slot_1_obstruction_if_visible(
            window,
            step,
            step_index,
        )
        if isinstance(dismissed_obstruction, RunResult):
            return dismissed_obstruction
        if dismissed_obstruction:
            finish_location = self._find_match_for_template(
                window,
                finish_probe_step,
                step_index,
                finish_template,
            )
            if not isinstance(finish_location, RunResult):
                return finish_location
            if finish_location.failure_reason != "match_not_found":
                return finish_location
        finish_location = self._find_match_for_template(
            window,
            finish_probe_step,
            step_index,
            finish_template,
        )
        if not isinstance(finish_location, RunResult):
            return finish_location
        if finish_location.failure_reason != "match_not_found":
            return finish_location
        return None

    def _prepare_slot_1_finish_after_image(
        self,
        window: WindowInfo,
        step: AutomationStep,
        step_index: int,
    ) -> RunResult | tuple[WindowInfo, Any, MatchResult] | None:
        finish_template_path = step.finish_template_path
        if finish_template_path is None or not Path(finish_template_path).exists():
            return None
        finish_template = self.template_loader(finish_template_path)
        finish_probe_step = replace(
            step,
            max_search_seconds=_SLOT_1_FINISH_AFTER_TEXT_SEARCH_SECONDS,
            max_scroll_attempts=0,
        )
        self._emit_slot_1_event(
            "slot1_finish_search_started",
            step_index,
            phase="after_image",
            window_handle=window.handle,
        )
        finish_location = self._find_match_for_template(
            window,
            finish_probe_step,
            step_index,
            finish_template,
        )
        if not isinstance(finish_location, RunResult):
            found_window, _found_frame, found_match = finish_location
            self._emit_slot_1_event(
                "slot1_finish_search_found",
                step_index,
                phase="after_image",
                score=found_match.score,
                center=[found_match.center_x, found_match.center_y],
                window_handle=found_window.handle,
            )
            return finish_location
        if finish_location.failure_reason != "match_not_found":
            return finish_location
        dismissed_obstruction = self._dismiss_slot_1_obstruction_if_visible(
            window,
            step,
            step_index,
        )
        if isinstance(dismissed_obstruction, RunResult):
            return dismissed_obstruction
        if dismissed_obstruction:
            finish_location = self._find_match_for_template(
                window,
                finish_probe_step,
                step_index,
                finish_template,
            )
            if not isinstance(finish_location, RunResult):
                return finish_location
            if finish_location.failure_reason != "match_not_found":
                return finish_location
        window = self._refresh_active_window(window, step_index)
        if isinstance(window, RunResult):
            return window
        stopped_result = self._try_input_action(
            lambda: self.input_driver.scroll(step.scroll_amount),
            window,
            step_index,
            step_phase="slot1_after_image",
        )
        if stopped_result is not None:
            return stopped_result
        self.emit_event(
            {
                "type": "slot1_finish_hidden_after_image_scroll_performed",
                "step_index": step_index,
                "window_handle": window.handle,
                "amount": step.scroll_amount,
            }
        )
        stopped_result = self._sleep_or_stop(
            _SLOT_1_FINISH_AFTER_TEXT_SCROLL_SETTLE_SECONDS,
            window,
            step_index,
            step_phase="slot1_after_image",
        )
        if stopped_result is not None:
            return stopped_result
        dismissed_obstruction = self._dismiss_slot_1_obstruction_if_visible(
            window,
            step,
            step_index,
        )
        if isinstance(dismissed_obstruction, RunResult):
            return dismissed_obstruction
        if dismissed_obstruction:
            finish_location = self._find_match_for_template(
                window,
                finish_probe_step,
                step_index,
                finish_template,
            )
            if not isinstance(finish_location, RunResult):
                return finish_location
            if finish_location.failure_reason != "match_not_found":
                return finish_location
        finish_location = self._find_match_for_template(
            window,
            finish_probe_step,
            step_index,
            finish_template,
        )
        if not isinstance(finish_location, RunResult):
            return finish_location
        if finish_location.failure_reason != "match_not_found":
            return finish_location
        return None

    def _dismiss_slot_1_obstruction_if_visible(
        self,
        window: WindowInfo,
        step: AutomationStep,
        step_index: int,
    ) -> RunResult | bool:
        obstruction_template_path = step.obstruction_template_path
        if (
            obstruction_template_path is None
            or not Path(obstruction_template_path).exists()
        ):
            return False
        obstruction_template = self.template_loader(obstruction_template_path)
        obstruction_probe_step = replace(
            step,
            max_search_seconds=0.0,
            max_scroll_attempts=0,
        )
        obstruction_location = self._find_match_for_template(
            window,
            obstruction_probe_step,
            step_index,
            obstruction_template,
        )
        if isinstance(obstruction_location, RunResult):
            if obstruction_location.failure_reason == "match_not_found":
                return False
            return obstruction_location
        obstruction_window, _frame, _match = obstruction_location
        obstruction_window = self._refresh_active_window(obstruction_window, step_index)
        if isinstance(obstruction_window, RunResult):
            return obstruction_window
        stopped_result = self._try_input_action(
            self.input_driver.press_escape,
            obstruction_window,
            step_index,
            step_phase="slot1_obstruction",
        )
        if stopped_result is not None:
            return stopped_result
        self.emit_event(
            {
                "type": "slot1_obstruction_escape_pressed",
                "step_index": step_index,
                "window_handle": obstruction_window.handle,
            }
        )
        stopped_result = self._sleep_or_stop(
            _SLOT_1_FINISH_AFTER_TEXT_ESCAPE_DELAY_SECONDS,
            obstruction_window,
            step_index,
            step_phase="slot1_obstruction",
        )
        if stopped_result is not None:
            return stopped_result
        return True

    def _reclick_slot_1_finish_if_still_visible(
        self,
        window: WindowInfo,
        step: AutomationStep,
        step_index: int,
        finish_template: Any,
        finish_frame: Any,
        finish_match: MatchResult,
    ) -> RunResult | tuple[WindowInfo, Any, MatchResult, bool]:
        reset_point = self._resolve_hover_reset_point(window, finish_match)
        stopped_result = self._try_input_action(
            lambda: self.input_driver.move_cursor(reset_point),
            window,
            step_index,
        )
        if stopped_result is not None:
            return stopped_result
        stopped_result = self._sleep_or_stop(
            _SLOT_1_RETRY_HOVER_RESET_DELAY_SECONDS,
            window,
            step_index,
        )
        if stopped_result is not None:
            return stopped_result
        reply_check_step = replace(
            step,
            max_search_seconds=_SLOT_1_REPLY_SUBMIT_RECHECK_SECONDS,
            max_scroll_attempts=0,
        )
        self._emit_slot_1_event(
            "slot1_finish_recheck_started",
            step_index,
            window_handle=window.handle,
        )
        finish_still_visible = self._find_match_for_template(
            window,
            reply_check_step,
            step_index,
            finish_template,
        )
        if isinstance(finish_still_visible, RunResult):
            if finish_still_visible.failure_reason == "match_not_found":
                self._emit_slot_1_event(
                    "slot1_finish_recheck_gone",
                    step_index,
                    window_handle=finish_still_visible.window_handle,
                )
                return (window, finish_frame, finish_match, False)
            return finish_still_visible
        retry_window, retry_frame, retry_match = finish_still_visible
        if self._did_match_region_change(
            finish_frame,
            retry_frame,
            finish_match,
        ):
            self._emit_slot_1_event(
                "slot1_finish_recheck_changed",
                step_index,
                score=retry_match.score,
                center=[retry_match.center_x, retry_match.center_y],
                window_handle=retry_window.handle,
            )
            return (window, finish_frame, finish_match, False)
        self._emit_slot_1_event(
            "slot1_finish_recheck_still_visible",
            step_index,
            score=retry_match.score,
            center=[retry_match.center_x, retry_match.center_y],
            window_handle=retry_window.handle,
        )
        retry_window = self._refresh_active_window(retry_window, step_index)
        if isinstance(retry_window, RunResult):
            return retry_window
        retry_point = self._resolve_click_point(
            retry_window,
            step,
            step_index,
            retry_match,
        )
        if isinstance(retry_point, RunResult):
            return retry_point
        self._emit_slot_1_event(
            "slot1_finish_reclick_started",
            step_index,
            point=retry_point,
            window_handle=retry_window.handle,
        )
        stopped_result = self._try_input_action(
            lambda: self.input_driver.move_click(
                retry_point, delay_seconds=_SLOT_1_FINISH_CLICK_DELAY_SECONDS
            ),
            retry_window,
            step_index,
        )
        if stopped_result is not None:
            return stopped_result
        self._emit_slot_1_event(
            "slot1_finish_reclick_succeeded",
            step_index,
            point=retry_point,
            window_handle=retry_window.handle,
        )
        self.emit_event(
            {
                "type": "step_clicked",
                "step_index": step_index,
                "point": retry_point,
            }
        )
        retry_reset_point = self._resolve_hover_reset_point(retry_window, retry_match)
        stopped_result = self._try_input_action(
            lambda: self.input_driver.move_cursor(retry_reset_point),
            retry_window,
            step_index,
        )
        if stopped_result is not None:
            return stopped_result
        stopped_result = self._sleep_or_stop(
            _SLOT_1_RETRY_HOVER_RESET_DELAY_SECONDS,
            retry_window,
            step_index,
        )
        if stopped_result is not None:
            return stopped_result
        return (retry_window, retry_frame, retry_match, True)

    def _verify_slot_1_reply_submission(
        self,
        window: WindowInfo,
        step: AutomationStep,
        step_index: int,
        finish_template: Any,
        original_finish_frame: Any,
        original_finish_match: MatchResult,
    ) -> RunResult | None:
        reply_check_step = replace(
            step,
            max_search_seconds=_SLOT_1_REPLY_SUBMIT_RECHECK_SECONDS,
            max_scroll_attempts=0,
        )
        finish_still_visible = self._find_match_for_template(
            window,
            reply_check_step,
            step_index,
            finish_template,
        )
        if isinstance(finish_still_visible, RunResult):
            if finish_still_visible.failure_reason == "match_not_found":
                return None
            return finish_still_visible
        retry_window, retry_frame, retry_match = finish_still_visible
        if self._did_match_region_change(
            original_finish_frame,
            retry_frame,
            original_finish_match,
        ):
            return None
        retry_window = self._refresh_active_window(retry_window, step_index)
        if isinstance(retry_window, RunResult):
            return retry_window
        retry_point = self._resolve_click_point(
            retry_window,
            step,
            step_index,
            retry_match,
        )
        if isinstance(retry_point, RunResult):
            return retry_point
        retry_reset_point = self._resolve_hover_reset_point(retry_window, retry_match)
        stopped_result = self._try_input_action(
            lambda: self.input_driver.move_cursor(retry_reset_point),
            retry_window,
            step_index,
        )
        if stopped_result is not None:
            return stopped_result
        stopped_result = self._sleep_or_stop(
            _SLOT_1_RETRY_HOVER_RESET_DELAY_SECONDS,
            retry_window,
            step_index,
        )
        if stopped_result is not None:
            return stopped_result
        stopped_result = self._try_input_action(
            lambda: self.input_driver.move_click(
                retry_point, delay_seconds=_SLOT_1_FINISH_CLICK_DELAY_SECONDS
            ),
            retry_window,
            step_index,
        )
        if stopped_result is not None:
            return stopped_result
        self.emit_event(
            {
                "type": "step_clicked",
                "step_index": step_index,
                "point": retry_point,
            }
        )
        retry_reset_point = self._resolve_hover_reset_point(retry_window, retry_match)
        stopped_result = self._try_input_action(
            lambda: self.input_driver.move_cursor(retry_reset_point),
            retry_window,
            step_index,
        )
        if stopped_result is not None:
            return stopped_result
        stopped_result = self._sleep_or_stop(
            _SLOT_1_RETRY_HOVER_RESET_DELAY_SECONDS,
            retry_window,
            step_index,
        )
        if stopped_result is not None:
            return stopped_result
        stopped_result = self._sleep_or_stop(
            _SLOT_1_REPLY_SUBMIT_RETRY_DELAY_SECONDS,
            retry_window,
            step_index,
        )
        if stopped_result is not None:
            return stopped_result
        finish_after_retry = self._find_match_for_template(
            retry_window,
            reply_check_step,
            step_index,
            finish_template,
        )
        if isinstance(finish_after_retry, RunResult):
            if finish_after_retry.failure_reason == "match_not_found":
                return None
            return finish_after_retry
        _final_window, final_frame, _final_match = finish_after_retry
        if self._did_match_region_change(
            original_finish_frame,
            final_frame,
            original_finish_match,
        ):
            return None
        return RunResult(
            status="failed",
            failure_reason="reply_submit_not_confirmed",
            window_handle=retry_window.handle,
            step_index=step_index,
        )

    def _step_succeeded(self, previous_match: MatchResult, next_match: MatchResult | None) -> bool:
        if next_match is None:
            return True
        return self._has_material_shift(previous_match, next_match)

    def _emit_slot_1_event(
        self,
        event_type: str,
        step_index: int,
        **fields: Any,
    ) -> None:
        self.emit_event(
            {
                "type": event_type,
                "step_index": step_index,
                **fields,
            }
        )

    def _confirm_ui_changed_after_click(
        self,
        window: WindowInfo,
        step: AutomationStep,
        step_index: int,
        template: Any,
        clicked_match: MatchResult,
        pre_click_frame: Any,
    ) -> RunResult | MatchResult | None:
        deadline = self.now() + self.click_confirmation_seconds
        settle_seconds = min(step.post_click_settle_ms / 1000, max(0.0, deadline - self.now()))
        if settle_seconds > 0:
            self.sleep(settle_seconds)
        while True:
            window = self._refresh_active_window(window, step_index)
            if isinstance(window, RunResult):
                return window
            frame = self.capture.capture(window.bounds)
            next_match = self.matcher.find_best_match(
                frame,
                template,
                threshold=step.match_threshold,
            )
            if self._did_match_region_change(pre_click_frame, frame, clicked_match):
                return RunResult(
                    status="completed",
                    window_handle=window.handle,
                    step_index=step_index,
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

    def _try_input_action(
        self,
        action: Callable[[], None],
        window: WindowInfo,
        step_index: int,
        *,
        step_phase: str | None = None,
    ) -> RunResult | None:
        try:
            action()
        except InputStopRequested:
            return self._stopped_result(window, step_index, step_phase=step_phase)
        return None

    def _sleep_or_stop(
        self,
        seconds: float,
        window: WindowInfo,
        step_index: int,
        *,
        step_phase: str | None = None,
        stop_after_completion: bool = False,
    ) -> RunResult | None:
        if seconds <= 0:
            if stop_after_completion and self._stop_requested:
                return self._stopped_result(window, step_index + 1)
            if self._stop_requested:
                return self._stopped_result(window, step_index, step_phase=step_phase)
            return None
        deadline = self.now() + seconds
        while True:
            remaining = deadline - self.now()
            if remaining <= 0:
                break
            self.sleep(min(self.scan_interval_seconds, remaining))
            if self._stop_requested:
                if stop_after_completion:
                    break
                return self._stopped_result(window, step_index, step_phase=step_phase)
        if stop_after_completion and self._stop_requested:
            return self._stopped_result(window, step_index + 1)
        return None

    def _stopped_result(
        self,
        window: WindowInfo,
        step_index: int,
        *,
        step_phase: str | None = None,
    ) -> RunResult:
        return RunResult(
            status="stopped",
            failure_reason="stopped",
            window_handle=window.handle,
            step_index=step_index,
            step_phase=step_phase,
        )

    def _has_material_shift(self, previous_match: MatchResult, next_match: MatchResult) -> bool:
        min_dimension = min(previous_match.width, previous_match.height)
        threshold = max(10.0, 0.25 * float(min_dimension))
        delta_x = next_match.center_x - previous_match.center_x
        delta_y = next_match.center_y - previous_match.center_y
        distance = (delta_x**2 + delta_y**2) ** 0.5
        return distance > threshold

    def _did_match_region_change(
        self,
        before_frame: Any,
        after_frame: Any,
        clicked_match: MatchResult,
    ) -> bool:
        before_region = self._extract_match_region(before_frame, clicked_match)
        after_region = self._extract_match_region(after_frame, clicked_match)
        if before_region is None or after_region is None:
            return False
        if before_region.shape != after_region.shape:
            return True
        difference = abs(before_region.astype("float32") - after_region.astype("float32"))
        return float(difference.mean()) >= 5.0

    def _extract_match_region(
        self,
        frame: Any,
        match: MatchResult,
    ):
        if frame is None:
            return None
        shape = getattr(frame, "shape", None)
        if shape is None or len(shape) < 2:
            return None
        height, width = int(shape[0]), int(shape[1])
        left = max(0, min(match.top_left_x, width))
        top = max(0, min(match.top_left_y, height))
        right = max(left, min(match.top_left_x + match.width, width))
        bottom = max(top, min(match.top_left_y + match.height, height))
        if right <= left or bottom <= top:
            return None
        return frame[top:bottom, left:right]
