from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Sequence


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


@dataclass(eq=True)
class BotActionSlotConfig:
    key: str
    label: str
    enabled: bool = False
    template_path: Path | None = None
    updated_at: str | None = None


_DEFAULT_BOT_ACTION_SLOT_LAYOUT: tuple[tuple[str, str], ...] = (
    ("slot_1_r", "R"),
    ("slot_2_l", "L"),
    ("slot_3_r", "R"),
    ("slot_4_b", "B"),
)


def default_bot_action_slots() -> tuple[BotActionSlotConfig, ...]:
    return tuple(
        BotActionSlotConfig(key=key, label=label)
        for key, label in _DEFAULT_BOT_ACTION_SLOT_LAYOUT
    )


@dataclass(init=False)
class DesktopAppConfig:
    telegram_api_id: int
    telegram_api_hash: str
    telegram_session_path: Path
    telegram_phone_number: str | None
    whitelisted_chat_ids: list[int]
    allowed_sender_ids: list[int]
    allowed_sender_entries: tuple[str, ...]
    chrome_profile_directory: str
    browser_mode: str
    executor_name: str
    preset_replies: tuple[str, ...]
    default_action_like: bool
    default_action_repost: bool
    default_action_bookmark: bool
    default_action_reply: bool
    auto_run_enabled: bool
    default_auto_sequence_id: str | None
    auto_run_settle_ms: int
    bot_action_slots: tuple[BotActionSlotConfig, ...]

    def __init__(
        self,
        telegram_api_id: int,
        telegram_api_hash: str,
        telegram_session_path: Path,
        telegram_phone_number: str | None,
        whitelisted_chat_ids: Sequence[int],
        chrome_profile_directory: str,
        allowed_sender_ids: Sequence[int] | None = None,
        allowed_sender_entries: Sequence[str] | None = None,
        *,
        raidar_sender_id: int | None = None,
        browser_mode: str = "launch-only",
        executor_name: str = "noop",
        preset_replies: Sequence[str] = (),
        default_action_like: bool = True,
        default_action_repost: bool = True,
        default_action_bookmark: bool = False,
        default_action_reply: bool = True,
        auto_run_enabled: bool = False,
        default_auto_sequence_id: str | None = None,
        auto_run_settle_ms: int = 1500,
        bot_action_slots: Sequence[BotActionSlotConfig] | None = None,
    ) -> None:
        self.telegram_api_id = telegram_api_id
        self.telegram_api_hash = telegram_api_hash
        self.telegram_session_path = Path(telegram_session_path)
        self.telegram_phone_number = telegram_phone_number
        self.whitelisted_chat_ids = [int(chat_id) for chat_id in whitelisted_chat_ids]
        self.allowed_sender_ids = self._coerce_allowed_sender_ids(
            allowed_sender_ids=allowed_sender_ids,
            raidar_sender_id=raidar_sender_id,
        )
        self.allowed_sender_entries = self._coerce_allowed_sender_entries(
            allowed_sender_entries=allowed_sender_entries,
            allowed_sender_ids=self.allowed_sender_ids,
        )
        self.chrome_profile_directory = chrome_profile_directory
        self.browser_mode = browser_mode
        self.executor_name = executor_name
        self.preset_replies = tuple(str(reply) for reply in preset_replies)
        self.default_action_like = default_action_like
        self.default_action_repost = default_action_repost
        self.default_action_bookmark = default_action_bookmark
        self.default_action_reply = default_action_reply
        self.auto_run_enabled = auto_run_enabled
        self.default_auto_sequence_id = default_auto_sequence_id
        self.auto_run_settle_ms = auto_run_settle_ms
        self.bot_action_slots = self._coerce_bot_action_slots(bot_action_slots)

    @property
    def raidar_sender_id(self) -> int | None:
        if not self.allowed_sender_ids:
            return None
        return self.allowed_sender_ids[0]

    def _coerce_allowed_sender_ids(
        self,
        *,
        allowed_sender_ids: Sequence[int] | None,
        raidar_sender_id: int | None,
    ) -> list[int]:
        if allowed_sender_ids is not None:
            return [int(sender_id) for sender_id in allowed_sender_ids]
        if raidar_sender_id is None:
            return []
        return [int(raidar_sender_id)]

    def _coerce_allowed_sender_entries(
        self,
        *,
        allowed_sender_entries: Sequence[str] | None,
        allowed_sender_ids: Sequence[int],
    ) -> tuple[str, ...]:
        if allowed_sender_entries is not None:
            return tuple(str(entry).strip() for entry in allowed_sender_entries if str(entry).strip())
        return tuple(str(sender_id) for sender_id in allowed_sender_ids)

    def _coerce_bot_action_slots(
        self, bot_action_slots: Sequence[BotActionSlotConfig] | None
    ) -> tuple[BotActionSlotConfig, ...]:
        normalized_slots: list[BotActionSlotConfig] = []
        provided_slots = tuple(bot_action_slots or ())
        for index, default_slot in enumerate(default_bot_action_slots()):
            provided_slot = provided_slots[index] if index < len(provided_slots) else None
            normalized_slots.append(
                BotActionSlotConfig(
                    key=default_slot.key,
                    label=default_slot.label,
                    enabled=bool(provided_slot.enabled) if provided_slot is not None else False,
                    template_path=(
                        Path(provided_slot.template_path)
                        if provided_slot is not None and provided_slot.template_path is not None
                        else None
                    ),
                    updated_at=(
                        str(provided_slot.updated_at)
                        if provided_slot is not None and provided_slot.updated_at is not None
                        else None
                    ),
                )
            )
        return tuple(normalized_slots)


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
    sender_rejected: int = 0
    browser_session_failed: int = 0
    page_ready: int = 0
    executor_not_configured: int = 0
    executor_succeeded: int = 0
    executor_failed: int = 0
    session_closed: int = 0
    last_successful_raid_open_at: str | None = None
    activity: list[ActivityEntry] = field(default_factory=list)
    last_error: str | None = None
    automation_queue_state: str = "idle"
    automation_queue_length: int = 0
    automation_current_url: str | None = None
    automation_last_error: str | None = None
