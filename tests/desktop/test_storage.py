from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from raidbot.desktop.models import (
    BotActionSlotConfig,
    BotActionPreset,
    ActivityEntry,
    BotRuntimeState,
    DashboardMetricResetState,
    DesktopAppConfig,
    DesktopAppState,
    RaidProfileConfig,
    RaidProfileState,
    SuccessfulProfileRun,
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


def test_storage_round_trips_raid_profiles_in_order(tmp_path) -> None:
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
        chrome_profile_directory="Default",
        raid_profiles=(
            RaidProfileConfig(
                profile_directory="Default",
                label="George",
                enabled=True,
                raid_on_restart=False,
                reply_enabled=True,
                like_enabled=False,
                repost_enabled=True,
                bookmark_enabled=False,
            ),
            RaidProfileConfig(
                profile_directory="Profile 3",
                label="Maria",
                enabled=False,
                raid_on_restart=True,
                reply_enabled=False,
                like_enabled=True,
                repost_enabled=False,
                bookmark_enabled=True,
            ),
        ),
    )

    storage.save_config(config)

    loaded = storage.load_config()

    assert loaded.raid_profiles == (
        RaidProfileConfig(
            profile_directory="Default",
            label="George",
            enabled=True,
            raid_on_restart=False,
            reply_enabled=True,
            like_enabled=False,
            repost_enabled=True,
            bookmark_enabled=False,
        ),
        RaidProfileConfig(
            profile_directory="Profile 3",
            label="Maria",
            enabled=False,
            raid_on_restart=True,
            reply_enabled=False,
            like_enabled=True,
            repost_enabled=False,
            bookmark_enabled=True,
        ),
    )


def test_storage_defaults_raid_profile_action_overrides_for_legacy_config(tmp_path) -> None:
    from raidbot.desktop.storage import DesktopStorage

    storage = DesktopStorage(tmp_path)
    storage.config_path.write_text(
        json.dumps(
            {
                "telegram_api_id": 123456,
                "telegram_api_hash": "api-hash",
                "telegram_session_path": "sessions/raid.session",
                "telegram_phone_number": "+15555550123",
                "whitelisted_chat_ids": [1001],
                "allowed_sender_ids": [424242],
                "allowed_sender_entries": ["@raidar"],
                "chrome_profile_directory": "Default",
                "raid_profiles": [
                    {
                        "profile_directory": "Default",
                        "label": "George",
                        "enabled": True,
                        "raid_on_restart": False,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    loaded = storage.load_config()

    assert loaded.raid_profiles == (
        RaidProfileConfig(
            profile_directory="Default",
            label="George",
            enabled=True,
            raid_on_restart=False,
            reply_enabled=True,
            like_enabled=True,
            repost_enabled=True,
            bookmark_enabled=True,
        ),
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


def test_storage_round_trips_slot_1_finish_template(tmp_path) -> None:
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
                    ),
                ),
            ),
            *default_bot_action_slots()[1:],
        ),
    )

    storage.save_config(config)

    loaded = storage.load_config()

    assert loaded.bot_action_slots[0].finish_template_path == Path(
        "bot_actions/slot_1_r_finish.png"
    )


def test_storage_round_trips_page_ready_template_path(tmp_path) -> None:
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
        page_ready_template_path=Path("bot_actions/page_ready.png"),
    )

    storage.save_config(config)

    loaded = storage.load_config()

    assert loaded.page_ready_template_path == Path("bot_actions/page_ready.png")


def test_state_round_trip_includes_activity_entries(tmp_path) -> None:
    from raidbot.desktop.storage import DesktopStorage

    storage = DesktopStorage(tmp_path)
    timestamp = datetime(2026, 3, 26, 12, 45, 0)
    state = DesktopAppState(
        bot_state=BotRuntimeState.stopped,
        connection_state=TelegramConnectionState.disconnected,
        raids_detected=9,
        raids_opened=7,
        raids_completed=3,
        raids_failed=2,
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


def test_state_round_trip_includes_successful_profile_runs(tmp_path) -> None:
    from raidbot.desktop.storage import DesktopStorage

    storage = DesktopStorage(tmp_path)
    timestamp = datetime(2026, 3, 26, 12, 45, 0)
    state = DesktopAppState(
        successful_profile_runs=[
            SuccessfulProfileRun(timestamp=timestamp, duration_seconds=3.0)
        ]
    )

    storage.save_state(state)

    loaded = storage.load_state()

    assert loaded.successful_profile_runs == [
        SuccessfulProfileRun(timestamp=timestamp, duration_seconds=3.0)
    ]


def test_storage_resets_legacy_successful_profile_metrics_once(tmp_path) -> None:
    from raidbot.desktop.storage import DesktopStorage

    storage = DesktopStorage(tmp_path)
    started_at = datetime.now().replace(microsecond=0) - timedelta(minutes=10)
    completed_at = started_at + timedelta(seconds=3)
    state = DesktopAppState(
        activity=[
            ActivityEntry(
                timestamp=started_at,
                action="automation_started",
                url="https://x.com/i/status/123",
                reason="automation_started",
                profile_directory="Default",
            ),
            ActivityEntry(
                timestamp=completed_at,
                action="automation_succeeded",
                url="https://x.com/i/status/123",
                reason="automation_succeeded",
                profile_directory="Default",
            ),
        ],
        successful_profile_runs=[
            SuccessfulProfileRun(timestamp=completed_at, duration_seconds=3.0)
        ],
        dashboard_metric_resets=DashboardMetricResetState(
            legacy_local_time_migrated=True,
            successful_profile_metrics_initialized=False,
        ),
    )

    storage.save_state(state)

    loaded = storage.load_state()

    assert loaded.successful_profile_runs == []
    assert loaded.dashboard_metric_resets.successful_profile_metrics_initialized is True


def test_storage_round_trips_dashboard_metric_reset_state(tmp_path) -> None:
    from raidbot.desktop.storage import DesktopStorage

    storage = DesktopStorage(tmp_path)
    reset_state = DashboardMetricResetState(
        avg_completion_reset_at=datetime(2026, 3, 31, 23, 15, 0),
        avg_raids_per_hour_reset_at=datetime(2026, 3, 31, 23, 20, 0),
        raids_completed_offset=14,
        raids_failed_offset=2,
        success_rate_completed_offset=14,
        success_rate_failed_offset=2,
        uptime_reset_at=datetime(2026, 3, 31, 23, 25, 0),
        legacy_local_time_migrated=True,
    )
    state = DesktopAppState(dashboard_metric_resets=reset_state)

    storage.save_state(state)

    loaded = storage.load_state()

    assert loaded.dashboard_metric_resets == reset_state


def test_storage_migrates_legacy_dashboard_timestamps_to_local_time_once(tmp_path) -> None:
    from raidbot.desktop.storage import DesktopStorage

    storage = DesktopStorage(tmp_path)
    legacy_activity_utc = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(
        minutes=10
    )
    legacy_last_successful_utc = legacy_activity_utc - timedelta(minutes=5)
    storage.save_config(
        DesktopAppConfig(
            telegram_api_id=123456,
            telegram_api_hash="api-hash",
            telegram_session_path=Path("sessions/raid.session"),
            telegram_phone_number="+15555550123",
            whitelisted_chat_ids=[1001],
            allowed_sender_ids=[424242],
            allowed_sender_entries=("@raidar",),
            chrome_profile_directory="Default",
        )
    )
    storage.state_path.write_text(
        json.dumps(
            {
                "bot_state": "stopped",
                "connection_state": "disconnected",
                "last_successful_raid_open_at": legacy_last_successful_utc.replace(
                    tzinfo=None
                ).isoformat(),
                "activity": [
                    {
                        "timestamp": legacy_activity_utc.replace(tzinfo=None).isoformat(),
                        "action": "automation_succeeded",
                        "url": "https://x.com/i/status/1",
                        "reason": "automation_succeeded",
                        "profile_directory": "Default",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    loaded = storage.load_state()
    expected_activity_timestamp = legacy_activity_utc.astimezone().replace(tzinfo=None)
    expected_last_successful = (
        legacy_last_successful_utc.astimezone().replace(tzinfo=None).isoformat()
    )

    assert loaded.dashboard_metric_resets.legacy_local_time_migrated is True
    assert loaded.activity[0].timestamp == expected_activity_timestamp
    assert loaded.last_successful_raid_open_at == expected_last_successful

    reloaded = storage.load_state()

    assert reloaded.activity[0].timestamp == expected_activity_timestamp
    assert reloaded.last_successful_raid_open_at == expected_last_successful


def test_storage_resets_corrupted_future_dashboard_history(tmp_path) -> None:
    from raidbot.desktop.storage import DesktopStorage

    storage = DesktopStorage(tmp_path)
    future_time = datetime.now() + timedelta(hours=2)
    state = DesktopAppState(
        raids_detected=9,
        raids_opened=7,
        raids_completed=31,
        raids_failed=3,
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
        last_successful_raid_open_at=future_time.isoformat(),
        activity=[
            ActivityEntry(
                timestamp=future_time,
                action="automation_succeeded",
                url="https://x.com/i/status/123",
                reason="automation_succeeded",
                profile_directory="Default",
            )
        ],
        last_error="boom",
        dashboard_metric_resets=DashboardMetricResetState(
            avg_completion_reset_at=future_time,
            avg_raids_per_hour_reset_at=future_time,
            raids_completed_offset=10,
            raids_failed_offset=1,
            success_rate_completed_offset=10,
            success_rate_failed_offset=1,
            uptime_reset_at=future_time,
            legacy_local_time_migrated=True,
        ),
    )

    storage.save_state(state)

    loaded = storage.load_state()

    assert loaded.raids_detected == 0
    assert loaded.raids_opened == 0
    assert loaded.raids_completed == 0
    assert loaded.raids_failed == 0
    assert loaded.activity == []
    assert loaded.last_successful_raid_open_at is None
    assert loaded.last_error is None
    assert loaded.dashboard_metric_resets == DashboardMetricResetState(
        legacy_local_time_migrated=True
    )


def test_storage_resets_legacy_per_profile_counter_baseline_once(tmp_path) -> None:
    from raidbot.desktop.storage import DesktopStorage

    storage = DesktopStorage(tmp_path)
    storage.save_config(
        DesktopAppConfig(
            telegram_api_id=123456,
            telegram_api_hash="api-hash",
            telegram_session_path=Path("sessions/raid.session"),
            telegram_phone_number="+15555550123",
            whitelisted_chat_ids=[1001],
            allowed_sender_ids=[424242],
            allowed_sender_entries=("@raidar",),
            chrome_profile_directory="Default",
        )
    )
    storage.state_path.write_text(
        json.dumps(
            {
                "bot_state": "stopped",
                "connection_state": "disconnected",
                "raids_completed": 14,
                "raids_failed": 3,
                "dashboard_metric_resets": {
                    "raids_completed_offset": 10,
                    "raids_failed_offset": 1,
                    "success_rate_completed_offset": 10,
                    "success_rate_failed_offset": 1,
                    "legacy_local_time_migrated": True,
                    "successful_profile_metrics_initialized": True,
                },
            }
        ),
        encoding="utf-8",
    )

    loaded = storage.load_state()

    assert loaded.raids_completed == 0
    assert loaded.raids_failed == 0
    assert loaded.dashboard_metric_resets.raids_completed_offset == 0
    assert loaded.dashboard_metric_resets.raids_failed_offset == 0
    assert loaded.dashboard_metric_resets.success_rate_completed_offset == 0
    assert loaded.dashboard_metric_resets.success_rate_failed_offset == 0
    assert loaded.dashboard_metric_resets.per_profile_outcome_counters_initialized is True

    reloaded = storage.load_state()

    assert reloaded.raids_completed == 0
    assert reloaded.raids_failed == 0
    assert (
        reloaded.dashboard_metric_resets.per_profile_outcome_counters_initialized is True
    )


def test_storage_round_trips_raid_profile_states(tmp_path) -> None:
    from raidbot.desktop.storage import DesktopStorage

    storage = DesktopStorage(tmp_path)
    state = DesktopAppState(
        raid_profile_states=(
            RaidProfileState(
                profile_directory="Default",
                label="George",
                status="green",
                last_error=None,
            ),
            RaidProfileState(
                profile_directory="Profile 3",
                label="Maria",
                status="red",
                last_error="not_logged_in",
            ),
        )
    )

    storage.save_state(state)

    loaded = storage.load_state()

    assert loaded.raid_profile_states == (
        RaidProfileState(
            profile_directory="Default",
            label="George",
            status="green",
            last_error=None,
        ),
        RaidProfileState(
            profile_directory="Profile 3",
            label="Maria",
            status="red",
            last_error="not_logged_in",
        ),
    )


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
    assert loaded.raid_profiles == (
        RaidProfileConfig(
            profile_directory="Profile 1",
            label="Profile 1",
            enabled=True,
        ),
    )


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


def test_storage_round_trips_slot_1_finish_delay_seconds(tmp_path) -> None:
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
        slot_1_finish_delay_seconds=4,
    )

    storage.save_config(config)

    loaded = storage.load_config()

    assert loaded.slot_1_finish_delay_seconds == 4


def test_storage_defaults_missing_slot_1_finish_delay_seconds_to_two(tmp_path) -> None:
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
            }
        ),
        encoding="utf-8",
    )

    loaded = storage.load_config()

    assert loaded.slot_1_finish_delay_seconds == 2


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
                "raids_detected": 6,
                "raids_opened": 7,
                "raids_completed": 4,
                "raids_failed": 1,
                "duplicates_skipped": 2,
                "non_matching_skipped": 5,
                "open_failures": 1,
            }
        ),
        encoding="utf-8",
    )

    loaded = storage.load_state()

    assert loaded.raids_detected == 6
    assert loaded.raids_opened == 7
    assert loaded.raids_completed == 4
    assert loaded.raids_failed == 1
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


def test_storage_round_trips_activity_profile_directory(tmp_path) -> None:
    from raidbot.desktop.storage import DesktopStorage

    storage = DesktopStorage(tmp_path)
    timestamp = datetime.now().replace(microsecond=0) - timedelta(minutes=10)
    state = DesktopAppState(
        activity=[
            ActivityEntry(
                timestamp=timestamp,
                action="automation_started",
                url="https://x.com/i/status/1",
                reason="automation_started",
                profile_directory="Profile 3",
            )
        ],
        dashboard_metric_resets=DashboardMetricResetState(
            legacy_local_time_migrated=True
        ),
    )

    storage.save_state(state)
    loaded = storage.load_state()

    assert loaded.activity[0].profile_directory == "Profile 3"


def test_storage_loads_legacy_activity_without_profile_directory(tmp_path) -> None:
    from raidbot.desktop.storage import DesktopStorage

    storage = DesktopStorage(tmp_path)
    timestamp = datetime.now().replace(microsecond=0) - timedelta(minutes=10)
    storage.state_path.write_text(
        json.dumps(
            {
                "bot_state": "stopped",
                "connection_state": "disconnected",
                "dashboard_metric_resets": {"legacy_local_time_migrated": True},
                "activity": [
                    {
                        "timestamp": timestamp.isoformat(),
                        "action": "automation_started",
                        "url": "https://x.com/i/status/1",
                        "reason": "automation_started",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    loaded = storage.load_state()

    assert loaded.activity[0].profile_directory is None
