from __future__ import annotations

import os
import threading
from pathlib import Path
from concurrent.futures import Future

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

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

    async def run(self) -> None:
        self.run_calls += 1

    async def stop(self) -> None:
        self.stop_calls += 1

    async def apply_config(self, config: DesktopAppConfig) -> None:
        self.config = config
        self.apply_calls.append(config)


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
