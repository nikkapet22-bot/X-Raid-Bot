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
    ) -> None:
        self.windows = windows or []
        self.focus_success = focus_success
        self.ensured_handles: list[int] = []

    def list_chrome_windows(self) -> list[WindowInfo]:
        return list(self.windows)

    def ensure_interactable_window(self, window: WindowInfo) -> WindowInteractionOutcome:
        self.ensured_handles.append(window.handle)
        if not self.focus_success:
            return WindowInteractionOutcome(success=False, reason="window_not_focusable")
        return WindowInteractionOutcome(success=True, window=window)


class FakeCapture:
    def __init__(self) -> None:
        self.frames = [np.zeros((40, 40), dtype=np.uint8)]
        self.calls = 0

    def capture(self, _bounds):
        self.calls += 1
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
        self.scrolls: list[int] = []

    def move_click(self, point: tuple[int, int], *, delay_seconds: float = 0.5) -> None:
        self.clicks.append(point)

    def scroll(self, amount: int) -> None:
        self.scrolls.append(amount)


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
    assert input_driver.scrolls == [-120]


def test_runner_retries_after_non_changing_click_then_fails() -> None:
    runner = SequenceRunner(
        window_manager=FakeWindowManager(windows=[_window()]),
        capture=FakeCapture(),
        matcher=FakeMatcher([_match(), _match(), _match()]),
        input_driver=FakeInputDriver(),
        template_loader=lambda _path: np.zeros((10, 10), dtype=np.uint8),
        now=FakeClock().now,
        sleep=FakeClock().sleep,
    )

    result = runner.run_sequence(_sequence(_step(max_click_attempts=2)), selected_window=_window())

    assert result.status == "failed"
    assert result.failure_reason == "no_ui_change_after_click"
    assert len(runner.input_driver.clicks) == 2


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
    manager = FakeWindowManager(windows=[reacquired_window])
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
    assert manager.ensured_handles == [9]


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
