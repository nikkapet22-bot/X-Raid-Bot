from __future__ import annotations

from collections.abc import Callable
import uuid

from raidbot.models import (
    IncomingMessage,
    RaidActionJob,
    RaidActionRequirements,
    RaidDetectionResult,
)
from raidbot.parser import parse_raid_message

class RaidService:
    def __init__(
        self,
        allowed_chat_ids: set[int],
        allowed_sender_ids: set[int] | None = None,
        dedupe_store=None,
        preset_replies: tuple[str, ...] = (),
        default_requirements: RaidActionRequirements | None = None,
        trace_id_factory: Callable[[], str] | None = None,
        *,
        allowed_sender_id: int | None = None,
        opener=None,
    ) -> None:
        resolved_sender_ids = set(allowed_sender_ids or ())
        if allowed_sender_id is not None:
            resolved_sender_ids.add(allowed_sender_id)
        if not resolved_sender_ids:
            raise ValueError("RaidService requires at least one allowed sender id")
        if dedupe_store is None:
            raise ValueError("RaidService requires a dedupe_store")

        self.allowed_chat_ids = allowed_chat_ids
        self.allowed_sender_ids = resolved_sender_ids
        self.allowed_sender_id = allowed_sender_id
        self.opener = opener
        self.dedupe_store = dedupe_store
        self.preset_replies = preset_replies
        self.default_requirements = default_requirements or RaidActionRequirements(
            like=False,
            repost=False,
            bookmark=False,
            reply=False,
        )
        self._trace_id_factory = trace_id_factory or _new_trace_id

    def handle_message(self, message: IncomingMessage) -> RaidDetectionResult:
        if message.chat_id not in self.allowed_chat_ids:
            return RaidDetectionResult(kind="chat_rejected")

        if message.sender_id not in self.allowed_sender_ids:
            return RaidDetectionResult(kind="sender_rejected")

        raid_match = parse_raid_message(message.text)
        if raid_match is None:
            return RaidDetectionResult(kind="not_a_raid")

        normalized_url = raid_match.normalized_url
        if self.dedupe_store.contains(normalized_url):
            return RaidDetectionResult(
                kind="duplicate",
                normalized_url=normalized_url,
            )

        job = RaidActionJob(
            normalized_url=normalized_url,
            raw_url=raid_match.raw_url,
            chat_id=message.chat_id,
            sender_id=message.sender_id,
            requirements=raid_match.requirements,
            preset_replies=self.preset_replies,
            trace_id=self._trace_id_factory(),
        )
        return RaidDetectionResult.job_detected(job)


def _new_trace_id() -> str:
    return f"raid-{uuid.uuid4().hex}"
