from __future__ import annotations

from datetime import datetime
from pathlib import Path

from raidbot.desktop.models import (
    BotActionSlotConfig,
    ActivityEntry,
    BotRuntimeState,
    DesktopAppConfig,
    DesktopAppState,
    TelegramConnectionState,
    default_bot_action_slots,
)


def test_desktop_app_config_holds_required_values() -> None:
    config = DesktopAppConfig(
        telegram_api_id=123,
        telegram_api_hash="hash",
        telegram_session_path=Path("session.session"),
        telegram_phone_number="+15555550123",
        whitelisted_chat_ids=[111, 222],
        allowed_sender_ids=[333, 444],
        chrome_profile_directory="Default",
        browser_mode="launch-only",
        executor_name="noop",
        preset_replies=("gm", "lfg"),
        default_action_like=True,
        default_action_repost=False,
        default_action_bookmark=True,
        default_action_reply=False,
        auto_run_enabled=True,
        default_auto_sequence_id="seq-1",
        auto_run_settle_ms=1500,
        bot_action_slots=(
            BotActionSlotConfig(key="slot_1_r", label="R", enabled=True),
            BotActionSlotConfig(
                key="slot_2_l",
                label="L",
                enabled=False,
                template_path=Path("templates/l.png"),
                updated_at="2026-03-28T12:00:00",
            ),
            BotActionSlotConfig(key="slot_3_r", label="R"),
            BotActionSlotConfig(key="slot_4_b", label="B"),
        ),
    )

    assert config.telegram_api_id == 123
    assert config.telegram_api_hash == "hash"
    assert config.telegram_session_path == Path("session.session")
    assert config.telegram_phone_number == "+15555550123"
    assert config.whitelisted_chat_ids == [111, 222]
    assert config.allowed_sender_ids == [333, 444]
    assert config.chrome_profile_directory == "Default"
    assert config.browser_mode == "launch-only"
    assert config.executor_name == "noop"
    assert config.preset_replies == ("gm", "lfg")
    assert config.default_action_like is True
    assert config.default_action_repost is False
    assert config.default_action_bookmark is True
    assert config.default_action_reply is False
    assert config.auto_run_enabled is True
    assert config.default_auto_sequence_id == "seq-1"
    assert config.auto_run_settle_ms == 1500
    assert config.bot_action_slots == (
        BotActionSlotConfig(key="slot_1_r", label="R", enabled=True),
        BotActionSlotConfig(
            key="slot_2_l",
            label="L",
            enabled=False,
            template_path=Path("templates/l.png"),
            updated_at="2026-03-28T12:00:00",
        ),
        BotActionSlotConfig(key="slot_3_r", label="R"),
        BotActionSlotConfig(key="slot_4_b", label="B"),
    )


def test_desktop_app_config_uses_default_bot_action_slots_when_unspecified() -> None:
    config = DesktopAppConfig(
        telegram_api_id=123,
        telegram_api_hash="hash",
        telegram_session_path=Path("session.session"),
        telegram_phone_number=None,
        whitelisted_chat_ids=[111],
        allowed_sender_ids=[333],
        chrome_profile_directory="Default",
    )

    assert config.bot_action_slots == default_bot_action_slots()


def test_desktop_app_config_preserves_page_ready_template_path() -> None:
    config = DesktopAppConfig(
        telegram_api_id=123,
        telegram_api_hash="hash",
        telegram_session_path=Path("session.session"),
        telegram_phone_number=None,
        whitelisted_chat_ids=[111],
        allowed_sender_ids=[333],
        chrome_profile_directory="Default",
        page_ready_template_path=Path("bot_actions/page_ready.png"),
    )

    assert config.page_ready_template_path == Path("bot_actions/page_ready.png")


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
    assert state.raids_detected == 0
    assert state.raids_opened == 0
    assert state.raids_completed == 0
    assert state.raids_failed == 0
    assert state.sender_rejected == 0
    assert state.browser_session_failed == 0
    assert state.page_ready == 0
    assert state.executor_not_configured == 0
    assert state.executor_succeeded == 0
    assert state.executor_failed == 0
    assert state.session_closed == 0
    assert state.activity == []
    assert state.last_successful_raid_open_at is None
    assert state.automation_queue_state == "idle"
    assert state.automation_queue_length == 0
    assert state.automation_current_url is None
    assert state.automation_last_error is None


def test_desktop_app_config_exposes_legacy_sender_property_for_compatibility() -> None:
    config = DesktopAppConfig(
        telegram_api_id=123,
        telegram_api_hash="hash",
        telegram_session_path=Path("session.session"),
        telegram_phone_number=None,
        whitelisted_chat_ids=[111],
        allowed_sender_ids=[333, 444],
        chrome_profile_directory="Default",
    )

    assert config.raidar_sender_id == 333


def test_desktop_app_config_legacy_sender_property_is_none_for_empty_allowlist() -> None:
    config = DesktopAppConfig(
        telegram_api_id=123,
        telegram_api_hash="hash",
        telegram_session_path=Path("session.session"),
        telegram_phone_number=None,
        whitelisted_chat_ids=[111],
        allowed_sender_ids=[],
        chrome_profile_directory="Default",
    )

    assert config.raidar_sender_id is None


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
