from __future__ import annotations

import json
import os
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import (
    BotActionSlotConfig,
    ActivityEntry,
    BotRuntimeState,
    DesktopAppConfig,
    DesktopAppState,
    TelegramConnectionState,
    default_bot_action_slots,
)

_ACTIVITY_LIMIT = 200


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
            return DesktopAppState()
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
            "bot_action_slots": [
                self._bot_action_slot_to_data(slot) for slot in config.bot_action_slots
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
        bot_action_slots_data = data.get("bot_action_slots")
        if bot_action_slots_data is None:
            bot_action_slots = default_bot_action_slots()
        else:
            bot_action_slots = tuple(
                self._bot_action_slot_from_data(slot_data) for slot_data in bot_action_slots_data
            )
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
            bot_action_slots=bot_action_slots,
        )

    def _state_to_data(self, state: DesktopAppState) -> dict[str, Any]:
        activity = self._cap_activity(state.activity)
        return {
            "bot_state": state.bot_state.value,
            "connection_state": state.connection_state.value,
            "raids_opened": state.raids_opened,
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
            "last_error": state.last_error,
            "automation_queue_state": state.automation_queue_state,
            "automation_queue_length": state.automation_queue_length,
            "automation_current_url": state.automation_current_url,
            "automation_last_error": state.automation_last_error,
        }

    def _state_from_data(self, data: dict[str, Any]) -> DesktopAppState:
        activity = [self._activity_from_data(item) for item in data.get("activity", [])]
        return DesktopAppState(
            bot_state=BotRuntimeState(data.get("bot_state", BotRuntimeState.stopped.value)),
            connection_state=TelegramConnectionState(
                data.get("connection_state", TelegramConnectionState.disconnected.value)
            ),
            raids_opened=int(data.get("raids_opened", 0)),
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
            last_error=data.get("last_error"),
            automation_queue_state=str(data.get("automation_queue_state") or "idle"),
            automation_queue_length=(
                int(data["automation_queue_length"])
                if data.get("automation_queue_length") is not None
                else 0
            ),
            automation_current_url=data.get("automation_current_url"),
            automation_last_error=data.get("automation_last_error"),
        )

    def _normalize_loaded_state(self, state: DesktopAppState) -> DesktopAppState:
        return replace(
            state,
            bot_state=self._normalize_bot_state(state.bot_state),
            connection_state=self._normalize_connection_state(state.connection_state),
            automation_queue_state="idle",
            automation_queue_length=0,
            automation_current_url=None,
            automation_last_error=None,
        )

    def _activity_to_data(self, entry: ActivityEntry) -> dict[str, Any]:
        return {
            "timestamp": entry.timestamp.isoformat(),
            "action": entry.action,
            "url": entry.url,
            "reason": entry.reason,
        }

    def _activity_from_data(self, data: dict[str, Any]) -> ActivityEntry:
        return ActivityEntry(
            timestamp=datetime.fromisoformat(str(data["timestamp"])),
            action=str(data["action"]),
            url=data.get("url"),
            reason=data.get("reason"),
        )

    def _cap_activity(self, activity: list[ActivityEntry]) -> list[ActivityEntry]:
        return list(activity[-_ACTIVITY_LIMIT:])

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
        }

    def _bot_action_slot_from_data(self, data: dict[str, Any]) -> BotActionSlotConfig:
        template_path = data.get("template_path")
        return BotActionSlotConfig(
            key=str(data["key"]),
            label=str(data["label"]),
            enabled=self._maybe_bool(data.get("enabled"), default=False),
            template_path=Path(template_path) if template_path is not None else None,
            updated_at=data.get("updated_at"),
        )

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
