from __future__ import annotations

from concurrent.futures import Future
from pathlib import Path

from raidbot.desktop.automation.models import AutomationSequence, AutomationStep, MatchResult
from raidbot.desktop.automation.storage import AutomationStorage
from raidbot.desktop.automation.windowing import WindowInfo
from raidbot.desktop.models import DesktopAppConfig


class FakeStorage:
    def __init__(self, base_dir: Path, config: DesktopAppConfig) -> None:
        self.base_dir = base_dir
        self._config = config
        self.saved_configs: list[DesktopAppConfig] = []

    def is_first_run(self) -> bool:
        return False

    def load_config(self) -> DesktopAppConfig:
        return self._config

    def save_config(self, config: DesktopAppConfig) -> None:
        self.saved_configs.append(config)
        self._config = config


class ImmediateRunner:
    def __init__(self) -> None:
        self.running = False
        self.started_jobs = []
        self.submitted_jobs = []

    def start(self, job) -> None:
        self.started_jobs.append(job)
        self.running = True
        try:
            job()
        finally:
            self.running = False

    def submit(self, job):
        self.submitted_jobs.append(job)
        future = Future()
        try:
            future.set_result(job())
        except Exception as exc:
            future.set_exception(exc)
        return future

    def is_running(self) -> bool:
        return self.running

    def wait_until_stopped(self, timeout: float | None = None) -> bool:
        return True


class PassiveRunner:
    def __init__(self) -> None:
        self.running = False
        self.started_jobs = []
        self.submitted_jobs = []

    def start(self, job) -> None:
        self.started_jobs.append(job)
        self.running = True

    def submit(self, job):
        self.submitted_jobs.append(job)
        future = Future()
        try:
            future.set_result(job())
        except Exception as exc:
            future.set_exception(exc)
        return future

    def is_running(self) -> bool:
        return self.running

    def wait_until_stopped(self, timeout: float | None = None) -> bool:
        self.running = False
        return True


class FakeAutomationRuntime:
    def __init__(
        self,
        *,
        windows: list[WindowInfo] | None = None,
        run_events: list[dict[str, object]] | None = None,
        run_result=None,
        dry_run_events: list[dict[str, object]] | None = None,
        dry_run_result=None,
    ) -> None:
        self.windows = windows or []
        self.run_events = run_events or []
        self.run_result = run_result
        self.dry_run_events = dry_run_events or []
        self.dry_run_result = dry_run_result
        self.run_calls: list[tuple[str, int | None]] = []
        self.dry_run_calls: list[tuple[str, int, int | None]] = []
        self.stop_calls = 0
        self.emit_event = None

    def attach_emitter(self, emit_event) -> None:
        self.emit_event = emit_event

    def list_target_windows(self) -> list[WindowInfo]:
        return list(self.windows)

    def run_sequence(self, sequence: AutomationSequence, selected_window_handle: int | None):
        self.run_calls.append((sequence.id, selected_window_handle))
        for event in self.run_events:
            self.emit_event(event)
        return self.run_result

    def dry_run_step(
        self,
        sequence: AutomationSequence,
        step_index: int,
        selected_window_handle: int | None,
    ):
        self.dry_run_calls.append((sequence.id, step_index, selected_window_handle))
        for event in self.dry_run_events:
            self.emit_event(event)
        return self.dry_run_result

    def request_stop(self) -> None:
        self.stop_calls += 1


def build_config(**overrides) -> DesktopAppConfig:
    values = {
        "telegram_api_id": 123456,
        "telegram_api_hash": "hash-value",
        "telegram_session_path": Path("raidbot.session"),
        "telegram_phone_number": "+40123456789",
        "whitelisted_chat_ids": [-1001],
        "raidar_sender_id": 42,
        "chrome_profile_directory": "Profile 3",
    }
    values.update(overrides)
    return DesktopAppConfig(**values)


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


def build_window(handle: int = 7, title: str = "Chrome") -> WindowInfo:
    return WindowInfo(
        handle=handle,
        title=title,
        bounds=(0, 0, 100, 100),
        last_focused_at=1.0,
    )


def build_controller(
    tmp_path: Path,
    *,
    runtime: FakeAutomationRuntime,
    runner_factory=ImmediateRunner,
):
    from raidbot.desktop.automation.runner import RunResult
    from raidbot.desktop.controller import DesktopController

    storage = FakeStorage(tmp_path, build_config())
    AutomationStorage(tmp_path).save_sequences([build_sequence()])

    controller = DesktopController(
        storage=storage,
        config=build_config(),
        runner_factory=runner_factory,
        automation_runtime_probe=lambda: (True, None),
        automation_runtime_factory=lambda emit_event: runtime.attach_emitter(emit_event) or runtime,
    )
    return controller, storage, RunResult


def test_controller_loads_saved_sequences_on_startup(tmp_path) -> None:
    controller, _storage, _run_result = build_controller(
        tmp_path,
        runtime=FakeAutomationRuntime(),
    )

    assert controller.list_automation_sequences()[0].name == "Chrome Flow"


def test_controller_lists_target_windows_for_ui_picker(tmp_path) -> None:
    controller, _storage, _run_result = build_controller(
        tmp_path,
        runtime=FakeAutomationRuntime(windows=[build_window(title="RaidBot - Chrome")]),
    )

    assert controller.list_target_windows()[0].title.endswith("Chrome")


def test_controller_emits_automation_events_from_runner(qtbot, tmp_path) -> None:
    runtime = FakeAutomationRuntime(
        run_events=[
            {"type": "run_started"},
            {"type": "target_window_acquired"},
            {"type": "step_search_started"},
            {"type": "step_found"},
            {"type": "step_clicked"},
            {"type": "step_succeeded"},
            {"type": "run_completed"},
        ],
    )
    controller, _storage, RunResult = build_controller(tmp_path, runtime=runtime)
    received = []
    states = []
    controller.automationRunEvent.connect(received.append)
    controller.automationRunStateChanged.connect(states.append)

    controller.start_automation_run("seq-1", selected_window_handle=7)

    assert [event["type"] for event in received] == [
        "run_started",
        "target_window_acquired",
        "step_search_started",
        "step_found",
        "step_clicked",
        "step_succeeded",
        "run_completed",
    ]
    assert states == ["running", "idle"]


def test_controller_emits_failure_and_stopped_events_for_unhappy_paths(qtbot, tmp_path) -> None:
    failure_runtime = FakeAutomationRuntime(
        run_result=None,
    )
    controller, _storage, RunResult = build_controller(
        tmp_path,
        runtime=failure_runtime,
    )
    received = []
    controller.automationRunEvent.connect(received.append)

    failure_runtime.run_result = RunResult(status="failed", failure_reason="target_window_not_found")
    controller.start_automation_run("seq-1", selected_window_handle=None)

    stopped_runtime = FakeAutomationRuntime(
        run_events=[{"type": "step_failed"}],
        run_result=RunResult(status="stopped", failure_reason="stopped"),
    )
    stopped_controller, _storage, _RunResult = build_controller(
        tmp_path / "stopped",
        runtime=stopped_runtime,
    )
    stopped_controller.automationRunEvent.connect(received.append)
    stopped_controller.start_automation_run("seq-1", selected_window_handle=7)

    stop_runtime = FakeAutomationRuntime(run_result=None)
    stop_controller, _storage, _RunResult = build_controller(
        tmp_path / "stop",
        runtime=stop_runtime,
        runner_factory=PassiveRunner,
    )
    stop_controller.start_automation_run("seq-1", selected_window_handle=None)
    stop_controller.stop_automation_run()
    qtbot.waitUntil(lambda: stop_runtime.stop_calls == 1)

    event_types = [event["type"] for event in received]
    assert "target_window_lost" in event_types
    assert "step_failed" in event_types
    assert "run_stopped" in event_types


def test_controller_surfaces_dry_run_match_result_to_ui(qtbot, tmp_path) -> None:
    runtime = FakeAutomationRuntime(
        dry_run_result=None,
    )
    controller, _storage, RunResult = build_controller(tmp_path, runtime=runtime)
    received = []
    controller.automationRunEvent.connect(received.append)

    runtime.dry_run_result = RunResult(
        status="dry_run_match_found",
        step_index=0,
        window_handle=7,
        match=MatchResult(score=0.97, top_left_x=10, top_left_y=20, width=8, height=8),
    )
    controller.dry_run_automation_step("seq-1", 0, selected_window_handle=7)

    assert received[-1]["type"] == "dry_run_match_found"
