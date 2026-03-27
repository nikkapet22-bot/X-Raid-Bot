from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from raidbot.desktop.models import (
    ActivityEntry,
    BotRuntimeState,
    DesktopAppConfig,
    DesktopAppState,
    TelegramConnectionState,
)


def test_default_base_dir_uses_appdata(monkeypatch) -> None:
    monkeypatch.setenv("APPDATA", r"C:\\Users\\tester\\AppData\\Roaming")

    from raidbot.desktop.storage import default_base_dir

    assert default_base_dir() == Path(r"C:\\Users\\tester\\AppData\\Roaming") / "RaidBot"


def test_storage_reports_first_run_when_config_missing(tmp_path) -> None:
    from raidbot.desktop.storage import DesktopStorage

    storage = DesktopStorage(tmp_path)

    assert storage.is_first_run() is True


def test_config_round_trip(tmp_path) -> None:
    from raidbot.desktop.storage import DesktopStorage

    storage = DesktopStorage(tmp_path)
    config = DesktopAppConfig(
        telegram_api_id=123456,
        telegram_api_hash="api-hash",
        telegram_session_path=Path("sessions/raid.session"),
        telegram_phone_number="+15555550123",
        whitelisted_chat_ids=[1001, 1002, 1003],
        raidar_sender_id=424242,
        chrome_profile_directory="Profile 1",
    )

    storage.save_config(config)

    loaded = storage.load_config()

    assert loaded == config
    assert storage.is_first_run() is False
    assert storage.config_path.exists()


def test_state_round_trip_includes_activity_entries(tmp_path) -> None:
    from raidbot.desktop.storage import DesktopStorage

    storage = DesktopStorage(tmp_path)
    timestamp = datetime(2026, 3, 26, 12, 45, 0)
    state = DesktopAppState(
        bot_state=BotRuntimeState.stopped,
        connection_state=TelegramConnectionState.disconnected,
        raids_opened=7,
        duplicates_skipped=2,
        non_matching_skipped=5,
        open_failures=1,
        last_successful_raid_open_at="2026-03-26T12:45:00",
        activity=[
            ActivityEntry(
                timestamp=timestamp,
                action="opened_raid",
                url="https://x.com/i/status/123",
                reason="matched active raid",
            )
        ],
        last_error="boom",
    )

    storage.save_state(state)

    loaded = storage.load_state()

    assert loaded == state
    assert loaded.activity[0].timestamp == timestamp
    assert loaded.activity[0].action == "opened_raid"
    assert loaded.activity[0].url == "https://x.com/i/status/123"
    assert loaded.activity[0].reason == "matched active raid"
    assert storage.state_path.exists()


def test_load_state_normalizes_stale_live_runtime_states(tmp_path) -> None:
    from raidbot.desktop.storage import DesktopStorage

    storage = DesktopStorage(tmp_path)
    state = DesktopAppState(
        bot_state=BotRuntimeState.starting,
        connection_state=TelegramConnectionState.connecting,
    )

    storage.save_state(state)

    loaded = storage.load_state()

    assert loaded.bot_state is BotRuntimeState.stopped
    assert loaded.connection_state is TelegramConnectionState.disconnected
    assert json.loads(storage.state_path.read_text(encoding="utf-8"))["bot_state"] == "stopped"
    assert json.loads(storage.state_path.read_text(encoding="utf-8"))["connection_state"] == "disconnected"


def test_activity_history_is_capped_to_200_entries(tmp_path) -> None:
    from raidbot.desktop.storage import DesktopStorage

    storage = DesktopStorage(tmp_path)
    base_timestamp = datetime(2026, 3, 26, 12, 0, 0)
    activity = [
        ActivityEntry(
            timestamp=base_timestamp + timedelta(minutes=index),
            action=f"event-{index}",
            url=f"https://x.com/i/status/{index}",
            reason="raid event",
        )
        for index in range(205)
    ]
    state = DesktopAppState(activity=activity)

    storage.save_state(state)
    loaded = storage.load_state()

    assert len(loaded.activity) == 200
    assert [entry.action for entry in loaded.activity] == [
        f"event-{index}" for index in range(5, 205)
    ]
    assert loaded.activity[0].timestamp == base_timestamp + timedelta(minutes=5)
    assert loaded.activity[-1].timestamp == base_timestamp + timedelta(minutes=204)
