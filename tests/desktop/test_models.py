from __future__ import annotations

from datetime import datetime
from pathlib import Path

from raidbot.desktop.models import (
    ActivityEntry,
    BotRuntimeState,
    DesktopAppConfig,
    DesktopAppState,
    TelegramConnectionState,
)


def test_desktop_app_config_holds_required_values() -> None:
    config = DesktopAppConfig(
        telegram_api_id=123,
        telegram_api_hash="hash",
        telegram_session_path=Path("session.session"),
        telegram_phone_number="+15555550123",
        whitelisted_chat_ids=[111, 222],
        raidar_sender_id=333,
        chrome_profile_directory="Default",
    )

    assert config.telegram_api_id == 123
    assert config.telegram_api_hash == "hash"
    assert config.telegram_session_path == Path("session.session")
    assert config.telegram_phone_number == "+15555550123"
    assert config.whitelisted_chat_ids == [111, 222]
    assert config.raidar_sender_id == 333
    assert config.chrome_profile_directory == "Default"


def test_desktop_model_enums_expose_expected_values() -> None:
    assert {member.value for member in BotRuntimeState} == {
        "setup_required",
        "stopped",
        "starting",
        "running",
        "stopping",
        "error",
    }
    assert {member.value for member in TelegramConnectionState} == {
        "disconnected",
        "connecting",
        "connected",
        "reconnecting",
        "auth_required",
    }


def test_desktop_app_state_defaults_are_stopped_and_disconnected() -> None:
    state = DesktopAppState()

    assert state.bot_state is BotRuntimeState.stopped
    assert state.connection_state is TelegramConnectionState.disconnected
    assert state.activity == []
    assert state.last_successful_raid_open_at is None


def test_activity_entry_stores_timestamp_and_reason() -> None:
    timestamp = datetime(2026, 3, 26, 12, 30, 45)
    entry = ActivityEntry(
        timestamp=timestamp,
        action="opened_raid",
        url="https://example.com/raid",
        reason="matched raid post",
    )

    assert entry.timestamp == timestamp
    assert entry.action == "opened_raid"
    assert entry.url == "https://example.com/raid"
    assert entry.reason == "matched raid post"
