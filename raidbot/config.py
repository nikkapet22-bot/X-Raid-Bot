from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    telegram_api_id: int
    telegram_api_hash: str
    telegram_session_path: Path
    telegram_chat_whitelist: set[int]
    allowed_sender_ids: set[int]
    chrome_path: Path
    chrome_user_data_dir: Path
    chrome_profile_directory: str
    raidar_sender_id: int | None = None
    browser_mode: str = "launch-only"
    executor_name: str = "noop"
    preset_replies: tuple[str, ...] = ()
    default_action_like: bool = True
    default_action_repost: bool = True
    default_action_bookmark: bool = False
    default_action_reply: bool = True
    open_cooldown_seconds: float = 0.0
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> "Settings":
        allowed_sender_ids = _parse_allowed_sender_ids()
        return cls(
            telegram_api_id=_require_int("TELEGRAM_API_ID"),
            telegram_api_hash=_require("TELEGRAM_API_HASH"),
            telegram_session_path=Path(_require("TELEGRAM_SESSION_PATH")),
            telegram_chat_whitelist=_parse_int_set("TELEGRAM_CHAT_WHITELIST"),
            allowed_sender_ids=allowed_sender_ids,
            chrome_path=Path(_require("CHROME_PATH")),
            chrome_user_data_dir=Path(_require("CHROME_USER_DATA_DIR")),
            chrome_profile_directory=_require("CHROME_PROFILE_DIRECTORY"),
            raidar_sender_id=_optional_int("RAIDAR_SENDER_ID"),
            browser_mode=_optional_str("BROWSER_MODE", "launch-only"),
            executor_name=_optional_str("EXECUTOR_NAME", "noop"),
            preset_replies=_parse_str_list("PRESET_REPLIES"),
            default_action_like=_optional_bool("DEFAULT_ACTION_LIKE", True),
            default_action_repost=_optional_bool("DEFAULT_ACTION_REPOST", True),
            default_action_bookmark=_optional_bool("DEFAULT_ACTION_BOOKMARK", False),
            default_action_reply=_optional_bool("DEFAULT_ACTION_REPLY", True),
            open_cooldown_seconds=_optional_float("OPEN_COOLDOWN_SECONDS", 0.0),
            log_level=_optional_str("LOG_LEVEL", "INFO").upper(),
        )


def _require(name: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        raise ValueError(f"Missing required setting: {name}")
    return value.strip()


def _require_int(name: str) -> int:
    return int(_require(name))


def _parse_int_set(name: str) -> set[int]:
    raw_value = _require(name)
    return _parse_int_csv(raw_value, name)


def _parse_int_csv(raw_value: str, setting_name: str) -> set[int]:
    items = [item.strip() for item in raw_value.split(",")]
    if not items or any(not item for item in items):
        raise ValueError(f"Missing required setting: {setting_name}")
    return {int(item) for item in items}


def _optional_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return float(value.strip())


def _optional_str(name: str, default: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip()


def _optional_int(name: str) -> int | None:
    value = os.getenv(name)
    if value is None or not value.strip():
        return None
    return int(value.strip())


def _optional_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default

    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"Invalid boolean setting: {name}")


def _parse_str_list(name: str) -> tuple[str, ...]:
    value = os.getenv(name)
    if value is None or not value.strip():
        return ()

    parts = [part.strip() for part in value.split(",")]
    return tuple(part for part in parts if part)


def _parse_allowed_sender_ids() -> set[int]:
    allowlist = os.getenv("ALLOWED_SENDER_IDS")
    if allowlist is not None and allowlist.strip():
        return _parse_int_csv(allowlist, "ALLOWED_SENDER_IDS")

    return {_require_int("RAIDAR_SENDER_ID")}
