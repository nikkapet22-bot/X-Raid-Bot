from __future__ import annotations

from dataclasses import dataclass

from raidbot.browser.models import (
    RaidActionJob,
    RaidActionRequirements,
    RaidDetectionResult,
    RaidExecutionResult,
)


@dataclass(frozen=True)
class IncomingMessage:
    chat_id: int
    sender_id: int
    text: str
    has_video: bool = False


@dataclass(frozen=True)
class MessageOutcome:
    # Compatibility contract for the existing service/runtime path.
    action: str
    reason: str
    normalized_url: str | None = None


@dataclass(frozen=True)
class RaidMatch:
    raw_url: str
    normalized_url: str


__all__ = [
    "IncomingMessage",
    "MessageOutcome",
    "RaidMatch",
    "RaidActionRequirements",
    "RaidActionJob",
    "RaidDetectionResult",
    "RaidExecutionResult",
]
