from __future__ import annotations

from collections.abc import Callable
import uuid

from raidbot.models import (
    IncomingMessage,
    RaidActionJob,
    RaidActionRequirements,
    RaidDetectionResult,
)
from raidbot.parser import analyze_raid_message

class RaidService:
    def __init__(
        self,
        allowed_chat_ids: set[int],
        allowed_sender_ids: set[int],
        dedupe_store=None,
        preset_replies: tuple[str, ...] = (),
        default_requirements: RaidActionRequirements | None = None,
        trace_id_factory: Callable[[], str] | None = None,
    ) -> None:
        if not allowed_sender_ids:
            raise ValueError("RaidService requires at least one allowed sender id")
        if dedupe_store is None:
            raise ValueError("RaidService requires a dedupe_store")

        self.allowed_chat_ids = allowed_chat_ids
        self.allowed_sender_ids = set(allowed_sender_ids)
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
            return RaidDetectionResult(kind="chat_rejected", reason="chat_rejected")

        if message.sender_id not in self.allowed_sender_ids:
            return RaidDetectionResult(
                kind="sender_rejected",
                reason=f"sender_id={message.sender_id} not in allowlist",
            )

        parse_outcome = analyze_raid_message(message.text)
        raid_match = parse_outcome.match
        if raid_match is None:
            return RaidDetectionResult(
                kind="not_a_raid",
                reason=parse_outcome.reason or "not_a_raid",
            )
        if not message.has_video:
            return RaidDetectionResult(kind="not_a_raid", reason="missing_video")

        normalized_url = raid_match.normalized_url
        if self.dedupe_store.contains(normalized_url):
            return RaidDetectionResult(
                kind="duplicate",
                normalized_url=normalized_url,
                reason="duplicate",
            )

        job = RaidActionJob(
            normalized_url=normalized_url,
            raw_url=raid_match.raw_url,
            chat_id=message.chat_id,
            sender_id=message.sender_id,
            requirements=raid_match.requirements.merged_with(self.default_requirements),
            preset_replies=self.preset_replies,
            trace_id=self._trace_id_factory(),
        )
        return RaidDetectionResult.job_detected(job)


def _new_trace_id() -> str:
    return f"raid-{uuid.uuid4().hex}"
