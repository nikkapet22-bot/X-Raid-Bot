from __future__ import annotations

import json
import os
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .models import (
    ActivityEntry,
    BotActionPreset,
    BotActionSlotConfig,
    BotRuntimeState,
    DashboardMetricResetState,
    DesktopAppConfig,
    DesktopAppState,
    RaidProfileConfig,
    RaidProfileState,
    SuccessfulProfileRun,
    TelegramConnectionState,
)

_ACTIVITY_LIMIT = 200
_SUCCESSFUL_PROFILE_RUN_LIMIT = 5000


def default_base_dir() -> Path:
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "RaidBot"
    return Path.home() / "AppData" / "Roaming" / "RaidBot"


class DesktopStorage:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.config_path = base_dir / "config.json"
        self.state_path = base_dir / "state.json"
        self.automation_sequences_path = base_dir / "automation_sequences.json"

    def is_first_run(self) -> bool:
        return not self.config_path.exists()

    def save_config(self, config: DesktopAppConfig) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(
            json.dumps(self._config_to_data(config), indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def load_config(self) -> DesktopAppConfig:
        data = json.loads(self.config_path.read_text(encoding="utf-8"))
        return self._config_from_data(data)

    def save_state(self, state: DesktopAppState) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(
            json.dumps(self._state_to_data(state), indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def load_state(self) -> DesktopAppState:
        if not self.state_path.exists():
            return self._normalize_loaded_state(DesktopAppState())
        data = json.loads(self.state_path.read_text(encoding="utf-8"))
        state = self._state_from_data(data)
        normalized_state = self._normalize_loaded_state(state)
        if normalized_state != state:
            self.save_state(normalized_state)
        return normalized_state

    def _config_to_data(self, config: DesktopAppConfig) -> dict[str, Any]:
        return {
            "telegram_api_id": config.telegram_api_id,
            "telegram_api_hash": config.telegram_api_hash,
            "telegram_session_path": str(config.telegram_session_path),
            "telegram_phone_number": config.telegram_phone_number,
            "whitelisted_chat_ids": list(config.whitelisted_chat_ids),
            "allowed_sender_ids": list(config.allowed_sender_ids),
            "allowed_sender_entries": list(config.allowed_sender_entries),
            "chrome_profile_directory": config.chrome_profile_directory,
            "browser_mode": config.browser_mode,
            "executor_name": config.executor_name,
            "preset_replies": list(config.preset_replies),
            "default_action_like": config.default_action_like,
            "default_action_repost": config.default_action_repost,
            "default_action_bookmark": config.default_action_bookmark,
            "default_action_reply": config.default_action_reply,
            "auto_run_enabled": config.auto_run_enabled,
            "default_auto_sequence_id": config.default_auto_sequence_id,
            "auto_run_settle_ms": config.auto_run_settle_ms,
            "slot_1_finish_delay_seconds": config.slot_1_finish_delay_seconds,
            "page_ready_template_path": (
                str(config.page_ready_template_path)
                if config.page_ready_template_path is not None
                else None
            ),
            "bot_action_slots": [
                self._bot_action_slot_to_data(slot) for slot in config.bot_action_slots
            ],
            "raid_profiles": [
                self._raid_profile_config_to_data(profile) for profile in config.raid_profiles
            ],
        }

    def _config_from_data(self, data: dict[str, Any]) -> DesktopAppConfig:
        allowed_sender_ids = data.get("allowed_sender_ids")
        if allowed_sender_ids is None:
            legacy_sender_id = self._maybe_int(data.get("raidar_sender_id"))
            allowed_sender_ids = [] if legacy_sender_id is None else [legacy_sender_id]
        allowed_sender_entries = data.get("allowed_sender_entries")
        if allowed_sender_entries is None:
            allowed_sender_entries = [str(sender_id) for sender_id in allowed_sender_ids]
        bot_action_slots_data = data.get("bot_action_slots") or ()
        raid_profiles_data = data.get("raid_profiles") or ()
        return DesktopAppConfig(
            telegram_api_id=int(data["telegram_api_id"]),
            telegram_api_hash=str(data["telegram_api_hash"]),
            telegram_session_path=Path(data["telegram_session_path"]),
            telegram_phone_number=data.get("telegram_phone_number"),
            whitelisted_chat_ids=[int(chat_id) for chat_id in data["whitelisted_chat_ids"]],
            allowed_sender_ids=[int(sender_id) for sender_id in allowed_sender_ids],
            allowed_sender_entries=tuple(str(entry) for entry in allowed_sender_entries),
            chrome_profile_directory=str(data["chrome_profile_directory"]),
            browser_mode=str(data.get("browser_mode", "launch-only")),
            executor_name=str(data.get("executor_name", "noop")),
            preset_replies=tuple(str(reply) for reply in data.get("preset_replies", [])),
            default_action_like=self._maybe_bool(data.get("default_action_like"), default=True),
            default_action_repost=self._maybe_bool(
                data.get("default_action_repost"),
                default=True,
            ),
            default_action_bookmark=self._maybe_bool(
                data.get("default_action_bookmark"),
                default=False,
            ),
            default_action_reply=self._maybe_bool(data.get("default_action_reply"), default=True),
            auto_run_enabled=self._maybe_bool(data.get("auto_run_enabled"), default=False),
            default_auto_sequence_id=data.get("default_auto_sequence_id"),
            auto_run_settle_ms=(
                int(data["auto_run_settle_ms"])
                if data.get("auto_run_settle_ms") is not None
                else 1500
            ),
            slot_1_finish_delay_seconds=(
                int(data["slot_1_finish_delay_seconds"])
                if data.get("slot_1_finish_delay_seconds") is not None
                else 2
            ),
            page_ready_template_path=(
                Path(data["page_ready_template_path"])
                if data.get("page_ready_template_path") is not None
                else None
            ),
            bot_action_slots=tuple(
                self._bot_action_slot_from_data(slot_data)
                for slot_data in bot_action_slots_data
                if isinstance(slot_data, dict)
            ),
            raid_profiles=tuple(
                self._raid_profile_config_from_data(profile_data)
                for profile_data in raid_profiles_data
                if isinstance(profile_data, dict)
            ),
        )

    def _state_to_data(self, state: DesktopAppState) -> dict[str, Any]:
        activity = self._cap_activity(state.activity)
        successful_profile_runs = self._cap_successful_profile_runs(
            state.successful_profile_runs
        )
        return {
            "bot_state": state.bot_state.value,
            "connection_state": state.connection_state.value,
            "raids_detected": state.raids_detected,
            "raids_opened": state.raids_opened,
            "raids_completed": state.raids_completed,
            "raids_failed": state.raids_failed,
            "duplicates_skipped": state.duplicates_skipped,
            "non_matching_skipped": state.non_matching_skipped,
            "open_failures": state.open_failures,
            "sender_rejected": state.sender_rejected,
            "browser_session_failed": state.browser_session_failed,
            "page_ready": state.page_ready,
            "executor_not_configured": state.executor_not_configured,
            "executor_succeeded": state.executor_succeeded,
            "executor_failed": state.executor_failed,
            "session_closed": state.session_closed,
            "last_successful_raid_open_at": state.last_successful_raid_open_at,
            "activity": [self._activity_to_data(entry) for entry in activity],
            "successful_profile_runs": [
                self._successful_profile_run_to_data(entry)
                for entry in successful_profile_runs
            ],
            "last_error": state.last_error,
            "automation_queue_state": state.automation_queue_state,
            "automation_queue_length": state.automation_queue_length,
            "automation_current_url": state.automation_current_url,
            "automation_last_error": state.automation_last_error,
            "dashboard_metric_resets": self._dashboard_metric_resets_to_data(
                state.dashboard_metric_resets
            ),
            "raid_profile_states": [
                self._raid_profile_state_to_data(profile_state)
                for profile_state in state.raid_profile_states
            ],
        }

    def _state_from_data(self, data: dict[str, Any]) -> DesktopAppState:
        activity = [self._activity_from_data(item) for item in data.get("activity", [])]
        successful_profile_runs = [
            self._successful_profile_run_from_data(item)
            for item in data.get("successful_profile_runs", [])
            if isinstance(item, dict)
        ]
        return DesktopAppState(
            bot_state=BotRuntimeState(data.get("bot_state", BotRuntimeState.stopped.value)),
            connection_state=TelegramConnectionState(
                data.get("connection_state", TelegramConnectionState.disconnected.value)
            ),
            raids_detected=int(data.get("raids_detected", 0)),
            raids_opened=int(data.get("raids_opened", 0)),
            raids_completed=int(data.get("raids_completed", 0)),
            raids_failed=int(data.get("raids_failed", 0)),
            duplicates_skipped=int(data.get("duplicates_skipped", 0)),
            non_matching_skipped=int(data.get("non_matching_skipped", 0)),
            open_failures=int(data.get("open_failures", 0)),
            sender_rejected=int(data.get("sender_rejected", 0)),
            browser_session_failed=int(data.get("browser_session_failed", 0)),
            page_ready=int(data.get("page_ready", 0)),
            executor_not_configured=int(data.get("executor_not_configured", 0)),
            executor_succeeded=int(data.get("executor_succeeded", 0)),
            executor_failed=int(data.get("executor_failed", 0)),
            session_closed=int(data.get("session_closed", 0)),
            last_successful_raid_open_at=data.get("last_successful_raid_open_at"),
            activity=activity[-_ACTIVITY_LIMIT:],
            successful_profile_runs=successful_profile_runs[
                -_SUCCESSFUL_PROFILE_RUN_LIMIT:
            ],
            last_error=data.get("last_error"),
            automation_queue_state=str(data.get("automation_queue_state") or "idle"),
            automation_queue_length=(
                int(data["automation_queue_length"])
                if data.get("automation_queue_length") is not None
                else 0
            ),
            automation_current_url=data.get("automation_current_url"),
            automation_last_error=data.get("automation_last_error"),
            dashboard_metric_resets=self._dashboard_metric_resets_from_data(
                data.get("dashboard_metric_resets")
            ),
            raid_profile_states=tuple(
                self._raid_profile_state_from_data(profile_state)
                for profile_state in data.get("raid_profile_states", ())
                if isinstance(profile_state, dict)
            ),
        )

    def _normalize_loaded_state(self, state: DesktopAppState) -> DesktopAppState:
        config = self.load_config() if self.config_path.exists() else None
        state = self._migrate_legacy_dashboard_timestamps_to_local_time(state)
        state = self._reset_corrupted_future_dashboard_history(state)
        state = self._initialize_per_profile_outcome_counters(state)
        state = self._initialize_successful_profile_metrics(state)
        return replace(
            state,
            bot_state=self._normalize_bot_state(state.bot_state),
            connection_state=self._normalize_connection_state(state.connection_state),
            automation_queue_state="idle",
            automation_queue_length=0,
            automation_current_url=None,
            automation_last_error=None,
            raid_profile_states=self._normalize_raid_profile_states(
                state.raid_profile_states,
                config=config,
            ),
        )

    def _activity_to_data(self, entry: ActivityEntry) -> dict[str, Any]:
        return {
            "timestamp": entry.timestamp.isoformat(),
            "action": entry.action,
            "url": entry.url,
            "reason": entry.reason,
            "profile_directory": entry.profile_directory,
        }

    def _activity_from_data(self, data: dict[str, Any]) -> ActivityEntry:
        return ActivityEntry(
            timestamp=datetime.fromisoformat(str(data["timestamp"])),
            action=str(data["action"]),
            url=data.get("url"),
            reason=data.get("reason"),
            profile_directory=data.get("profile_directory"),
        )

    def _cap_activity(self, activity: list[ActivityEntry]) -> list[ActivityEntry]:
        return list(activity[-_ACTIVITY_LIMIT:])

    def _successful_profile_run_to_data(
        self,
        entry: SuccessfulProfileRun,
    ) -> dict[str, Any]:
        return {
            "timestamp": entry.timestamp.isoformat(),
            "duration_seconds": entry.duration_seconds,
        }

    def _successful_profile_run_from_data(
        self,
        data: dict[str, Any],
    ) -> SuccessfulProfileRun:
        return SuccessfulProfileRun(
            timestamp=datetime.fromisoformat(str(data["timestamp"])),
            duration_seconds=(
                float(data["duration_seconds"])
                if data.get("duration_seconds") is not None
                else None
            ),
        )

    def _cap_successful_profile_runs(
        self,
        successful_profile_runs: list[SuccessfulProfileRun],
    ) -> list[SuccessfulProfileRun]:
        return list(successful_profile_runs[-_SUCCESSFUL_PROFILE_RUN_LIMIT:])

    def _dashboard_metric_resets_to_data(
        self,
        resets: DashboardMetricResetState,
    ) -> dict[str, Any]:
        return {
            "avg_completion_reset_at": (
                resets.avg_completion_reset_at.isoformat()
                if resets.avg_completion_reset_at is not None
                else None
            ),
            "avg_raids_per_hour_reset_at": (
                resets.avg_raids_per_hour_reset_at.isoformat()
                if resets.avg_raids_per_hour_reset_at is not None
                else None
            ),
            "raids_completed_offset": resets.raids_completed_offset,
            "raids_failed_offset": resets.raids_failed_offset,
            "success_rate_completed_offset": resets.success_rate_completed_offset,
            "success_rate_failed_offset": resets.success_rate_failed_offset,
            "uptime_reset_at": (
                resets.uptime_reset_at.isoformat()
                if resets.uptime_reset_at is not None
                else None
            ),
            "legacy_local_time_migrated": bool(resets.legacy_local_time_migrated),
            "successful_profile_metrics_initialized": bool(
                resets.successful_profile_metrics_initialized
            ),
            "per_profile_outcome_counters_initialized": bool(
                resets.per_profile_outcome_counters_initialized
            ),
        }

    def _dashboard_metric_resets_from_data(
        self,
        data: Any,
    ) -> DashboardMetricResetState:
        if not isinstance(data, dict):
            return DashboardMetricResetState(
                legacy_local_time_migrated=False,
                successful_profile_metrics_initialized=False,
                per_profile_outcome_counters_initialized=False,
            )
        return DashboardMetricResetState(
            avg_completion_reset_at=self._maybe_datetime(
                data.get("avg_completion_reset_at")
            ),
            avg_raids_per_hour_reset_at=self._maybe_datetime(
                data.get("avg_raids_per_hour_reset_at")
            ),
            raids_completed_offset=int(data.get("raids_completed_offset", 0)),
            raids_failed_offset=int(data.get("raids_failed_offset", 0)),
            success_rate_completed_offset=int(
                data.get("success_rate_completed_offset", 0)
            ),
            success_rate_failed_offset=int(data.get("success_rate_failed_offset", 0)),
            uptime_reset_at=self._maybe_datetime(data.get("uptime_reset_at")),
            legacy_local_time_migrated=bool(data.get("legacy_local_time_migrated", False)),
            successful_profile_metrics_initialized=bool(
                data.get("successful_profile_metrics_initialized", False)
            ),
            per_profile_outcome_counters_initialized=bool(
                data.get("per_profile_outcome_counters_initialized", False)
            ),
        )

    def _maybe_datetime(self, value: Any) -> datetime | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        return datetime.fromisoformat(text)

    def _migrate_legacy_dashboard_timestamps_to_local_time(
        self,
        state: DesktopAppState,
    ) -> DesktopAppState:
        resets = state.dashboard_metric_resets
        if resets.legacy_local_time_migrated:
            return state
        migrated_activity = [
            replace(entry, timestamp=self._legacy_utc_to_local_naive(entry.timestamp))
            for entry in state.activity
        ]
        migrated_last_successful = self._migrate_legacy_iso_timestamp(
            state.last_successful_raid_open_at
        )
        migrated_resets = replace(resets, legacy_local_time_migrated=True)
        return replace(
            state,
            activity=migrated_activity,
            last_successful_raid_open_at=migrated_last_successful,
            dashboard_metric_resets=migrated_resets,
        )

    def _migrate_legacy_iso_timestamp(self, value: str | None) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        return self._legacy_utc_to_local_naive(datetime.fromisoformat(text)).isoformat()

    def _legacy_utc_to_local_naive(self, value: datetime) -> datetime:
        return value.replace(tzinfo=timezone.utc).astimezone().replace(tzinfo=None)

    def _initialize_successful_profile_metrics(
        self,
        state: DesktopAppState,
    ) -> DesktopAppState:
        resets = state.dashboard_metric_resets
        if resets.successful_profile_metrics_initialized:
            return replace(
                state,
                successful_profile_runs=self._cap_successful_profile_runs(
                    state.successful_profile_runs
                ),
            )
        return replace(
            state,
            successful_profile_runs=[],
            dashboard_metric_resets=replace(
                resets,
                successful_profile_metrics_initialized=True,
            ),
        )

    def _initialize_per_profile_outcome_counters(
        self,
        state: DesktopAppState,
    ) -> DesktopAppState:
        resets = state.dashboard_metric_resets
        if resets.per_profile_outcome_counters_initialized:
            return state
        return replace(
            state,
            raids_completed=0,
            raids_failed=0,
            dashboard_metric_resets=replace(
                resets,
                raids_completed_offset=0,
                raids_failed_offset=0,
                success_rate_completed_offset=0,
                success_rate_failed_offset=0,
                per_profile_outcome_counters_initialized=True,
            ),
        )

    def _reset_corrupted_future_dashboard_history(
        self,
        state: DesktopAppState,
    ) -> DesktopAppState:
        if not self._state_has_future_dashboard_history(state):
            return state
        return replace(
            state,
            raids_detected=0,
            raids_opened=0,
            raids_completed=0,
            raids_failed=0,
            duplicates_skipped=0,
            non_matching_skipped=0,
            open_failures=0,
            sender_rejected=0,
            browser_session_failed=0,
            page_ready=0,
            executor_not_configured=0,
            executor_succeeded=0,
            executor_failed=0,
            session_closed=0,
            last_successful_raid_open_at=None,
            activity=[],
            successful_profile_runs=[],
            last_error=None,
            dashboard_metric_resets=DashboardMetricResetState(
                legacy_local_time_migrated=state.dashboard_metric_resets.legacy_local_time_migrated,
                per_profile_outcome_counters_initialized=True,
            ),
        )

    def _state_has_future_dashboard_history(self, state: DesktopAppState) -> bool:
        future_cutoff = datetime.now() + timedelta(minutes=5)
        if state.last_successful_raid_open_at:
            last_successful = datetime.fromisoformat(state.last_successful_raid_open_at)
            if last_successful > future_cutoff:
                return True
        return any(entry.timestamp > future_cutoff for entry in state.activity) or any(
            entry.timestamp > future_cutoff for entry in state.successful_profile_runs
        )

    def _maybe_int(self, value: Any) -> int | None:
        if value is None:
            return None
        return int(value)

    def _maybe_bool(self, value: Any, *, default: bool) -> bool:
        if value is None:
            return default
        return bool(value)

    def _bot_action_slot_to_data(self, slot: BotActionSlotConfig) -> dict[str, Any]:
        return {
            "key": slot.key,
            "label": slot.label,
            "enabled": slot.enabled,
            "template_path": str(slot.template_path) if slot.template_path is not None else None,
            "updated_at": slot.updated_at,
            "presets": [
                {
                    "id": preset.id,
                    "text": preset.text,
                    "image_path": (
                        str(preset.image_path) if preset.image_path is not None else None
                    ),
                }
                for preset in slot.presets
            ],
            "finish_template_path": (
                str(slot.finish_template_path)
                if slot.finish_template_path is not None
                else None
            ),
        }

    def _bot_action_slot_from_data(self, data: dict[str, Any]) -> BotActionSlotConfig:
        template_path = data.get("template_path")
        finish_template_path = data.get("finish_template_path")
        presets = tuple(
            BotActionPreset(
                id=str(preset.get("id") or ""),
                text=str(preset.get("text") or ""),
                image_path=(
                    Path(preset.get("image_path"))
                    if preset.get("image_path") is not None
                    else None
                ),
            )
            for preset in data.get("presets", ())
            if isinstance(preset, dict)
        )
        return BotActionSlotConfig(
            key=str(data.get("key") or ""),
            label=str(data.get("label") or ""),
            enabled=self._maybe_bool(data.get("enabled"), default=False),
            template_path=Path(template_path) if template_path is not None else None,
            updated_at=data.get("updated_at"),
            presets=presets,
            finish_template_path=(
                Path(finish_template_path) if finish_template_path is not None else None
            ),
        )

    def _raid_profile_config_to_data(self, profile: RaidProfileConfig) -> dict[str, Any]:
        return {
            "profile_directory": profile.profile_directory,
            "label": profile.label,
            "enabled": profile.enabled,
            "raid_on_restart": profile.raid_on_restart,
            "reply_enabled": profile.reply_enabled,
            "like_enabled": profile.like_enabled,
            "repost_enabled": profile.repost_enabled,
            "bookmark_enabled": profile.bookmark_enabled,
        }

    def _raid_profile_config_from_data(self, data: dict[str, Any]) -> RaidProfileConfig:
        profile_directory = str(data.get("profile_directory") or "").strip()
        return RaidProfileConfig(
            profile_directory=profile_directory,
            label=str(data.get("label") or profile_directory).strip() or profile_directory,
            enabled=self._maybe_bool(data.get("enabled"), default=True),
            raid_on_restart=self._maybe_bool(data.get("raid_on_restart"), default=False),
            reply_enabled=self._maybe_bool(data.get("reply_enabled"), default=True),
            like_enabled=self._maybe_bool(data.get("like_enabled"), default=True),
            repost_enabled=self._maybe_bool(data.get("repost_enabled"), default=True),
            bookmark_enabled=self._maybe_bool(data.get("bookmark_enabled"), default=True),
        )

    def _raid_profile_state_to_data(self, profile_state: RaidProfileState) -> dict[str, Any]:
        return {
            "profile_directory": profile_state.profile_directory,
            "label": profile_state.label,
            "status": profile_state.status,
            "last_error": profile_state.last_error,
        }

    def _raid_profile_state_from_data(self, data: dict[str, Any]) -> RaidProfileState:
        profile_directory = str(data.get("profile_directory") or "").strip()
        return RaidProfileState(
            profile_directory=profile_directory,
            label=str(data.get("label") or profile_directory).strip() or profile_directory,
            status=str(data.get("status") or "green"),
            last_error=data.get("last_error"),
        )

    def _normalize_raid_profile_states(
        self,
        raid_profile_states: tuple[RaidProfileState, ...],
        *,
        config: DesktopAppConfig | None,
    ) -> tuple[RaidProfileState, ...]:
        provided_states: dict[str, RaidProfileState] = {}
        for profile_state in raid_profile_states:
            profile_directory = str(profile_state.profile_directory).strip()
            if not profile_directory:
                continue
            provided_states[profile_directory] = RaidProfileState(
                profile_directory=profile_directory,
                label=str(profile_state.label).strip() or profile_directory,
                status=str(profile_state.status or "green"),
                last_error=profile_state.last_error,
            )
        if config is None:
            return tuple(provided_states.values())
        normalized_states: list[RaidProfileState] = []
        for profile in config.raid_profiles:
            existing_state = provided_states.get(profile.profile_directory)
            normalized_states.append(
                RaidProfileState(
                    profile_directory=profile.profile_directory,
                    label=profile.label,
                    status=existing_state.status if existing_state is not None else "green",
                    last_error=(
                        existing_state.last_error if existing_state is not None else None
                    ),
                )
            )
        return tuple(normalized_states)

    def _normalize_bot_state(self, state: BotRuntimeState) -> BotRuntimeState:
        if state in {
            BotRuntimeState.starting,
            BotRuntimeState.running,
            BotRuntimeState.stopping,
        }:
            return BotRuntimeState.stopped
        return state

    def _normalize_connection_state(
        self, state: TelegramConnectionState
    ) -> TelegramConnectionState:
        if state in {
            TelegramConnectionState.connecting,
            TelegramConnectionState.connected,
            TelegramConnectionState.reconnecting,
        }:
            return TelegramConnectionState.disconnected
        return state
