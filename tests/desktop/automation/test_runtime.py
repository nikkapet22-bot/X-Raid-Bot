from __future__ import annotations

from pathlib import Path

from raidbot.desktop.automation.models import AutomationSequence, AutomationStep
from raidbot.desktop.automation.runner import RunResult
from raidbot.desktop.automation.runtime import AutomationRuntime
from raidbot.desktop.automation.windowing import WindowInfo, WindowInteractionOutcome


class FakeWindowManager:
    def __init__(self, windows: list[WindowInfo]) -> None:
        self.windows = list(windows)

    def list_chrome_windows(self) -> list[WindowInfo]:
        return list(self.windows)

    def ensure_interactable_window(self, window: WindowInfo) -> WindowInteractionOutcome:
        return WindowInteractionOutcome(success=True, window=window)


class FakeSequenceRunner:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.request_stop_called = False

    def run_sequence(self, sequence: AutomationSequence, *, selected_window: WindowInfo | None):
        self.run_call = (sequence.id, getattr(selected_window, "handle", None))
        return RunResult(status="completed", window_handle=getattr(selected_window, "handle", None))

    def dry_run_step(
        self,
        sequence: AutomationSequence,
        step_index: int,
        *,
        selected_window: WindowInfo | None,
    ):
        self.dry_run_call = (sequence.id, step_index, getattr(selected_window, "handle", None))
        return RunResult(
            status="dry_run_match_found",
            step_index=step_index,
            window_handle=getattr(selected_window, "handle", None),
        )

    def request_stop(self) -> None:
        self.request_stop_called = True


class FailIfCalledSequenceRunner:
    def __init__(self, **_kwargs) -> None:
        raise AssertionError("sequence runner should not be created")


def build_sequence(sequence_id: str = "seq-1") -> AutomationSequence:
    return AutomationSequence(
        id=sequence_id,
        name="Chrome Flow",
        target_window_rule="Chrome",
        steps=[
            AutomationStep(
                name="Open menu",
                template_path=Path("templates/menu.png"),
                match_threshold=0.9,
                max_search_seconds=1.0,
                max_scroll_attempts=1,
                scroll_amount=-120,
                max_click_attempts=1,
                post_click_settle_ms=100,
            )
        ],
    )


def build_window(handle: int = 7, title: str = "RaidBot - Chrome") -> WindowInfo:
    return WindowInfo(
        handle=handle,
        title=title,
        bounds=(0, 0, 100, 100),
        last_focused_at=1.0,
    )


def test_runtime_reuses_shared_sequence_runner_and_request_stop() -> None:
    window = build_window()
    events: list[dict[str, object]] = []
    created: list[FakeSequenceRunner] = []

    def sequence_runner_factory(**kwargs):
        runner = FakeSequenceRunner(**kwargs)
        created.append(runner)
        return runner

    runtime = AutomationRuntime(
        emit_event=events.append,
        window_manager_factory=lambda: FakeWindowManager([window]),
        capture_factory=lambda: object(),
        matcher_factory=lambda: object(),
        input_driver_factory=lambda: object(),
        sequence_runner_factory=sequence_runner_factory,
    )

    assert runtime.list_target_windows() == [window]

    run_result = runtime.run_sequence(build_sequence(), selected_window_handle=window.handle)
    dry_run_result = runtime.dry_run_step(build_sequence(), 0, selected_window_handle=window.handle)
    runtime.request_stop()

    assert run_result.status == "completed"
    assert dry_run_result.status == "dry_run_match_found"
    assert created[0].run_call == ("seq-1", window.handle)
    assert created[1].dry_run_call == ("seq-1", 0, window.handle)
    assert created[1].request_stop_called is True


def test_runtime_fails_closed_when_selected_window_handle_is_missing() -> None:
    runtime = AutomationRuntime(
        emit_event=lambda _event: None,
        window_manager_factory=lambda: FakeWindowManager([]),
        capture_factory=lambda: object(),
        matcher_factory=lambda: object(),
        input_driver_factory=lambda: object(),
        sequence_runner_factory=FailIfCalledSequenceRunner,
    )

    result = runtime.run_sequence(build_sequence(), selected_window_handle=999)

    assert result.status == "failed"
    assert result.failure_reason == "target_window_not_found"
