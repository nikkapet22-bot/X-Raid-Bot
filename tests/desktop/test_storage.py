from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from raidbot.desktop.models import (
    BotActionSlotConfig,
    BotActionPreset,
    ActivityEntry,
    BotRuntimeState,
    DesktopAppConfig,
    DesktopAppState,
    TelegramConnectionState,
    default_bot_action_slots,
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
        allowed_sender_ids=[424242, 515151],
        allowed_sender_entries=("@raidar", "@delugeraidbot"),
        chrome_profile_directory="Profile 1",
        browser_mode="launch-only",
        executor_name="noop",
        preset_replies=("gm", "lfggg"),
        default_action_like=True,
        default_action_repost=False,
        default_action_bookmark=True,
        default_action_reply=False,
        auto_run_enabled=True,
        default_auto_sequence_id="seq-1",
        auto_run_settle_ms=2750,
        bot_action_slots=(
            BotActionSlotConfig(key="slot_1_r", label="R", enabled=True),
            BotActionSlotConfig(
                key="slot_2_l",
                label="L",
                enabled=True,
                template_path=Path("templates/slot-2.png"),
                updated_at="2026-03-28T12:00:00",
            ),
            BotActionSlotConfig(key="slot_3_r", label="R", enabled=False),
            BotActionSlotConfig(key="slot_4_b", label="B", enabled=True),
        ),
    )

    storage.save_config(config)

    loaded = storage.load_config()

    assert loaded == config
    assert storage.is_first_run() is False
    assert storage.config_path.exists()
    assert loaded.auto_run_settle_ms == 2750
    assert loaded.bot_action_slots == (
        BotActionSlotConfig(key="slot_1_r", label="R", enabled=True),
        BotActionSlotConfig(
            key="slot_2_l",
            label="L",
            enabled=True,
            template_path=Path("templates/slot-2.png"),
            updated_at="2026-03-28T12:00:00",
        ),
        BotActionSlotConfig(key="slot_3_r", label="R", enabled=False),
        BotActionSlotConfig(key="slot_4_b", label="B", enabled=True),
    )


def test_storage_round_trips_slot_1_presets_and_finish_template(tmp_path) -> None:
    from raidbot.desktop.storage import DesktopStorage

    storage = DesktopStorage(tmp_path)
    config = DesktopAppConfig(
        telegram_api_id=123456,
        telegram_api_hash="api-hash",
        telegram_session_path=Path("sessions/raid.session"),
        telegram_phone_number="+15555550123",
        whitelisted_chat_ids=[1001],
        allowed_sender_ids=[424242],
        allowed_sender_entries=("@raidar",),
        chrome_profile_directory="Profile 1",
        bot_action_slots=(
            BotActionSlotConfig(
                key="slot_1_r",
                label="R",
                enabled=True,
                template_path=Path("bot_actions/slot_1_r.png"),
                finish_template_path=Path("bot_actions/slot_1_r_finish.png"),
                presets=(
                    BotActionPreset(
                        id="preset-1",
                        text="gm",
                        image_path=Path("bot_actions/presets/gm.png"),
                    ),
                    BotActionPreset(
                        id="preset-2",
                        text="wagmi",
                    ),
                ),
            ),
            *default_bot_action_slots()[1:],
        ),
    )

    storage.save_config(config)

    loaded = storage.load_config()

    assert loaded.bot_action_slots[0].presets == config.bot_action_slots[0].presets
    assert loaded.bot_action_slots[0].finish_template_path == Path(
        "bot_actions/slot_1_r_finish.png"
    )


def test_storage_round_trips_slot_1_second_finish_template(tmp_path) -> None:
    from raidbot.desktop.storage import DesktopStorage

    storage = DesktopStorage(tmp_path)
    config = DesktopAppConfig(
        telegram_api_id=123456,
        telegram_api_hash="api-hash",
        telegram_session_path=Path("sessions/raid.session"),
        telegram_phone_number="+15555550123",
        whitelisted_chat_ids=[1001],
        allowed_sender_ids=[424242],
        allowed_sender_entries=("@raidar",),
        chrome_profile_directory="Profile 1",
        bot_action_slots=(
            BotActionSlotConfig(
                key="slot_1_r",
                label="R",
                enabled=True,
                template_path=Path("bot_actions/slot_1_r.png"),
                finish_template_path=Path("bot_actions/slot_1_r_finish.png"),
                finish_template_path_2=Path("bot_actions/slot_1_r_finish_2.png"),
                presets=(
                    BotActionPreset(
                        id="preset-1",
                        text="gm",
                    ),
                ),
            ),
            *default_bot_action_slots()[1:],
        ),
    )

    storage.save_config(config)

    loaded = storage.load_config()

    assert loaded.bot_action_slots[0].finish_template_path_2 == Path(
        "bot_actions/slot_1_r_finish_2.png"
    )


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
        sender_rejected=4,
        browser_session_failed=3,
        page_ready=6,
        executor_not_configured=2,
        executor_succeeded=1,
        executor_failed=5,
        session_closed=6,
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


def test_storage_loads_legacy_single_sender_as_allowlist(tmp_path) -> None:
    from raidbot.desktop.storage import DesktopStorage

    storage = DesktopStorage(tmp_path)
    storage.config_path.write_text(
        json.dumps(
            {
                "telegram_api_id": 123456,
                "telegram_api_hash": "api-hash",
                "telegram_session_path": "sessions/raid.session",
                "telegram_phone_number": "+15555550123",
                "whitelisted_chat_ids": [1001, 1002],
                "raidar_sender_id": 424242,
                "chrome_profile_directory": "Profile 1",
            }
        ),
        encoding="utf-8",
    )

    loaded = storage.load_config()

    assert loaded.allowed_sender_ids == [424242]
    assert loaded.browser_mode == "launch-only"
    assert loaded.executor_name == "noop"
    assert loaded.preset_replies == ()
    assert loaded.default_action_like is True
    assert loaded.default_action_repost is True
    assert loaded.default_action_bookmark is False
    assert loaded.default_action_reply is True
    assert loaded.auto_run_enabled is False
    assert loaded.default_auto_sequence_id is None
    assert loaded.auto_run_settle_ms == 1500
    assert loaded.allowed_sender_entries == ("424242",)


def test_storage_loads_sender_entries_when_present(tmp_path) -> None:
    from raidbot.desktop.storage import DesktopStorage

    storage = DesktopStorage(tmp_path)
    storage.config_path.write_text(
        json.dumps(
            {
                "telegram_api_id": 123456,
                "telegram_api_hash": "api-hash",
                "telegram_session_path": "sessions/raid.session",
                "telegram_phone_number": "+15555550123",
                "whitelisted_chat_ids": [1001, 1002],
                "allowed_sender_ids": [424242, 515151],
                "allowed_sender_entries": ["@raidar", "@delugeraidbot"],
                "chrome_profile_directory": "Profile 1",
            }
        ),
        encoding="utf-8",
    )

    loaded = storage.load_config()

    assert loaded.allowed_sender_ids == [424242, 515151]
    assert loaded.allowed_sender_entries == ("@raidar", "@delugeraidbot")


def test_storage_loads_legacy_bot_action_slots_as_disabled_defaults(tmp_path) -> None:
    from raidbot.desktop.storage import DesktopStorage

    storage = DesktopStorage(tmp_path)
    storage.config_path.write_text(
        json.dumps(
            {
                "telegram_api_id": 123456,
                "telegram_api_hash": "api-hash",
                "telegram_session_path": "sessions/raid.session",
                "telegram_phone_number": "+15555550123",
                "whitelisted_chat_ids": [1001, 1002],
                "allowed_sender_ids": [424242],
                "allowed_sender_entries": ["@raidar"],
                "chrome_profile_directory": "Profile 1",
                "auto_run_settle_ms": 1800,
            }
        ),
        encoding="utf-8",
    )

    loaded = storage.load_config()

    assert loaded.auto_run_settle_ms == 1800
    assert loaded.bot_action_slots == default_bot_action_slots()
    assert all(slot.enabled is False for slot in loaded.bot_action_slots)
    assert all(slot.template_path is None for slot in loaded.bot_action_slots)
    assert all(slot.updated_at is None for slot in loaded.bot_action_slots)


def test_storage_normalizes_malformed_bot_action_slots_to_fixed_layout(tmp_path) -> None:
    from raidbot.desktop.storage import DesktopStorage

    storage = DesktopStorage(tmp_path)
    storage.config_path.write_text(
        json.dumps(
            {
                "telegram_api_id": 123456,
                "telegram_api_hash": "api-hash",
                "telegram_session_path": "sessions/raid.session",
                "telegram_phone_number": "+15555550123",
                "whitelisted_chat_ids": [1001, 1002],
                "allowed_sender_ids": [424242],
                "allowed_sender_entries": ["@raidar"],
                "chrome_profile_directory": "Profile 1",
                "auto_run_settle_ms": 1800,
                "bot_action_slots": [
                    {
                        "key": "wrong-1",
                        "label": "X",
                        "enabled": True,
                        "template_path": "templates/slot-1.png",
                        "updated_at": "2026-03-28T12:00:00",
                    },
                    {
                        "enabled": False,
                        "template_path": "templates/slot-2.png",
                        "updated_at": "2026-03-28T12:01:00",
                    },
                    {
                        "key": "wrong-3",
                        "label": "Z",
                        "enabled": True,
                    },
                    {
                        "key": "wrong-4",
                        "label": "Q",
                        "enabled": True,
                        "template_path": "templates/slot-4.png",
                    },
                    {
                        "key": "wrong-5",
                        "label": "IGNORED",
                        "enabled": True,
                        "template_path": "templates/slot-5.png",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    loaded = storage.load_config()

    assert loaded.bot_action_slots == (
        BotActionSlotConfig(
            key="slot_1_r",
            label="R",
            enabled=True,
            template_path=Path("templates/slot-1.png"),
            updated_at="2026-03-28T12:00:00",
        ),
        BotActionSlotConfig(
            key="slot_2_l",
            label="L",
            enabled=False,
            template_path=Path("templates/slot-2.png"),
            updated_at="2026-03-28T12:01:00",
        ),
        BotActionSlotConfig(
            key="slot_3_r",
            label="R",
            enabled=True,
        ),
        BotActionSlotConfig(
            key="slot_4_b",
            label="B",
            enabled=True,
            template_path=Path("templates/slot-4.png"),
        ),
    )


def test_storage_load_state_defaults_new_pipeline_counters_to_zero(tmp_path) -> None:
    from raidbot.desktop.storage import DesktopStorage

    storage = DesktopStorage(tmp_path)
    storage.state_path.write_text(
        json.dumps(
            {
                "bot_state": "stopped",
                "connection_state": "disconnected",
                "raids_opened": 7,
                "duplicates_skipped": 2,
                "non_matching_skipped": 5,
                "open_failures": 1,
            }
        ),
        encoding="utf-8",
    )

    loaded = storage.load_state()

    assert loaded.raids_opened == 7
    assert loaded.duplicates_skipped == 2
    assert loaded.non_matching_skipped == 5
    assert loaded.open_failures == 1
    assert loaded.sender_rejected == 0
    assert loaded.browser_session_failed == 0
    assert loaded.page_ready == 0
    assert loaded.executor_not_configured == 0
    assert loaded.executor_succeeded == 0
    assert loaded.executor_failed == 0
    assert loaded.session_closed == 0
    assert loaded.automation_queue_state == "idle"
    assert loaded.automation_queue_length == 0
    assert loaded.automation_current_url is None
    assert loaded.automation_last_error is None


def test_load_state_resets_stale_automation_queue_runtime_fields(tmp_path) -> None:
    from raidbot.desktop.storage import DesktopStorage

    storage = DesktopStorage(tmp_path)
    storage.state_path.write_text(
        json.dumps(
            {
                "bot_state": "stopped",
                "connection_state": "disconnected",
                "automation_queue_state": "running",
                "automation_queue_length": 4,
                "automation_current_url": "https://example.com/current",
                "automation_last_error": "queue boom",
            }
        ),
        encoding="utf-8",
    )

    loaded = storage.load_state()

    assert loaded.automation_queue_state == "idle"
    assert loaded.automation_queue_length == 0
    assert loaded.automation_current_url is None
    assert loaded.automation_last_error is None
    assert json.loads(storage.state_path.read_text(encoding="utf-8"))[
        "automation_queue_state"
    ] == "idle"
    assert json.loads(storage.state_path.read_text(encoding="utf-8"))[
        "automation_queue_length"
    ] == 0
    assert json.loads(storage.state_path.read_text(encoding="utf-8"))[
        "automation_current_url"
    ] is None
    assert json.loads(storage.state_path.read_text(encoding="utf-8"))[
        "automation_last_error"
    ] is None


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
