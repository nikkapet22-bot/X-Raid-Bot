from __future__ import annotations

import logging

from raidbot.models import IncomingMessage, MessageOutcome
from raidbot.parser import parse_raid_message

logger = logging.getLogger(__name__)


class RaidService:
    def __init__(
        self,
        allowed_chat_ids: set[int],
        allowed_sender_id: int,
        opener,
        dedupe_store,
    ) -> None:
        self.allowed_chat_ids = allowed_chat_ids
        self.allowed_sender_id = allowed_sender_id
        self.opener = opener
        self.dedupe_store = dedupe_store

    def handle_message(self, message: IncomingMessage) -> MessageOutcome:
        if message.chat_id not in self.allowed_chat_ids:
            return MessageOutcome(action="skipped", reason="chat_not_whitelisted")

        if message.sender_id != self.allowed_sender_id:
            return MessageOutcome(action="skipped", reason="sender_not_allowed")

        raid_match = parse_raid_message(message.text)
        if raid_match is None:
            return MessageOutcome(action="skipped", reason="not_a_raid")

        normalized_url = raid_match.normalized_url
        if self.dedupe_store.contains(normalized_url):
            return MessageOutcome(
                action="skipped",
                reason="duplicate",
                normalized_url=normalized_url,
            )

        try:
            self.opener.open(normalized_url)
        except Exception:
            logger.exception("Failed to open raid URL: %s", normalized_url)
            return MessageOutcome(
                action="skipped",
                reason="open_failed",
                normalized_url=normalized_url,
            )

        self.dedupe_store.mark_if_new(normalized_url)
        return MessageOutcome(
            action="opened",
            reason="raid_opened",
            normalized_url=normalized_url,
        )
