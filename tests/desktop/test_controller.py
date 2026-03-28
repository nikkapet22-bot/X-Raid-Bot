from __future__ import annotations

import os
import threading
from pathlib import Path
from concurrent.futures import Future

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from raidbot.desktop.automation.models import AutomationSequence, AutomationStep
from raidbot.desktop.models import DesktopAppConfig


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


def build_config(**overrides) -> DesktopAppConfig:
    values = {
        "telegram_api_id": 123456,
        "telegram_api_hash": "hash-value",
        "telegram_session_path": Path("raidbot.session"),
        "telegram_phone_number": "+40123456789",
        "whitelisted_chat_ids": [-1001],
        "allowed_sender_ids": [42],
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
        chrome_profile_directory="Profile 9",
    )

    controller.apply_config(new_config)

    assert storage.saved_configs == [new_config]
    assert controller.config == new_config
    assert len(runner.submitted_coroutines) == 1


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
