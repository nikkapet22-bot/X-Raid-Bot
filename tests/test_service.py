from raidbot.dedupe import InMemoryOpenedUrlStore
from raidbot.models import IncomingMessage
from raidbot.service import RaidService


class FakeOpener:
    def __init__(self) -> None:
        self.opened_urls: list[str] = []

    def open(self, url: str) -> None:
        self.opened_urls.append(url)


class RaisingOpener:
    def open(self, url: str) -> None:
        raise RuntimeError("chrome launch failed")


class TrackingDedupeStore:
    def __init__(self) -> None:
        self.marked_urls: list[str] = []

    def contains(self, url: str) -> bool:
        return False

    def mark_if_new(self, url: str) -> bool:
        self.marked_urls.append(url)
        return True


def build_service() -> tuple[RaidService, FakeOpener]:
    opener = FakeOpener()
    service = RaidService(
        allowed_chat_ids={-1001},
        allowed_sender_id=42,
        opener=opener,
        dedupe_store=InMemoryOpenedUrlStore(),
    )
    return service, opener


def test_handle_message_opens_a_new_matching_raid():
    service, opener = build_service()

    outcome = service.handle_message(
        IncomingMessage(
            chat_id=-1001,
            sender_id=42,
            text="Likes 10 | 8 [%]\n\nhttps://x.com/i/status/123",
        )
    )

    assert outcome.action == "opened"
    assert outcome.reason == "raid_opened"
    assert outcome.normalized_url == "https://x.com/i/status/123"
    assert opener.opened_urls == ["https://x.com/i/status/123"]


def test_handle_message_skips_duplicate_raid_urls():
    service, opener = build_service()
    message = IncomingMessage(
        chat_id=-1001,
        sender_id=42,
        text="Likes 10 | 8 [%]\n\nhttps://x.com/i/status/123",
    )

    first_outcome = service.handle_message(message)
    second_outcome = service.handle_message(message)

    assert first_outcome.action == "opened"
    assert second_outcome.action == "skipped"
    assert second_outcome.reason == "duplicate"
    assert second_outcome.normalized_url == "https://x.com/i/status/123"
    assert opener.opened_urls == ["https://x.com/i/status/123"]


def test_handle_message_skips_when_opening_fails():
    dedupe_store = TrackingDedupeStore()
    service = RaidService(
        allowed_chat_ids={-1001},
        allowed_sender_id=42,
        opener=RaisingOpener(),
        dedupe_store=dedupe_store,
    )

    outcome = service.handle_message(
        IncomingMessage(
            chat_id=-1001,
            sender_id=42,
            text="Likes 10 | 8 [%]\n\nhttps://x.com/i/status/123",
        )
    )

    assert outcome.action == "skipped"
    assert outcome.reason == "open_failed"
    assert outcome.normalized_url == "https://x.com/i/status/123"
    assert dedupe_store.marked_urls == []


def test_handle_message_rejects_non_whitelisted_chats():
    service, opener = build_service()

    outcome = service.handle_message(
        IncomingMessage(
            chat_id=-9999,
            sender_id=42,
            text="Likes 10 | 8 [%]\n\nhttps://x.com/i/status/123",
        )
    )

    assert outcome.action == "skipped"
    assert outcome.reason == "chat_not_whitelisted"
    assert outcome.normalized_url is None
    assert opener.opened_urls == []


def test_handle_message_rejects_wrong_sender_id():
    service, opener = build_service()

    outcome = service.handle_message(
        IncomingMessage(
            chat_id=-1001,
            sender_id=777,
            text="Likes 10 | 8 [%]\n\nhttps://x.com/i/status/123",
        )
    )

    assert outcome.action == "skipped"
    assert outcome.reason == "sender_not_allowed"
    assert outcome.normalized_url is None
    assert opener.opened_urls == []
