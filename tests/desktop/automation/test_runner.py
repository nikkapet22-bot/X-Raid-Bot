from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from raidbot.desktop.automation.models import AutomationSequence, AutomationStep, MatchResult
from raidbot.desktop.automation.runner import SequenceRunner
from raidbot.desktop.automation.windowing import WindowInfo, WindowInteractionOutcome


@dataclass
class FakeClock:
    value: float = 100.0

    def now(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.value += seconds


class FakeWindowManager:
    def __init__(
        self,
        *,
        windows: list[WindowInfo] | None = None,
        focus_success: bool = True,
        listed_windows: list[list[WindowInfo]] | None = None,
        ensure_outcomes: list[WindowInteractionOutcome] | None = None,
    ) -> None:
        self.windows = windows or []
        self.focus_success = focus_success
        self.listed_windows = [list(batch) for batch in listed_windows] if listed_windows else []
        self.ensure_outcomes = list(ensure_outcomes or [])
        self.ensured_handles: list[int] = []

    def list_chrome_windows(self) -> list[WindowInfo]:
        if self.listed_windows:
            if len(self.listed_windows) > 1:
                return self.listed_windows.pop(0)
            return list(self.listed_windows[0])
        return list(self.windows)

    def ensure_interactable_window(self, window: WindowInfo) -> WindowInteractionOutcome:
        self.ensured_handles.append(window.handle)
        if self.ensure_outcomes:
            outcome = self.ensure_outcomes.pop(0)
            if outcome.success and outcome.window is None:
                return WindowInteractionOutcome(success=True, window=window)
            return outcome
        if not self.focus_success:
            return WindowInteractionOutcome(success=False, reason="window_not_focusable")
        return WindowInteractionOutcome(success=True, window=window)


class FakeCapture:
    def __init__(self, frames: list[np.ndarray] | None = None) -> None:
        self.frames = list(frames or [np.zeros((40, 40), dtype=np.uint8)])
        self.calls = 0

    def capture(self, _bounds):
        self.calls += 1
        if len(self.frames) > 1:
            return self.frames.pop(0)
        return self.frames[0]


class FakeMatcher:
    def __init__(self, results: list[MatchResult | None]) -> None:
        self.results = list(results)
        self.calls = 0

    def find_best_match(self, _frame, _template, threshold: float):
        self.calls += 1
        if self.results:
            return self.results.pop(0)
        return None


class FakeInputDriver:
    def __init__(self) -> None:
        self.clicks: list[tuple[int, int]] = []
        self.cursor_moves: list[tuple[int, int]] = []
        self.scrolls: list[int] = []
        self.pasted_text: list[str] = []
        self.pasted_images: list[Path] = []
        self.file_pasted_images: list[Path] = []

    def move_click(self, point: tuple[int, int], *, delay_seconds: float = 0.5) -> None:
        self.clicks.append(point)

    def move_cursor(self, point: tuple[int, int]) -> None:
        self.cursor_moves.append(point)

    def scroll(self, amount: int) -> None:
        self.scrolls.append(amount)

    def paste_text(self, text: str) -> None:
        self.pasted_text.append(text)

    def paste_image(self, image_path: Path) -> None:
        self.pasted_images.append(image_path)

    def paste_image_file(self, image_path: Path) -> None:
        self.file_pasted_images.append(image_path)


def _step(**overrides) -> AutomationStep:
    values = {
        "name": "step",
        "template_path": Path("template.png"),
        "match_threshold": 0.8,
        "max_search_seconds": 0.2,
        "max_scroll_attempts": 1,
        "scroll_amount": -120,
        "max_click_attempts": 2,
        "post_click_settle_ms": 100,
        "click_offset_x": 0,
        "click_offset_y": 0,
    }
    values.update(overrides)
    return AutomationStep(**values)


def _sequence(*steps: AutomationStep, target_window_rule: str | None = None) -> AutomationSequence:
    return AutomationSequence(
        id="sequence-1",
        name="Chrome Flow",
        target_window_rule=target_window_rule,
        steps=list(steps),
    )


def _window(
    handle: int = 7,
    *,
    title: str = "RaidBot - Chrome",
    bounds: tuple[int, int, int, int] = (0, 0, 100, 100),
) -> WindowInfo:
    return WindowInfo(
        handle=handle,
        title=title,
        bounds=bounds,
        last_focused_at=1.0,
    )


def _match(x: int = 20, y: int = 10) -> MatchResult:
    return MatchResult(score=0.95, top_left_x=x, top_left_y=y, width=10, height=10)


def test_runner_clicks_match_and_advances_to_next_step() -> None:
    events: list[dict[str, object]] = []
    runner = SequenceRunner(
        window_manager=FakeWindowManager(windows=[_window()]),
        capture=FakeCapture(),
        matcher=FakeMatcher([_match(), None]),
        input_driver=FakeInputDriver(),
        template_loader=lambda _path: np.zeros((10, 10), dtype=np.uint8),
        now=FakeClock().now,
        sleep=FakeClock().sleep,
        emit_event=events.append,
    )

    result = runner.run_sequence(_sequence(_step()), selected_window=_window())

    assert result.status == "completed"
    assert result.window_handle == 7
    assert runner.input_driver.clicks == [(25, 15)]
    assert [event["type"] for event in events] == [
        "run_started",
        "target_window_acquired",
        "step_search_started",
        "step_found",
        "step_clicked",
        "step_succeeded",
        "run_completed",
    ]


def test_runner_fails_when_template_never_appears_after_scroll_budget() -> None:
    clock = FakeClock()
    input_driver = FakeInputDriver()
    runner = SequenceRunner(
        window_manager=FakeWindowManager(windows=[_window()]),
        capture=FakeCapture(),
        matcher=FakeMatcher([None, None, None, None, None]),
        input_driver=input_driver,
        template_loader=lambda _path: np.zeros((10, 10), dtype=np.uint8),
        now=clock.now,
        sleep=clock.sleep,
    )

    result = runner.run_sequence(_sequence(_step(max_scroll_attempts=1)), selected_window=_window())

    assert result.status == "failed"
    assert result.failure_reason == "match_not_found"
    assert input_driver.cursor_moves == []
    assert input_driver.scrolls == [-120]


def test_runner_retries_after_non_changing_click_then_fails() -> None:
    clock = FakeClock()
    matcher = FakeMatcher([_match()] * 64)
    runner = SequenceRunner(
        window_manager=FakeWindowManager(windows=[_window()]),
        capture=FakeCapture(),
        matcher=matcher,
        input_driver=FakeInputDriver(),
        template_loader=lambda _path: np.zeros((10, 10), dtype=np.uint8),
        now=clock.now,
        sleep=clock.sleep,
    )

    result = runner.run_sequence(_sequence(_step(max_click_attempts=1)), selected_window=_window())

    assert result.status == "failed"
    assert result.failure_reason == "ui_did_not_change"
    assert len(runner.input_driver.clicks) == 1
    assert matcher.calls >= 3


def test_runner_caps_no_change_confirmation_budget_at_two_seconds_from_click() -> None:
    clock = FakeClock()
    matcher = FakeMatcher([_match()] * 64)
    runner = SequenceRunner(
        window_manager=FakeWindowManager(windows=[_window()]),
        capture=FakeCapture(),
        matcher=matcher,
        input_driver=FakeInputDriver(),
        template_loader=lambda _path: np.zeros((10, 10), dtype=np.uint8),
        now=clock.now,
        sleep=clock.sleep,
        scan_interval_seconds=0.6,
    )

    result = runner.run_sequence(
        _sequence(_step(max_click_attempts=1, post_click_settle_ms=500)),
        selected_window=_window(),
    )

    assert result.status == "failed"
    assert result.failure_reason == "ui_did_not_change"
    assert clock.value <= 102.0


def test_runner_rejects_click_offset_outside_window_bounds() -> None:
    runner = SequenceRunner(
        window_manager=FakeWindowManager(windows=[_window()]),
        capture=FakeCapture(),
        matcher=FakeMatcher([_match()]),
        input_driver=FakeInputDriver(),
        template_loader=lambda _path: np.zeros((10, 10), dtype=np.uint8),
        now=FakeClock().now,
        sleep=FakeClock().sleep,
    )

    result = runner.run_sequence(
        _sequence(_step(click_offset_x=1000)),
        selected_window=_window(),
    )

    assert result.status == "failed"
    assert result.failure_reason == "invalid_click_target"
    assert runner.input_driver.clicks == []


def test_runner_converts_match_coordinates_to_screen_space() -> None:
    runner = SequenceRunner(
        window_manager=FakeWindowManager(windows=[_window(bounds=(100, 200, 300, 400))]),
        capture=FakeCapture(),
        matcher=FakeMatcher([_match(), None]),
        input_driver=FakeInputDriver(),
        template_loader=lambda _path: np.zeros((10, 10), dtype=np.uint8),
        now=FakeClock().now,
        sleep=FakeClock().sleep,
    )

    result = runner.run_sequence(
        _sequence(_step()),
        selected_window=_window(bounds=(100, 200, 300, 400)),
    )

    assert result.status == "completed"
    assert runner.input_driver.clicks == [(125, 215)]


def test_runner_dry_run_reports_match_without_clicking() -> None:
    runner = SequenceRunner(
        window_manager=FakeWindowManager(windows=[_window()]),
        capture=FakeCapture(),
        matcher=FakeMatcher([_match()]),
        input_driver=FakeInputDriver(),
        template_loader=lambda _path: np.zeros((10, 10), dtype=np.uint8),
        now=FakeClock().now,
        sleep=FakeClock().sleep,
    )

    result = runner.dry_run_step(_sequence(_step()), 0, selected_window=_window())

    assert result.status == "dry_run_match_found"
    assert result.match is not None
    assert runner.input_driver.clicks == []


def test_runner_prefers_selected_window_over_saved_rule() -> None:
    selected_window = _window(handle=9, title="Selected - Chrome")
    reacquired_window = _window(handle=3, title="Rule Match - Chrome")
    manager = FakeWindowManager(windows=[selected_window, reacquired_window])
    runner = SequenceRunner(
        window_manager=manager,
        capture=FakeCapture(),
        matcher=FakeMatcher([_match(), None]),
        input_driver=FakeInputDriver(),
        template_loader=lambda _path: np.zeros((10, 10), dtype=np.uint8),
        now=FakeClock().now,
        sleep=FakeClock().sleep,
    )

    result = runner.run_sequence(
        _sequence(_step(), target_window_rule="Rule Match"),
        selected_window=selected_window,
    )

    assert result.status == "completed"
    assert result.window_handle == 9
    assert manager.ensured_handles
    assert set(manager.ensured_handles) == {9}


def test_runner_reacquires_window_from_saved_rule_when_no_selection_is_provided() -> None:
    reacquired_window = _window(handle=3, title="Rule Match - Chrome")
    runner = SequenceRunner(
        window_manager=FakeWindowManager(windows=[_window(handle=1, title="Other - Chrome"), reacquired_window]),
        capture=FakeCapture(),
        matcher=FakeMatcher([_match(), None]),
        input_driver=FakeInputDriver(),
        template_loader=lambda _path: np.zeros((10, 10), dtype=np.uint8),
        now=FakeClock().now,
        sleep=FakeClock().sleep,
    )

    result = runner.run_sequence(
        _sequence(_step(), target_window_rule="Rule Match"),
        selected_window=None,
    )

    assert result.status == "completed"
    assert result.window_handle == 3


def test_runner_fails_when_window_disappears_mid_run() -> None:
    window = _window()
    runner = SequenceRunner(
        window_manager=FakeWindowManager(
            windows=[window],
            listed_windows=[[window], []],
        ),
        capture=FakeCapture(),
        matcher=FakeMatcher([_match()]),
        input_driver=FakeInputDriver(),
        template_loader=lambda _path: np.zeros((10, 10), dtype=np.uint8),
        now=FakeClock().now,
        sleep=FakeClock().sleep,
    )

    result = runner.run_sequence(
        _sequence(_step(max_click_attempts=1)),
        selected_window=window,
    )

    assert result.status == "failed"
    assert result.failure_reason == "target_window_not_found"
    assert runner.input_driver.clicks == []


def test_runner_fails_when_window_becomes_not_focusable_mid_run() -> None:
    window = _window()
    runner = SequenceRunner(
        window_manager=FakeWindowManager(
            windows=[window],
            listed_windows=[[window], [window]],
            ensure_outcomes=[
                WindowInteractionOutcome(success=True, window=window),
                WindowInteractionOutcome(success=False, reason="window_not_focusable"),
            ],
        ),
        capture=FakeCapture(),
        matcher=FakeMatcher([_match()]),
        input_driver=FakeInputDriver(),
        template_loader=lambda _path: np.zeros((10, 10), dtype=np.uint8),
        now=FakeClock().now,
        sleep=FakeClock().sleep,
    )

    result = runner.run_sequence(
        _sequence(_step(max_click_attempts=1)),
        selected_window=window,
    )

    assert result.status == "failed"
    assert result.failure_reason == "window_not_focusable"
    assert runner.input_driver.clicks == []


def test_runner_can_run_without_focus_requirement_for_slot_tests() -> None:
    window = _window()
    manager = FakeWindowManager(windows=[window], focus_success=False)
    runner = SequenceRunner(
        window_manager=manager,
        capture=FakeCapture(),
        matcher=FakeMatcher([_match(), None]),
        input_driver=FakeInputDriver(),
        template_loader=lambda _path: np.zeros((10, 10), dtype=np.uint8),
        now=FakeClock().now,
        sleep=FakeClock().sleep,
        require_interactable_window=False,
    )

    result = runner.run_sequence(_sequence(_step()), selected_window=window)

    assert result.status == "completed"
    assert result.window_handle == window.handle
    assert runner.input_driver.clicks == [(25, 15)]
    assert manager.ensured_handles == []


def test_runner_does_not_require_focus_during_search_before_scroll_or_click() -> None:
    window = _window()
    capture = FakeCapture()

    class DelayedFocusWindowManager(FakeWindowManager):
        def ensure_interactable_window(self, candidate: WindowInfo) -> WindowInteractionOutcome:
            self.ensured_handles.append(candidate.handle)
            if len(self.ensured_handles) >= 2 and capture.calls == 0:
                return WindowInteractionOutcome(success=False, reason="window_not_focusable")
            return WindowInteractionOutcome(success=True, window=candidate)

    input_driver = FakeInputDriver()
    clock = FakeClock()
    runner = SequenceRunner(
        window_manager=DelayedFocusWindowManager(windows=[window]),
        capture=capture,
        matcher=FakeMatcher([None, _match(), None]),
        input_driver=input_driver,
        template_loader=lambda _path: np.zeros((10, 10), dtype=np.uint8),
        now=clock.now,
        sleep=clock.sleep,
    )

    result = runner.run_sequence(
        _sequence(_step(max_search_seconds=0.0, max_scroll_attempts=1)),
        selected_window=window,
    )

    assert result.status == "completed"
    assert input_driver.scrolls == [-120]
    assert input_driver.cursor_moves == []
    assert input_driver.clicks == [(25, 15)]


def test_runner_can_move_cursor_into_window_before_scroll_when_enabled() -> None:
    window = _window(bounds=(10, 20, 110, 220))
    input_driver = FakeInputDriver()
    clock = FakeClock()
    runner = SequenceRunner(
        window_manager=FakeWindowManager(windows=[window]),
        capture=FakeCapture(),
        matcher=FakeMatcher([None, _match(), None]),
        input_driver=input_driver,
        template_loader=lambda _path: np.zeros((10, 10), dtype=np.uint8),
        now=clock.now,
        sleep=clock.sleep,
        move_cursor_before_scroll=True,
    )

    result = runner.run_sequence(
        _sequence(_step(max_search_seconds=0.0, max_scroll_attempts=1)),
        selected_window=window,
    )

    assert result.status == "completed"
    assert input_driver.cursor_moves == [(60, 120)]
    assert input_driver.scrolls == [-120]
    assert input_driver.clicks == [(35, 35)]


def test_runner_performs_two_clicks_before_confirming_when_step_requires_it() -> None:
    clock = FakeClock()
    runner = SequenceRunner(
        window_manager=FakeWindowManager(windows=[_window()]),
        capture=FakeCapture(),
        matcher=FakeMatcher([_match(), None]),
        input_driver=FakeInputDriver(),
        template_loader=lambda _path: np.zeros((10, 10), dtype=np.uint8),
        now=clock.now,
        sleep=clock.sleep,
    )

    result = runner.run_sequence(
        _sequence(
            _step(
                max_click_attempts=2,
                pre_confirm_clicks=2,
                inter_click_delay_ms=500,
            )
        ),
        selected_window=_window(),
    )

    assert result.status == "completed"
    assert runner.input_driver.clicks == [(25, 15), (25, 15)]
    assert clock.value >= 100.5


def test_runner_counts_same_position_visual_change_as_success() -> None:
    before = np.zeros((40, 40, 3), dtype=np.uint8)
    after = before.copy()
    before[10:20, 20:30] = [0, 0, 0]
    after[10:20, 20:30] = [0, 0, 255]
    runner = SequenceRunner(
        window_manager=FakeWindowManager(windows=[_window()]),
        capture=FakeCapture(frames=[before, after]),
        matcher=FakeMatcher([_match(), _match()]),
        input_driver=FakeInputDriver(),
        template_loader=lambda _path: np.zeros((10, 10), dtype=np.uint8),
        now=FakeClock().now,
        sleep=FakeClock().sleep,
    )

    result = runner.run_sequence(_sequence(_step(max_click_attempts=1)), selected_window=_window())

    assert result.status == "completed"
    assert runner.input_driver.clicks == [(25, 15)]


def test_runner_slot_1_pastes_text_optional_image_and_clicks_finish_template(
    tmp_path: Path,
) -> None:
    clock = FakeClock()
    input_driver = FakeInputDriver()
    reply_image_path = tmp_path / "reply.png"
    reply_image_path.write_bytes(b"reply image")
    finish_template_path = tmp_path / "finish.png"
    finish_template_path.write_bytes(b"finish image")
    runner = SequenceRunner(
        window_manager=FakeWindowManager(windows=[_window()]),
        capture=FakeCapture(),
        matcher=FakeMatcher([_match(), _match(40, 10), None]),
        input_driver=input_driver,
        template_loader=lambda _path: np.zeros((10, 10), dtype=np.uint8),
        now=clock.now,
        sleep=clock.sleep,
    )

    result = runner.run_sequence(
        _sequence(
                _step(
                    name="slot_1_r",
                    preset_text="gm",
                    preset_image_path=reply_image_path,
                    finish_template_path=finish_template_path,
                    max_click_attempts=1,
                )
            ),
        selected_window=_window(),
    )

    assert result.status == "completed"
    assert input_driver.pasted_text == ["gm"]
    assert input_driver.file_pasted_images == [reply_image_path]
    assert input_driver.pasted_images == []
    assert input_driver.clicks == [(25, 15), (45, 15)]


def test_runner_slot_1_pastes_text_and_image_without_extra_waits(
    tmp_path: Path,
) -> None:
    clock = FakeClock()

    class TimedInputDriver(FakeInputDriver):
        def __init__(self, current_time) -> None:
            super().__init__()
            self.events: list[tuple[str, float]] = []
            self._current_time = current_time

        def paste_text(self, text: str) -> None:
            super().paste_text(text)
            self.events.append((f"text:{text}", self._current_time()))

        def paste_image(self, image_path: Path) -> None:
            super().paste_image(image_path)
            self.events.append((f"image:{image_path}", self._current_time()))

        def paste_image_file(self, image_path: Path) -> None:
            super().paste_image_file(image_path)
            self.events.append((f"file_image:{image_path}", self._current_time()))

    input_driver = TimedInputDriver(clock.now)
    reply_image_path = tmp_path / "reply.png"
    reply_image_path.write_bytes(b"reply image")
    finish_template_path = tmp_path / "finish.png"
    finish_template_path.write_bytes(b"finish image")
    runner = SequenceRunner(
        window_manager=FakeWindowManager(windows=[_window()]),
        capture=FakeCapture(),
        matcher=FakeMatcher([_match(), _match(40, 10), None]),
        input_driver=input_driver,
        template_loader=lambda _path: np.zeros((10, 10), dtype=np.uint8),
        now=clock.now,
        sleep=clock.sleep,
    )

    result = runner.run_sequence(
        _sequence(
            _step(
                name="slot_1_r",
                preset_text="gm",
                preset_image_path=reply_image_path,
                finish_template_path=finish_template_path,
                max_click_attempts=1,
            )
        ),
        selected_window=_window(),
    )

    assert result.status == "completed"
    assert input_driver.events == [
        ("text:gm", 100.0),
        (f"file_image:{reply_image_path}", 100.5),
    ]


def test_runner_slot_1_clicks_main_image_then_single_finish_image(
    tmp_path: Path,
) -> None:
    clock = FakeClock()
    input_driver = FakeInputDriver()
    finish_template_path = tmp_path / "finish.png"
    finish_template_path.write_bytes(b"finish image")
    runner = SequenceRunner(
        window_manager=FakeWindowManager(windows=[_window()]),
        capture=FakeCapture(),
        matcher=FakeMatcher([_match(), _match(40, 10), None]),
        input_driver=input_driver,
        template_loader=lambda _path: np.zeros((10, 10), dtype=np.uint8),
        now=clock.now,
        sleep=clock.sleep,
    )

    result = runner.run_sequence(
        _sequence(
            _step(
                name="slot_1_r",
                preset_text="gm",
                finish_template_path=finish_template_path,
                max_click_attempts=1,
            )
        ),
        selected_window=_window(),
    )

    assert result.status == "completed"
    assert input_driver.clicks == [(25, 15), (45, 15)]
    assert clock.value >= 102.0


def test_runner_slot_1_uses_configured_finish_delay(
    tmp_path: Path,
) -> None:
    clock = FakeClock()
    input_driver = FakeInputDriver()
    finish_template_path = tmp_path / "finish.png"
    finish_template_path.write_bytes(b"finish image")
    runner = SequenceRunner(
        window_manager=FakeWindowManager(windows=[_window()]),
        capture=FakeCapture(),
        matcher=FakeMatcher([_match(), _match(40, 10), None]),
        input_driver=input_driver,
        template_loader=lambda _path: np.zeros((10, 10), dtype=np.uint8),
        now=clock.now,
        sleep=clock.sleep,
    )

    result = runner.run_sequence(
        _sequence(
            _step(
                name="slot_1_r",
                preset_text="gm",
                finish_template_path=finish_template_path,
                finish_delay_seconds=4.0,
                max_click_attempts=1,
            )
        ),
        selected_window=_window(),
    )

    assert result.status == "completed"
    assert input_driver.clicks == [(25, 15), (45, 15)]
    assert clock.value >= 104.0


def test_runner_slot_1_waits_briefly_for_finish_image_before_scrolling(
    tmp_path: Path,
) -> None:
    clock = FakeClock()
    input_driver = FakeInputDriver()
    finish_template_path = tmp_path / "finish.png"
    finish_template_path.write_bytes(b"finish image")
    runner = SequenceRunner(
        window_manager=FakeWindowManager(windows=[_window()]),
        capture=FakeCapture(),
        matcher=FakeMatcher([_match(), None, _match(40, 10), None]),
        input_driver=input_driver,
        template_loader=lambda _path: np.zeros((10, 10), dtype=np.uint8),
        now=clock.now,
        sleep=clock.sleep,
    )

    result = runner.run_sequence(
        _sequence(
            _step(
                name="slot_1_r",
                preset_text="gm",
                finish_template_path=finish_template_path,
                max_click_attempts=1,
            )
        ),
        selected_window=_window(),
    )

    assert result.status == "completed"
    assert input_driver.scrolls == []
    assert input_driver.clicks == [(25, 15), (45, 15)]
    assert clock.value >= 102.1


def test_runner_slot_1_scrolls_down_when_finish_image_is_not_initially_visible(
    tmp_path: Path,
) -> None:
    clock = FakeClock()
    input_driver = FakeInputDriver()
    finish_template_path = tmp_path / "finish.png"
    finish_template_path.write_bytes(b"finish image")
    runner = SequenceRunner(
        window_manager=FakeWindowManager(windows=[_window()]),
        capture=FakeCapture(),
        matcher=FakeMatcher([_match(), *([None] * 25), _match(40, 10), None]),
        input_driver=input_driver,
        template_loader=lambda _path: np.zeros((10, 10), dtype=np.uint8),
        now=clock.now,
        sleep=clock.sleep,
    )

    result = runner.run_sequence(
        _sequence(
            _step(
                name="slot_1_r",
                preset_text="gm",
                finish_template_path=finish_template_path,
                max_search_seconds=0.0,
                max_scroll_attempts=0,
                scroll_amount=-120,
                max_click_attempts=1,
            )
        ),
        selected_window=_window(),
    )

    assert result.status == "completed"
    assert input_driver.scrolls == [-120]
    assert input_driver.clicks == [(25, 15), (45, 15)]
    assert clock.value >= 102.1


def test_runner_slot_1_fails_when_finish_image_is_missing(
    tmp_path: Path,
) -> None:
    clock = FakeClock()
    input_driver = FakeInputDriver()
    finish_template_path = tmp_path / "finish.png"
    finish_template_path.write_bytes(b"finish image")
    runner = SequenceRunner(
        window_manager=FakeWindowManager(windows=[_window()]),
        capture=FakeCapture(),
        matcher=FakeMatcher([_match()]),
        input_driver=input_driver,
        template_loader=lambda _path: np.zeros((10, 10), dtype=np.uint8),
        now=clock.now,
        sleep=clock.sleep,
    )

    result = runner.run_sequence(
        _sequence(
            _step(
                name="slot_1_r",
                preset_text="gm",
                finish_template_path=tmp_path / "missing-finish.png",
                max_click_attempts=1,
            )
        ),
        selected_window=_window(),
    )

    assert result.status == "failed"
    assert result.failure_reason == "finish_template_missing"
