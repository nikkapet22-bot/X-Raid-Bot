from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from pathlib import Path

import pytest

from raidbot.models import IncomingMessage
from raidbot.desktop.models import (
    ActivityEntry,
    BotRuntimeState,
    DesktopAppConfig,
    DesktopAppState,
    TelegramConnectionState,
)


class FakeStorage:
    def __init__(self, initial_state: DesktopAppState | None = None) -> None:
        self.initial_state = initial_state or DesktopAppState()
        self.saved_states: list[DesktopAppState] = []

    def load_state(self) -> DesktopAppState:
        return deepcopy(self.initial_state)

    def save_state(self, state: DesktopAppState) -> None:
        self.saved_states.append(deepcopy(state))


class FakeOpener:
    def __init__(self, profile_directory: str) -> None:
        self.profile_directory = profile_directory


class FakeService:
    def __init__(self, config: DesktopAppConfig) -> None:
        self.allowed_chat_ids = set(config.whitelisted_chat_ids)
        self.allowed_sender_id = config.raidar_sender_id
        self.opener = FakeOpener(config.chrome_profile_directory)


class FakeListener:
    def __init__(self, on_connection_state_change=None) -> None:
        self.on_connection_state_change = on_connection_state_change
        self.stop_calls = 0
        self.run_calls = 0

    async def run_forever(self) -> None:
        self.run_calls += 1
        if self.on_connection_state_change is not None:
            self.on_connection_state_change("connecting")
            self.on_connection_state_change("connected")
            self.on_connection_state_change("disconnected")

    async def stop(self) -> None:
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


def build_worker(storage: FakeStorage, events: list[dict], now: datetime):
    from raidbot.desktop.worker import DesktopBotWorker

    created_services = []
    created_listeners = []

    def service_factory(config: DesktopAppConfig) -> FakeService:
        service = FakeService(config)
        created_services.append(service)
        return service

    def listener_factory(**kwargs) -> FakeListener:
        listener = FakeListener(
            on_connection_state_change=kwargs.get("on_connection_state_change")
        )
        created_listeners.append(listener)
        return listener

    worker = DesktopBotWorker(
        config=build_config(),
        storage=storage,
        emit_event=events.append,
        service_factory=service_factory,
        listener_factory=listener_factory,
        now=lambda: now,
    )
    return worker, created_services, created_listeners


def build_default_worker(
    storage: FakeStorage,
    events: list[dict],
    now: datetime,
    *,
    chrome_environment_factory,
    listener_factory=None,
):
    from raidbot.desktop.worker import DesktopBotWorker

    return DesktopBotWorker(
        config=build_config(),
        storage=storage,
        emit_event=events.append,
        chrome_environment_factory=chrome_environment_factory,
        listener_factory=listener_factory or (lambda **kwargs: FakeListener()),
        now=lambda: now,
    )


def test_worker_records_opened_raid_and_updates_stats() -> None:
    events: list[dict] = []
    timestamp = datetime(2026, 3, 26, 12, 0, 0)
    storage = FakeStorage()
    worker, _services, _listeners = build_worker(storage, events, timestamp)

    worker._record_service_outcome("opened", "raid_opened", "https://x.com/i/status/123")

    assert worker.state.raids_opened == 1
    assert worker.state.last_successful_raid_open_at == "2026-03-26T12:00:00"
    assert worker.state.activity[-1] == ActivityEntry(
        timestamp=timestamp,
        action="opened",
        url="https://x.com/i/status/123",
        reason="raid_opened",
    )
    assert storage.saved_states[-1].raids_opened == 1
    assert [event["type"] for event in events] == ["stats_changed", "activity_added"]


def test_worker_preserves_dedupe_across_service_rebuilds(monkeypatch: pytest.MonkeyPatch) -> None:
    import raidbot.desktop.worker as worker_module

    opened_urls: list[str] = []
    timestamp = datetime(2026, 3, 26, 12, 1, 0)
    events: list[dict] = []
    storage = FakeStorage()

    class RecordingChromeOpener:
        def __init__(self, *, profile_directory: str, **_kwargs) -> None:
            self.profile_directory = profile_directory

        def open(self, url: str) -> None:
            opened_urls.append(url)

    class FakeChromeEnvironment:
        chrome_path = Path(r"C:\Chrome\chrome.exe")
        user_data_dir = Path(r"C:\Chrome\User Data")

    monkeypatch.setattr(worker_module, "ChromeOpener", RecordingChromeOpener)
    worker = build_default_worker(
        storage,
        events,
        timestamp,
        chrome_environment_factory=lambda: FakeChromeEnvironment(),
    )
    message = IncomingMessage(
        chat_id=-1001,
        sender_id=42,
        text="Likes 10 | 8 [%]\n\nhttps://x.com/i/status/123",
    )

    worker._service = worker._build_service(worker.config)
    first_outcome = worker._handle_message(message)
    worker._service = worker._build_service(worker.config)
    second_outcome = worker._handle_message(message)

    assert first_outcome.action == "opened"
    assert second_outcome.reason == "duplicate"
    assert opened_urls == ["https://x.com/i/status/123"]
    assert worker.state.duplicates_skipped == 1


def test_worker_loads_persisted_state_and_saves_updates() -> None:
    events: list[dict] = []
    timestamp = datetime(2026, 3, 26, 12, 5, 0)
    storage = FakeStorage(
        DesktopAppState(
            raids_opened=4,
            activity=[
                ActivityEntry(
                    timestamp=datetime(2026, 3, 26, 11, 55, 0),
                    action="opened",
                    url="https://x.com/i/status/100",
                    reason="raid_opened",
                )
            ],
        )
    )
    worker, _services, _listeners = build_worker(storage, events, timestamp)

    worker._record_service_outcome("skipped", "duplicate", "https://x.com/i/status/100")

    assert worker.state.raids_opened == 4
    assert worker.state.duplicates_skipped == 1
    assert len(worker.state.activity) == 2
    assert storage.saved_states[-1].duplicates_skipped == 1


def test_worker_records_skipped_outcomes_without_entering_error_state() -> None:
    events: list[dict] = []
    timestamp = datetime(2026, 3, 26, 12, 7, 0)
    storage = FakeStorage()
    worker, _services, _listeners = build_worker(storage, events, timestamp)

    worker.state.bot_state = BotRuntimeState.running
    worker._record_service_outcome("skipped", "duplicate", "https://x.com/i/status/100")
    worker._record_service_outcome("skipped", "not_a_raid", None)
    worker._record_service_outcome("skipped", "open_failed", "https://x.com/i/status/200")

    assert worker.state.duplicates_skipped == 1
    assert worker.state.non_matching_skipped == 1
    assert worker.state.open_failures == 1
    assert worker.state.bot_state is BotRuntimeState.running
    assert worker.state.last_error == "open_failed"
    assert [entry.reason for entry in worker.state.activity] == [
        "duplicate",
        "not_a_raid",
        "open_failed",
    ]
    assert [event["type"] for event in events] == [
        "stats_changed",
        "activity_added",
        "stats_changed",
        "activity_added",
        "stats_changed",
        "activity_added",
        "error",
    ]


@pytest.mark.asyncio
async def test_worker_run_emits_state_changes_and_stop_uses_listener() -> None:
    from raidbot.desktop.worker import DesktopBotWorker

    events: list[dict] = []
    timestamp = datetime(2026, 3, 26, 12, 10, 0)
    storage = FakeStorage()
    listener = FakeListener()

    worker = DesktopBotWorker(
        config=build_config(),
        storage=storage,
        emit_event=events.append,
        service_factory=lambda config: FakeService(config),
        listener_factory=lambda **kwargs: listener,
        now=lambda: timestamp,
    )

    await worker.run()
    await worker.stop()

    assert listener.run_calls == 1
    assert listener.stop_calls == 1
    assert worker.state.bot_state is BotRuntimeState.stopped
    assert worker.state.connection_state is TelegramConnectionState.disconnected
    assert storage.saved_states[-1].bot_state is BotRuntimeState.stopped
    assert [event["type"] for event in events[:4]] == [
        "bot_state_changed",
        "connection_state_changed",
        "connection_state_changed",
        "bot_state_changed",
    ]
    assert "connection_state_changed" in [event["type"] for event in events]


@pytest.mark.asyncio
async def test_worker_apply_config_updates_live_fields_without_restart() -> None:
    events: list[dict] = []
    timestamp = datetime(2026, 3, 26, 12, 15, 0)
    storage = FakeStorage()
    worker, created_services, created_listeners = build_worker(storage, events, timestamp)

    worker._service = FakeService(worker.config)
    worker._listener = FakeListener()
    new_config = build_config(
        whitelisted_chat_ids=[-1001, -2002],
        raidar_sender_id=99,
        chrome_profile_directory="Profile 9",
    )

    await worker.apply_config(new_config)

    assert worker.config == new_config
    assert worker._service.allowed_chat_ids == {-1001, -2002}
    assert worker._service.allowed_sender_id == 99
    assert worker._service.opener.profile_directory == "Profile 9"
    assert worker._listener.stop_calls == 0
    assert created_services == []
    assert created_listeners == []


@pytest.mark.asyncio
async def test_worker_apply_config_requests_restart_for_telegram_changes() -> None:
    events: list[dict] = []
    timestamp = datetime(2026, 3, 26, 12, 20, 0)
    storage = FakeStorage()
    worker, _services, _listeners = build_worker(storage, events, timestamp)

    worker._service = FakeService(worker.config)
    worker._listener = FakeListener()
    new_config = build_config(telegram_api_hash="new-hash")

    await worker.apply_config(new_config)

    assert worker.config == new_config
    assert worker._restart_requested is True
    assert worker._listener.stop_calls == 1


@pytest.mark.asyncio
async def test_worker_run_sets_stopped_state_when_listener_exits_normally() -> None:
    from raidbot.desktop.worker import DesktopBotWorker

    events: list[dict] = []
    timestamp = datetime(2026, 3, 26, 12, 25, 0)
    storage = FakeStorage()
    listener = FakeListener()

    worker = DesktopBotWorker(
        config=build_config(),
        storage=storage,
        emit_event=events.append,
        service_factory=lambda config: FakeService(config),
        listener_factory=lambda **kwargs: listener,
        now=lambda: timestamp,
    )

    await worker.run()

    assert worker.state.bot_state is BotRuntimeState.stopped
    assert worker.state.connection_state is TelegramConnectionState.disconnected
    assert events[-1] == {"type": "bot_state_changed", "state": "stopped"}


@pytest.mark.asyncio
async def test_worker_run_reports_startup_service_build_failures_as_error_state() -> None:
    from raidbot.desktop.worker import DesktopBotWorker

    events: list[dict] = []
    timestamp = datetime(2026, 3, 26, 12, 30, 0)
    storage = FakeStorage()
    worker = DesktopBotWorker(
        config=build_config(),
        storage=storage,
        emit_event=events.append,
        service_factory=lambda _config: (_ for _ in ()).throw(RuntimeError("service boom")),
        listener_factory=lambda **kwargs: FakeListener(),
        now=lambda: timestamp,
    )

    with pytest.raises(RuntimeError, match="service boom"):
        await worker.run()

    assert worker.state.bot_state is BotRuntimeState.error
    assert worker.state.last_error == "service boom"
    assert storage.saved_states[-1].bot_state is BotRuntimeState.error
    assert events[-1] == {"type": "error", "message": "service boom"}


@pytest.mark.asyncio
async def test_worker_run_reports_startup_listener_build_failures_as_error_state() -> None:
    from raidbot.desktop.worker import DesktopBotWorker

    events: list[dict] = []
    timestamp = datetime(2026, 3, 26, 12, 35, 0)
    storage = FakeStorage()
    worker = DesktopBotWorker(
        config=build_config(),
        storage=storage,
        emit_event=events.append,
        service_factory=lambda config: FakeService(config),
        listener_factory=lambda **kwargs: (_ for _ in ()).throw(RuntimeError("listener boom")),
        now=lambda: timestamp,
    )

    with pytest.raises(RuntimeError, match="listener boom"):
        await worker.run()

    assert worker.state.bot_state is BotRuntimeState.error
    assert worker.state.last_error == "listener boom"
    assert storage.saved_states[-1].bot_state is BotRuntimeState.error
    assert events[-1] == {"type": "error", "message": "listener boom"}


def test_worker_ignores_messages_after_stop_is_requested() -> None:
    from raidbot.desktop.worker import DesktopBotWorker

    events: list[dict] = []
    timestamp = datetime(2026, 3, 27, 9, 0, 0)
    storage = FakeStorage()
    handled_messages: list[IncomingMessage] = []

    class CountingService:
        def __init__(self, config: DesktopAppConfig) -> None:
            self.allowed_chat_ids = set(config.whitelisted_chat_ids)
            self.allowed_sender_id = config.raidar_sender_id
            self.opener = FakeOpener(config.chrome_profile_directory)

        def handle_message(self, message: IncomingMessage):
            handled_messages.append(message)
            raise AssertionError("service should not receive messages after stop is requested")

    worker = DesktopBotWorker(
        config=build_config(),
        storage=storage,
        emit_event=events.append,
        service_factory=lambda config: CountingService(config),
        listener_factory=lambda **kwargs: FakeListener(),
        now=lambda: timestamp,
    )
    worker._service = CountingService(worker.config)
    worker._stop_requested = True
    worker.state.bot_state = BotRuntimeState.stopped
    message = IncomingMessage(
        chat_id=-1001,
        sender_id=42,
        text="Likes 10 | 8 [%]\n\nhttps://x.com/i/status/123",
    )

    outcome = worker._handle_message(message)

    assert outcome.action == "ignored"
    assert outcome.reason == "bot_inactive"
    assert handled_messages == []
    assert events == []
    assert storage.saved_states == []
