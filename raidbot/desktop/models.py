from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
from pathlib import Path


class BotRuntimeState(str, Enum):
    setup_required = "setup_required"
    stopped = "stopped"
    starting = "starting"
    running = "running"
    stopping = "stopping"
    error = "error"


class TelegramConnectionState(str, Enum):
    disconnected = "disconnected"
    connecting = "connecting"
    connected = "connected"
    reconnecting = "reconnecting"
    auth_required = "auth_required"


@dataclass
class DesktopAppConfig:
    telegram_api_id: int
    telegram_api_hash: str
    telegram_session_path: Path
    telegram_phone_number: str | None
    whitelisted_chat_ids: list[int]
    raidar_sender_id: int | None
    chrome_profile_directory: str


@dataclass
class ActivityEntry:
    timestamp: datetime
    action: str
    url: str | None = None
    reason: str | None = None


@dataclass
class DesktopAppState:
    bot_state: BotRuntimeState = BotRuntimeState.stopped
    connection_state: TelegramConnectionState = TelegramConnectionState.disconnected
    raids_opened: int = 0
    duplicates_skipped: int = 0
    non_matching_skipped: int = 0
    open_failures: int = 0
    last_successful_raid_open_at: str | None = None
    activity: list[ActivityEntry] = field(default_factory=list)
    last_error: str | None = None
