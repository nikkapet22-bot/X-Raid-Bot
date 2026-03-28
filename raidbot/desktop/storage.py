from __future__ import annotations

import json
import os
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import (
    ActivityEntry,
    BotRuntimeState,
    DesktopAppConfig,
    DesktopAppState,
    TelegramConnectionState,
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
            "raidar_sender_id": config.raidar_sender_id,
            "chrome_profile_directory": config.chrome_profile_directory,
        }

    def _config_from_data(self, data: dict[str, Any]) -> DesktopAppConfig:
        return DesktopAppConfig(
            telegram_api_id=int(data["telegram_api_id"]),
            telegram_api_hash=str(data["telegram_api_hash"]),
            telegram_session_path=Path(data["telegram_session_path"]),
            telegram_phone_number=data.get("telegram_phone_number"),
            whitelisted_chat_ids=[int(chat_id) for chat_id in data["whitelisted_chat_ids"]],
            raidar_sender_id=self._maybe_int(data.get("raidar_sender_id")),
            chrome_profile_directory=str(data["chrome_profile_directory"]),
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
            "last_successful_raid_open_at": state.last_successful_raid_open_at,
            "activity": [self._activity_to_data(entry) for entry in activity],
            "last_error": state.last_error,
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
            last_successful_raid_open_at=data.get("last_successful_raid_open_at"),
            activity=activity[-_ACTIVITY_LIMIT:],
            last_error=data.get("last_error"),
        )

    def _normalize_loaded_state(self, state: DesktopAppState) -> DesktopAppState:
        return replace(
            state,
            bot_state=self._normalize_bot_state(state.bot_state),
            connection_state=self._normalize_connection_state(state.connection_state),
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
