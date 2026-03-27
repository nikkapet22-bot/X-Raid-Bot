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
    raidar_sender_id: int
    chrome_path: Path
    chrome_user_data_dir: Path
    chrome_profile_directory: str
    open_cooldown_seconds: float = 0.0
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            telegram_api_id=_require_int("TELEGRAM_API_ID"),
            telegram_api_hash=_require("TELEGRAM_API_HASH"),
            telegram_session_path=Path(_require("TELEGRAM_SESSION_PATH")),
            telegram_chat_whitelist=_parse_int_set("TELEGRAM_CHAT_WHITELIST"),
            raidar_sender_id=_require_int("RAIDAR_SENDER_ID"),
            chrome_path=Path(_require("CHROME_PATH")),
            chrome_user_data_dir=Path(_require("CHROME_USER_DATA_DIR")),
            chrome_profile_directory=_require("CHROME_PROFILE_DIRECTORY"),
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
    items = [item.strip() for item in raw_value.split(",")]
    if any(not item for item in items):
        raise ValueError(f"Missing required setting: {name}")
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
