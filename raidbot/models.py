from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IncomingMessage:
    chat_id: int
    sender_id: int
    text: str


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
