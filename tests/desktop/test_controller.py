from __future__ import annotations

import os
import threading
from dataclasses import replace
from pathlib import Path
from concurrent.futures import Future
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from raidbot.desktop.automation.models import AutomationSequence, AutomationStep
from raidbot.desktop.models import BotActionPreset, DesktopAppConfig


class FakeStorage:
    def __init__(self) -> None:
        self.saved_configs: list[DesktopAppConfig] = []

    def save_config(self, config: DesktopAppConfig) -> None:
        self.saved_configs.append(config)

    def is_first_run(self) -> bool:
        return False

    def load_config(self) -> DesktopAppConfig:
        return build_config()


class FakeWorker:
    def __init__(self, *, emit_event, config: DesktopAppConfig, **_kwargs) -> None:
        self.emit_event = emit_event
        self.config = config
        self.run_calls = 0
        self.stop_calls = 0
        self.apply_calls: list[DesktopAppConfig] = []
        self.resume_calls = 0
        self.clear_calls = 0
        self.manual_finished_calls = 0

    async def run(self) -> None:
        self.run_calls += 1

    async def stop(self) -> None:
        self.stop_calls += 1

    async def apply_config(self, config: DesktopAppConfig) -> None:
        self.config = config
        self.apply_calls.append(config)

    def resume_automation_queue(self) -> None:
        self.resume_calls += 1

    def clear_automation_queue(self) -> None:
        self.clear_calls += 1

    def notify_manual_automation_finished(self) -> None:
        self.manual_finished_calls += 1


class FakeRunner:
    def __init__(self) -> None:
        self.started_coroutines = []
        self.submitted_coroutines = []
        self.running = False
        self.submission_future: Future | None = None
        self.stopped_event = threading.Event()
        self.wait_until_stopped_calls = 0

    def start(self, coroutine) -> None:
        self.started_coroutines.append(coroutine)
        self.running = True

    def submit(self, coroutine):
        self.submitted_coroutines.append(coroutine)
        if self.submission_future is None:
            future = Future()
            future.set_result(None)
            return future
        return self.submission_future

    def is_running(self) -> bool:
        return self.running

    def wait_until_stopped(self, timeout: float | None = None) -> bool:
        self.wait_until_stopped_calls += 1
        stopped = self.stopped_event.wait(timeout)
        if stopped:
            self.running = False
        return stopped


class ImmediateRunner:
    def __init__(self) -> None:
        self.started_jobs = []
        self.submitted_jobs = []
        self.running = False

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
        self.running = False
        return True


class RaisingAutomationRuntime:
    def __init__(self, exc: Exception) -> None:
        self.exc = exc

    def list_target_windows(self):
        return []

    def run_sequence(self, sequence, selected_window_handle):
        raise self.exc

    def dry_run_step(self, sequence, step_index, selected_window_handle):
        raise self.exc

    def request_stop(self) -> None:
        return None


class FakeSlotTestRuntime:
    def __init__(self, *, windows=None, result=None) -> None:
        from raidbot.desktop.automation.runner import RunResult

        self.windows = list(windows or [])
        self.result = result or RunResult(status="completed", window_handle=7, step_index=0)
        self.run_calls = []

    def list_target_windows(self):
        return list(self.windows)

    def run_sequence(
        self,
        sequence,
        selected_window_handle,
        *,
        require_interactable_window=True,
    ):
        self.run_calls.append((sequence, selected_window_handle, require_interactable_window))
        return self.result

    def dry_run_step(self, sequence, step_index, selected_window_handle):
        raise AssertionError("slot test should not use dry_run_step")

    def request_stop(self) -> None:
        return None


class FakeAutomationWindowManager:
    def __init__(self, windows=None) -> None:
        self.windows = list(windows or [])

    def list_chrome_windows(self):
        return list(self.windows)

    def ensure_interactable_window(self, window):
        from raidbot.desktop.automation.windowing import WindowInteractionOutcome

        return WindowInteractionOutcome(success=True, window=window)


class FailIfCalledSequenceRunner:
    def __init__(self, **_kwargs) -> None:
        raise AssertionError("sequence runner should not be created")


class FakeSenderResolverService:
    def __init__(self, resolved_ids_by_entry=None, failures=None) -> None:
        self.resolved_ids_by_entry = resolved_ids_by_entry or {}
        self.failures = set(failures or [])
        self.resolve_calls = []

    async def resolve_sender_entry(self, entry: str) -> int:
        self.resolve_calls.append(entry)
        if entry in self.failures:
            raise ValueError(f"Could not resolve sender '{entry}'.")
        return int(self.resolved_ids_by_entry[entry])


class FailIfResolveCalled:
    async def resolve_sender_entry(self, entry: str) -> int:
        raise AssertionError(f"resolve_sender_entry should not be called for {entry}")


def build_config(**overrides) -> DesktopAppConfig:
    values = {
        "telegram_api_id": 123456,
        "telegram_api_hash": "hash-value",
        "telegram_session_path": Path("raidbot.session"),
        "telegram_phone_number": "+40123456789",
        "whitelisted_chat_ids": [-1001],
        "allowed_sender_ids": [42],
        "allowed_sender_entries": ("42",),
        "chrome_profile_directory": "Profile 3",
    }
    values.update(overrides)
    return DesktopAppConfig(**values)


def build_sequence(sequence_id: str = "seq-1") -> AutomationSequence:
    return AutomationSequence(
        id=sequence_id,
        name="Chrome Flow",
        target_window_rule="Rule Match",
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


def test_controller_start_bot_and_forward_events(qtbot) -> None:
    from raidbot.desktop.controller import DesktopController

    storage = FakeStorage()
    created = {}

    def worker_factory(**kwargs):
        worker = FakeWorker(**kwargs)
        created["worker"] = worker
        return worker

    runner = FakeRunner()
    controller = DesktopController(
        storage=storage,
        config=build_config(),
        worker_factory=worker_factory,
        runner_factory=lambda: runner,
    )

    bot_states = []
    connection_states = []
    stats_payloads = []
    activity_entries = []
    errors = []
    controller.botStateChanged.connect(bot_states.append)
    controller.connectionStateChanged.connect(connection_states.append)
    controller.statsChanged.connect(stats_payloads.append)
    controller.activityAdded.connect(activity_entries.append)
    controller.errorRaised.connect(errors.append)

    controller.start_bot()

    assert created["worker"].config == build_config()
    assert len(runner.started_coroutines) == 1

    created["worker"].emit_event({"type": "bot_state_changed", "state": "running"})
    created["worker"].emit_event({"type": "connection_state_changed", "state": "connected"})
    created["worker"].emit_event({"type": "stats_changed", "state": object()})
    created["worker"].emit_event({"type": "activity_added", "entry": "entry"})
    created["worker"].emit_event({"type": "error", "message": "boom"})
    qtbot.waitUntil(lambda: errors == ["boom"])

    assert bot_states == ["running"]
    assert connection_states == ["connected"]
    assert len(stats_payloads) == 1
    assert activity_entries == ["entry"]


def test_controller_apply_config_saves_and_live_applies_when_running(qtbot) -> None:
    from raidbot.desktop.controller import DesktopController

    storage = FakeStorage()
    created = {}

    def worker_factory(**kwargs):
        worker = FakeWorker(**kwargs)
        created["worker"] = worker
        return worker

    runner = FakeRunner()
    controller = DesktopController(
        storage=storage,
        config=build_config(),
        worker_factory=worker_factory,
        runner_factory=lambda: runner,
    )
    controller.start_bot()

    new_config = build_config(
        whitelisted_chat_ids=[-1001, -2002],
        allowed_sender_ids=[99, 101],
        allowed_sender_entries=("99", "101"),
        chrome_profile_directory="Profile 9",
    )

    controller.apply_config(new_config)

    assert storage.saved_configs == [new_config]
    assert controller.config == new_config
    assert len(runner.submitted_coroutines) == 1


def test_controller_resolves_sender_entries_before_saving(qtbot) -> None:
    from raidbot.desktop.controller import DesktopController

    storage = FakeStorage()
    resolver = FakeSenderResolverService(
        resolved_ids_by_entry={"@delugeraidbot": 99, "raidar": 101}
    )
    controller = DesktopController(
        storage=storage,
        config=build_config(),
        worker_factory=lambda **kwargs: FakeWorker(**kwargs),
        runner_factory=lambda: FakeRunner(),
        telegram_setup_service_factory=lambda _config: resolver,
    )

    controller.apply_config(
        build_config(
            allowed_sender_ids=[],
            allowed_sender_entries=("@delugeraidbot", "raidar", "123"),
        )
    )

    assert resolver.resolve_calls == ["@delugeraidbot", "raidar"]
    assert storage.saved_configs[-1].allowed_sender_entries == (
        "@delugeraidbot",
        "raidar",
        "123",
    )
    assert storage.saved_configs[-1].allowed_sender_ids == [99, 101, 123]
    assert controller.config.allowed_sender_ids == [99, 101, 123]


def test_controller_rejects_unresolved_sender_entries_without_saving(qtbot) -> None:
    from raidbot.desktop.controller import DesktopController

    storage = FakeStorage()
    resolver = FakeSenderResolverService(failures={"@missing"})
    controller = DesktopController(
        storage=storage,
        config=build_config(),
        worker_factory=lambda **kwargs: FakeWorker(**kwargs),
        runner_factory=lambda: FakeRunner(),
        telegram_setup_service_factory=lambda _config: resolver,
    )

    try:
        controller.apply_config(
            build_config(
                allowed_sender_ids=[],
                allowed_sender_entries=("@missing",),
            )
        )
    except ValueError as exc:
        assert str(exc) == "Could not resolve sender '@missing'."
    else:
        raise AssertionError("Expected unresolved sender entry to raise ValueError.")

    assert storage.saved_configs == []
    assert controller.config == build_config()


def test_controller_updates_auto_run_config_through_apply_config(qtbot) -> None:
    from raidbot.desktop.controller import DesktopController

    storage = FakeStorage()
    controller = DesktopController(
        storage=storage,
        config=build_config(
            auto_run_enabled=False,
            default_auto_sequence_id=None,
            auto_run_settle_ms=1500,
        ),
        worker_factory=lambda **kwargs: FakeWorker(**kwargs),
        runner_factory=lambda: FakeRunner(),
    )
    configs = []
    controller.configChanged.connect(configs.append)

    controller.set_auto_run_enabled(True)
    controller.set_default_auto_sequence_id("seq-2")
    controller.set_auto_run_settle_ms(2750)

    assert storage.saved_configs[-1].auto_run_enabled is True
    assert storage.saved_configs[-1].default_auto_sequence_id == "seq-2"
    assert storage.saved_configs[-1].auto_run_settle_ms == 2750
    assert controller.config.auto_run_enabled is True
    assert controller.config.default_auto_sequence_id == "seq-2"
    assert controller.config.auto_run_settle_ms == 2750
    assert configs[-1] == controller.config


def test_controller_settle_delay_persists_without_resolving_sender_entries(qtbot) -> None:
    from raidbot.desktop.controller import DesktopController

    storage = FakeStorage()
    config = build_config(
        allowed_sender_ids=[42],
        allowed_sender_entries=("raidar",),
        auto_run_settle_ms=1500,
    )
    controller = DesktopController(
        storage=storage,
        config=config,
        worker_factory=lambda **kwargs: FakeWorker(**kwargs),
        runner_factory=lambda: FakeRunner(),
        telegram_setup_service_factory=lambda _config: FailIfResolveCalled(),
    )
    changed_configs = []
    controller.configChanged.connect(changed_configs.append)

    controller.set_auto_run_settle_ms(2750)

    assert storage.saved_configs[-1].auto_run_settle_ms == 2750
    assert storage.saved_configs[-1].allowed_sender_entries == ("raidar",)
    assert storage.saved_configs[-1].allowed_sender_ids == [42]
    assert controller.config.auto_run_settle_ms == 2750
    assert changed_configs[-1] == controller.config


def test_controller_capture_updates_bot_action_slot_template_and_saves(qtbot) -> None:
    from raidbot.desktop.controller import DesktopController

    storage = FakeStorage()
    config = build_config(
        allowed_sender_ids=[42],
        allowed_sender_entries=("raidar",),
    )
    controller = DesktopController(
        storage=storage,
        config=config,
        worker_factory=lambda **kwargs: FakeWorker(**kwargs),
        runner_factory=lambda: FakeRunner(),
        telegram_setup_service_factory=lambda _config: FailIfResolveCalled(),
    )
    updated_configs = []
    controller.configChanged.connect(updated_configs.append)
    captured_path = Path("bot_actions/slot_1_r.png")

    controller.set_bot_action_slot_template_path(0, captured_path)

    assert storage.saved_configs[-1].bot_action_slots[0].template_path == captured_path
    assert controller.config.bot_action_slots[0].template_path == captured_path
    assert updated_configs[-1].bot_action_slots[0].template_path == captured_path
    assert storage.saved_configs[-1].bot_action_slots[1:] == replace(
        config, bot_action_slots=storage.saved_configs[-1].bot_action_slots
    ).bot_action_slots[1:]


def test_controller_persists_slot_1_presets_and_finish_template(qtbot) -> None:
    from raidbot.desktop.controller import DesktopController

    storage = FakeStorage()
    config = build_config(
        allowed_sender_ids=[42],
        allowed_sender_entries=("raidar",),
    )
    controller = DesktopController(
        storage=storage,
        config=config,
        worker_factory=lambda **kwargs: FakeWorker(**kwargs),
        runner_factory=lambda: FakeRunner(),
        telegram_setup_service_factory=lambda _config: FailIfResolveCalled(),
    )
    updated_configs = []
    controller.configChanged.connect(updated_configs.append)
    presets = (
        BotActionPreset(
            id="preset-1",
            text="gm",
            image_path=Path("bot_actions/presets/gm.png"),
        ),
    )
    finish_template_path = Path("bot_actions/slot_1_r_finish.png")

    controller.set_bot_action_slot_1_presets(
        presets=presets,
        finish_template_path=finish_template_path,
    )

    saved_slot = storage.saved_configs[-1].bot_action_slots[0]
    assert saved_slot.presets == presets
    assert saved_slot.finish_template_path == finish_template_path
    assert controller.config.bot_action_slots[0].presets == presets
    assert controller.config.bot_action_slots[0].finish_template_path == finish_template_path
    assert updated_configs[-1].bot_action_slots[0].presets == presets


def test_controller_ignores_noop_slot_template_updates(qtbot) -> None:
    from raidbot.desktop.controller import DesktopController

    initial_config = build_config(
        bot_action_slots=(
            replace(build_config().bot_action_slots[0], template_path=Path("existing.png")),
            *build_config().bot_action_slots[1:],
        )
    )
    storage = FakeStorage()
    created = {}

    def worker_factory(**kwargs):
        worker = FakeWorker(**kwargs)
        created["worker"] = worker
        return worker

    runner = FakeRunner()
    controller = DesktopController(
        storage=storage,
        config=initial_config,
        worker_factory=worker_factory,
        runner_factory=lambda: runner,
        telegram_setup_service_factory=lambda _config: FailIfResolveCalled(),
    )
    controller.start_bot()
    changed_configs = []
    controller.configChanged.connect(changed_configs.append)

    controller.set_bot_action_slot_template_path(0, Path("existing.png"))

    assert storage.saved_configs == []
    assert changed_configs == []
    assert created["worker"].apply_calls == []
    assert runner.submitted_coroutines == []


def test_controller_slot_enabled_updates_bot_action_slot_and_saves(qtbot) -> None:
    from raidbot.desktop.controller import DesktopController

    storage = FakeStorage()
    config = build_config(
        allowed_sender_ids=[42],
        allowed_sender_entries=("raidar",),
    )
    controller = DesktopController(
        storage=storage,
        config=config,
        worker_factory=lambda **kwargs: FakeWorker(**kwargs),
        runner_factory=lambda: FakeRunner(),
        telegram_setup_service_factory=lambda _config: FailIfResolveCalled(),
    )
    updated_configs = []
    controller.configChanged.connect(updated_configs.append)

    controller.set_bot_action_slot_enabled(1, True)

    assert storage.saved_configs[-1].bot_action_slots[1].enabled is True
    assert controller.config.bot_action_slots[1].enabled is True
    assert updated_configs[-1].bot_action_slots[1].enabled is True
    assert storage.saved_configs[-1].bot_action_slots[0] == config.bot_action_slots[0]
    assert storage.saved_configs[-1].bot_action_slots[2:] == config.bot_action_slots[2:]


def test_controller_ignores_noop_slot_enabled_updates(qtbot) -> None:
    from raidbot.desktop.controller import DesktopController

    initial_config = build_config(
        bot_action_slots=(
            build_config().bot_action_slots[0],
            replace(build_config().bot_action_slots[1], enabled=True),
            *build_config().bot_action_slots[2:],
        )
    )
    storage = FakeStorage()
    created = {}

    def worker_factory(**kwargs):
        worker = FakeWorker(**kwargs)
        created["worker"] = worker
        return worker

    runner = FakeRunner()
    controller = DesktopController(
        storage=storage,
        config=initial_config,
        worker_factory=worker_factory,
        runner_factory=lambda: runner,
        telegram_setup_service_factory=lambda _config: FailIfResolveCalled(),
    )
    controller.start_bot()
    changed_configs = []
    controller.configChanged.connect(changed_configs.append)

    controller.set_bot_action_slot_enabled(1, True)

    assert storage.saved_configs == []
    assert changed_configs == []
    assert created["worker"].apply_calls == []
    assert runner.submitted_coroutines == []


def test_controller_rejects_slot_test_when_template_missing(qtbot) -> None:
    from raidbot.desktop.controller import DesktopController

    controller = DesktopController(
        storage=FakeStorage(),
        config=build_config(),
        runner_factory=ImmediateRunner,
        automation_runtime_probe=lambda: (True, None),
        automation_runtime_factory=lambda _emit_event: FakeSlotTestRuntime(),
    )
    events = []
    controller.botActionRunEvent.connect(events.append)

    controller.test_bot_action_slot(0)

    assert events == [
        {
            "type": "slot_test_failed",
            "slot_index": 0,
            "reason": "template_missing",
            "message": "Slot 1 (R): template missing",
        }
    ]


def test_controller_rejects_slot_test_when_template_file_is_missing(qtbot) -> None:
    from raidbot.desktop.controller import DesktopController

    controller = DesktopController(
        storage=FakeStorage(),
        config=build_config(
            bot_action_slots=(
                replace(
                    build_config().bot_action_slots[0],
                    template_path=Path("missing-template.png"),
                ),
                *build_config().bot_action_slots[1:],
            )
        ),
        runner_factory=ImmediateRunner,
        automation_runtime_probe=lambda: (True, None),
        automation_runtime_factory=lambda _emit_event: FakeSlotTestRuntime(),
    )
    events = []
    controller.botActionRunEvent.connect(events.append)

    controller.test_bot_action_slot(0)

    assert events == [
        {
            "type": "slot_test_failed",
            "slot_index": 0,
            "reason": "template_missing",
            "message": "Slot 1 (R): template missing",
        }
    ]


def test_controller_rejects_slot_1_test_when_no_presets_configured(
    qtbot,
    tmp_path: Path,
) -> None:
    from raidbot.desktop.controller import DesktopController

    template_path = tmp_path / "slot_1_r.png"
    template_path.write_bytes(b"capture")
    runtime = FakeSlotTestRuntime(
        windows=[SimpleNamespace(handle=9, last_focused_at=1.0, title="Chrome 1")]
    )
    controller = DesktopController(
        storage=FakeStorage(),
        config=build_config(
            bot_action_slots=(
                replace(build_config().bot_action_slots[0], template_path=template_path),
                *build_config().bot_action_slots[1:],
            )
        ),
        runner_factory=ImmediateRunner,
        automation_runtime_probe=lambda: (True, None),
        automation_runtime_factory=lambda _emit_event: runtime,
    )
    events = []
    controller.botActionRunEvent.connect(events.append)

    controller.test_bot_action_slot(0)

    assert events == [
        {
            "type": "slot_test_failed",
            "slot_index": 0,
            "reason": "no_presets_configured",
            "message": "Slot 1 (R): no presets configured",
        }
    ]
    assert runtime.run_calls == []


def test_controller_rejects_slot_test_when_no_chrome_window_exists(qtbot, tmp_path: Path) -> None:
    from raidbot.desktop.controller import DesktopController

    template_path = tmp_path / "slot_2_l.png"
    template_path.write_bytes(b"capture")
    runtime = FakeSlotTestRuntime(windows=[])
    controller = DesktopController(
        storage=FakeStorage(),
        config=build_config(
            bot_action_slots=(
                build_config().bot_action_slots[0],
                replace(build_config().bot_action_slots[1], template_path=template_path),
                *build_config().bot_action_slots[2:],
            )
        ),
        runner_factory=ImmediateRunner,
        automation_runtime_probe=lambda: (True, None),
        automation_runtime_factory=lambda _emit_event: runtime,
    )
    events = []
    controller.botActionRunEvent.connect(events.append)

    controller.test_bot_action_slot(1)

    assert events == [
        {
            "type": "slot_test_failed",
            "slot_index": 1,
            "reason": "target_window_not_found",
            "message": "Slot 2 (L): no Chrome window found",
        }
    ]
    assert runtime.run_calls == []


def test_controller_runs_slot_test_against_most_recent_chrome_window(qtbot, tmp_path: Path) -> None:
    from raidbot.desktop.controller import DesktopController

    template_path = tmp_path / "slot_2_l.png"
    template_path.write_bytes(b"capture")
    runtime = FakeSlotTestRuntime(
        windows=[
            SimpleNamespace(handle=7, last_focused_at=1.0, title="Chrome 1"),
            SimpleNamespace(handle=9, last_focused_at=5.0, title="Chrome 2"),
        ]
    )
    controller = DesktopController(
        storage=FakeStorage(),
        config=build_config(
            bot_action_slots=(
                build_config().bot_action_slots[0],
                replace(build_config().bot_action_slots[1], template_path=template_path),
                *build_config().bot_action_slots[2:],
            )
        ),
        runner_factory=ImmediateRunner,
        automation_runtime_probe=lambda: (True, None),
        automation_runtime_factory=lambda _emit_event: runtime,
    )
    events = []
    controller.botActionRunEvent.connect(events.append)

    controller.test_bot_action_slot(1)

    assert [event["type"] for event in events] == [
        "slot_test_started",
        "slot_test_succeeded",
    ]
    assert events[-1]["message"] == "Slot 2 (L): success"
    assert runtime.run_calls[0][1] == 9
    assert runtime.run_calls[0][2] is False
    assert runtime.run_calls[0][0].steps[0].template_path == template_path


def test_controller_stop_bot_submits_stop_when_running(qtbot) -> None:
    from raidbot.desktop.controller import DesktopController

    storage = FakeStorage()

    runner = FakeRunner()
    controller = DesktopController(
        storage=storage,
        config=build_config(),
        worker_factory=lambda **kwargs: FakeWorker(**kwargs),
        runner_factory=lambda: runner,
    )
    controller.start_bot()

    controller.stop_bot()

    assert len(runner.submitted_coroutines) == 1


def test_controller_stop_bot_and_wait_blocks_until_runner_exits(qtbot) -> None:
    from raidbot.desktop.controller import DesktopController

    storage = FakeStorage()
    runner = FakeRunner()
    stop_future = Future()
    runner.submission_future = stop_future
    controller = DesktopController(
        storage=storage,
        config=build_config(),
        worker_factory=lambda **kwargs: FakeWorker(**kwargs),
        runner_factory=lambda: runner,
    )
    controller.start_bot()

    completed = []

    def stop_worker() -> None:
        controller.stop_bot_and_wait()
        completed.append(True)

    thread = threading.Thread(target=stop_worker)
    thread.start()
    qtbot.waitUntil(lambda: len(runner.submitted_coroutines) == 1)
    assert completed == []

    stop_future.set_result(None)
    qtbot.waitUntil(lambda: runner.wait_until_stopped_calls == 1)
    assert completed == []

    runner.stopped_event.set()
    thread.join(timeout=1)

    assert completed == [True]
    assert runner.running is False


def test_controller_routes_submission_failures_to_error_signal(qtbot) -> None:
    from raidbot.desktop.controller import DesktopController

    storage = FakeStorage()
    runner = FakeRunner()
    failure = Future()
    failure.set_exception(RuntimeError("submit boom"))
    runner.submission_future = failure
    controller = DesktopController(
        storage=storage,
        config=build_config(),
        worker_factory=lambda **kwargs: FakeWorker(**kwargs),
        runner_factory=lambda: runner,
    )
    errors = []
    controller.errorRaised.connect(errors.append)
    controller.start_bot()

    controller.stop_bot()
    qtbot.waitUntil(lambda: errors == ["submit boom"])

    controller.apply_config(build_config(chrome_profile_directory="Profile 9"))
    qtbot.waitUntil(lambda: errors == ["submit boom", "submit boom"])


def test_controller_forwards_queue_and_auto_run_worker_events(qtbot) -> None:
    from raidbot.desktop.controller import DesktopController

    storage = FakeStorage()
    runner = FakeRunner()
    created = {}

    def worker_factory(**kwargs):
        worker = FakeWorker(**kwargs)
        created["worker"] = worker
        return worker

    controller = DesktopController(
        storage=storage,
        config=build_config(
            auto_run_enabled=True,
            default_auto_sequence_id="seq-1",
        ),
        worker_factory=worker_factory,
        runner_factory=lambda: runner,
    )

    queue_states = []
    queue_lengths = []
    current_urls = []
    run_events = []
    controller.automationQueueStateChanged.connect(queue_states.append)
    controller.automationQueueLengthChanged.connect(queue_lengths.append)
    controller.automationCurrentUrlChanged.connect(current_urls.append)
    controller.automationRunEvent.connect(run_events.append)

    controller.start_bot()

    created["worker"].emit_event({"type": "automation_queue_state_changed", "state": "queued"})
    created["worker"].emit_event({"type": "automation_queue_length_changed", "length": 3})
    created["worker"].emit_event(
        {"type": "automation_current_url_changed", "url": "https://example.com"}
    )
    created["worker"].emit_event(
        {
            "type": "automation_run_started",
            "sequence_id": "seq-1",
            "url": "https://example.com",
            "window_handle": 7,
        }
    )
    created["worker"].emit_event(
        {
            "type": "automation_run_succeeded",
            "sequence_id": "seq-1",
            "url": "https://example.com",
        }
    )
    created["worker"].emit_event(
        {
            "type": "automation_run_failed",
            "sequence_id": "seq-1",
            "url": "https://example.com",
            "reason": "boom",
        }
    )

    qtbot.waitUntil(
        lambda: queue_states == ["queued"]
        and queue_lengths == [3]
        and current_urls == ["https://example.com"]
        and len(run_events) == 3
    )

    assert run_events == [
        {
            "type": "automation_run_started",
            "sequence_id": "seq-1",
            "url": "https://example.com",
            "window_handle": 7,
        },
        {
            "type": "automation_run_succeeded",
            "sequence_id": "seq-1",
            "url": "https://example.com",
        },
        {
            "type": "automation_run_failed",
            "sequence_id": "seq-1",
            "url": "https://example.com",
            "reason": "boom",
        },
    ]

    controller.resume_automation_queue()
    controller.clear_automation_queue()

    assert len(runner.submitted_coroutines) == 2


def test_controller_forwards_bot_action_runtime_worker_events(qtbot) -> None:
    from raidbot.desktop.controller import DesktopController

    storage = FakeStorage()
    runner = FakeRunner()
    created = {}

    def worker_factory(**kwargs):
        worker = FakeWorker(**kwargs)
        created["worker"] = worker
        return worker

    controller = DesktopController(
        storage=storage,
        config=build_config(
            bot_action_slots=(
                replace(build_config().bot_action_slots[0], enabled=False),
                replace(build_config().bot_action_slots[1], enabled=True),
                replace(build_config().bot_action_slots[2], enabled=False),
                replace(build_config().bot_action_slots[3], enabled=False),
            )
        ),
        worker_factory=worker_factory,
        runner_factory=lambda: runner,
    )
    bot_action_events = []
    controller.botActionRunEvent.connect(bot_action_events.append)

    controller.start_bot()

    created["worker"].emit_event(
        {
            "type": "automation_run_started",
            "sequence_id": "slot-2-sequence",
            "url": "https://example.com",
        }
    )
    created["worker"].emit_event(
        {
            "type": "automation_runtime_event",
            "event": {"type": "step_search_started", "step_index": 0},
        }
    )
    created["worker"].emit_event(
        {
            "type": "automation_run_succeeded",
            "sequence_id": "slot-2-sequence",
            "url": "https://example.com",
        }
    )

    qtbot.waitUntil(lambda: len(bot_action_events) == 3)

    assert bot_action_events == [
        {
            "type": "automation_run_started",
            "sequence_id": "slot-2-sequence",
            "url": "https://example.com",
        },
        {"type": "step_search_started", "step_index": 0},
        {
            "type": "automation_run_succeeded",
            "sequence_id": "slot-2-sequence",
            "url": "https://example.com",
        },
    ]


def test_controller_rejects_manual_automation_actions_when_queue_owns_slot(qtbot) -> None:
    from raidbot.desktop.controller import DesktopController

    storage = FakeStorage()
    runner = FakeRunner()
    created = {}

    def worker_factory(**kwargs):
        worker = FakeWorker(**kwargs)
        created["worker"] = worker
        return worker

    created_runners = []

    def runner_factory():
        created_runners.append(runner)
        return runner

    controller = DesktopController(
        storage=storage,
        config=build_config(
            auto_run_enabled=True,
            default_auto_sequence_id="seq-1",
        ),
        worker_factory=worker_factory,
        runner_factory=runner_factory,
        automation_runtime_probe=lambda: (True, None),
        automation_runtime_factory=lambda _emit_event: object(),
    )
    controller._automation_sequences = [build_sequence()]
    errors = []
    controller.errorRaised.connect(errors.append)

    controller.start_bot()
    created["worker"].emit_event({"type": "automation_queue_state_changed", "state": "queued"})
    qtbot.waitUntil(lambda: errors == [])

    controller.start_automation_run("seq-1", selected_window_handle=7)
    controller.dry_run_automation_step("seq-1", 0, selected_window_handle=7)

    assert errors == [
        "Automation queue owns the execution slot",
        "Automation queue owns the execution slot",
    ]
    assert len(created_runners) == 1


def test_controller_notifies_worker_to_resume_queued_auto_run_after_manual_completion(
    qtbot,
) -> None:
    from raidbot.desktop.controller import DesktopController
    from raidbot.desktop.automation.runner import RunResult

    storage = FakeStorage()
    manual_runner = ImmediateRunner()
    created_worker = {}
    sequence = build_sequence()

    class ExecutingWorkerRunner(FakeRunner):
        def submit(self, coroutine):
            self.submitted_coroutines.append(coroutine)
            future = Future()
            try:
                future.set_result(coroutine())
            except Exception as exc:
                future.set_exception(exc)
            return future

    worker_runner = ExecutingWorkerRunner()

    def worker_factory(**kwargs):
        worker = FakeWorker(**kwargs)
        created_worker["worker"] = worker
        return worker

    runtime = None

    class QueueingRuntime:
        def run_sequence(self, current_sequence, selected_window_handle):
            created_worker["worker"].emit_event(
                {"type": "automation_queue_state_changed", "state": "queued"}
            )
            created_worker["worker"].emit_event(
                {"type": "automation_queue_length_changed", "length": 1}
            )
            return RunResult(status="completed", window_handle=selected_window_handle)

        def dry_run_step(self, current_sequence, step_index, selected_window_handle):
            raise AssertionError("dry run should not be called")

        def request_stop(self) -> None:
            return None

    runtime = QueueingRuntime()
    runners = iter([worker_runner, manual_runner])
    controller = DesktopController(
        storage=storage,
        config=build_config(),
        worker_factory=worker_factory,
        runner_factory=lambda: next(runners),
        automation_runtime_probe=lambda: (True, None),
        automation_runtime_factory=lambda _emit_event: runtime,
    )
    controller._automation_sequences = [sequence]

    controller.start_bot()
    controller.start_automation_run("seq-1", selected_window_handle=7)

    assert created_worker["worker"].manual_finished_calls == 1


def test_controller_clears_queue_cache_when_bot_stops_and_unblocks_manual_runs(qtbot) -> None:
    from raidbot.desktop.controller import DesktopController

    storage = FakeStorage()
    worker_runner = FakeRunner()
    manual_runner = ImmediateRunner()
    created = {}

    def worker_factory(**kwargs):
        worker = FakeWorker(**kwargs)
        created["worker"] = worker
        return worker

    class RecordingRuntime:
        def __init__(self) -> None:
            self.run_calls = []

        def run_sequence(self, sequence, selected_window_handle):
            self.run_calls.append((sequence.id, selected_window_handle))
            from raidbot.desktop.automation.runner import RunResult

            return RunResult(status="completed", window_handle=selected_window_handle)

        def dry_run_step(self, sequence, step_index, selected_window_handle):
            raise AssertionError("dry run should not be called")

        def request_stop(self) -> None:
            return None

    runtime = RecordingRuntime()
    runners = iter([worker_runner, manual_runner])
    controller = DesktopController(
        storage=storage,
        config=build_config(auto_run_enabled=True, default_auto_sequence_id="seq-1"),
        worker_factory=worker_factory,
        runner_factory=lambda: next(runners),
        automation_runtime_probe=lambda: (True, None),
        automation_runtime_factory=lambda _emit_event: runtime,
    )
    controller._automation_sequences = [build_sequence()]
    errors = []
    controller.errorRaised.connect(errors.append)

    controller.start_bot()
    created["worker"].emit_event({"type": "automation_queue_state_changed", "state": "queued"})
    created["worker"].emit_event({"type": "automation_queue_length_changed", "length": 2})

    controller.start_automation_run("seq-1", selected_window_handle=7)
    assert errors == ["Automation queue owns the execution slot"]

    created["worker"].emit_event({"type": "bot_state_changed", "state": "stopped"})
    qtbot.waitUntil(lambda: controller._automation_queue_state == "idle")

    controller.start_automation_run("seq-1", selected_window_handle=7)

    assert runtime.run_calls == [("seq-1", 7)]


def test_controller_clears_default_auto_sequence_when_deleted(qtbot) -> None:
    from raidbot.desktop.controller import DesktopController

    storage = FakeStorage()
    controller = DesktopController(
        storage=storage,
        config=build_config(default_auto_sequence_id="seq-1"),
        worker_factory=lambda **kwargs: FakeWorker(**kwargs),
        runner_factory=lambda: FakeRunner(),
    )
    controller._automation_sequences = [build_sequence("seq-1"), build_sequence("seq-2")]
    configs = []
    controller.configChanged.connect(configs.append)
    sequence_changes = []
    controller.automationSequencesChanged.connect(sequence_changes.append)

    controller.delete_automation_sequence("seq-1")

    assert controller.config.default_auto_sequence_id is None
    assert storage.saved_configs[-1].default_auto_sequence_id is None
    assert configs[-1].default_auto_sequence_id is None
    assert [sequence.id for sequence in sequence_changes[-1]] == ["seq-2"]


def test_async_worker_runner_submit_returns_future(monkeypatch) -> None:
    from raidbot.desktop.controller import AsyncWorkerRunner

    runner = AsyncWorkerRunner()
    loop = object()
    submitted = {}

    def fake_run_coroutine_threadsafe(coro, current_loop):
        submitted["coroutine"] = coro
        submitted["loop"] = current_loop
        return "future"

    monkeypatch.setattr(
        "raidbot.desktop.controller.asyncio.run_coroutine_threadsafe",
        fake_run_coroutine_threadsafe,
    )
    runner._loop = loop

    future = runner.submit(lambda: None)

    submitted["coroutine"].close()

    assert future == "future"
    assert submitted["loop"] is loop


def test_controller_resets_automation_state_when_runtime_run_raises(qtbot) -> None:
    from raidbot.desktop.controller import DesktopController

    runtime = RaisingAutomationRuntime(RuntimeError("runtime boom"))
    controller = DesktopController(
        storage=FakeStorage(),
        config=build_config(),
        runner_factory=ImmediateRunner,
        automation_runtime_probe=lambda: (True, None),
        automation_runtime_factory=lambda _emit_event: runtime,
    )
    controller._automation_sequences = [build_sequence()]
    states = []
    events = []
    errors = []
    controller.automationRunStateChanged.connect(states.append)
    controller.automationRunEvent.connect(events.append)
    controller.errorRaised.connect(errors.append)

    controller.start_automation_run("seq-1", selected_window_handle=None)

    assert states == ["running", "idle"]
    assert errors == ["runtime boom"]
    assert events[-1] == {"type": "step_failed", "reason": "runtime_error"}


def test_automation_runtime_fails_closed_when_selected_window_handle_is_missing() -> None:
    from raidbot.desktop.controller import _AutomationRuntime

    runtime = _AutomationRuntime(
        emit_event=lambda _event: None,
        window_manager_factory=lambda: FakeAutomationWindowManager(windows=[]),
        capture_factory=lambda: object(),
        matcher_factory=lambda: object(),
        input_driver_factory=lambda: object(),
        sequence_runner_factory=FailIfCalledSequenceRunner,
    )

    result = runtime.run_sequence(build_sequence(), selected_window_handle=999)

    assert result.status == "failed"
    assert result.failure_reason == "target_window_not_found"
