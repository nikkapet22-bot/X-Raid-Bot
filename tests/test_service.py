from raidbot.models import IncomingMessage, RaidActionRequirements
from raidbot.service import RaidService


class TrackingDedupeStore:
    def __init__(self) -> None:
        self.contains_calls: list[str] = []
        self.mark_calls: list[str] = []
        self.existing: set[str] = set()

    def contains(self, url: str) -> bool:
        self.contains_calls.append(url)
        return url in self.existing

    def mark_if_new(self, url: str) -> bool:
        self.mark_calls.append(url)
        return True


def build_service(
    *,
    dedupe_store: TrackingDedupeStore | None = None,
    trace_id_factory=None,
) -> tuple[RaidService, TrackingDedupeStore]:
    dedupe_store = dedupe_store or TrackingDedupeStore()
    service = RaidService(
        allowed_chat_ids={-1001},
        allowed_sender_ids={42, 77},
        dedupe_store=dedupe_store,
        preset_replies=("gm", "lfg"),
        default_requirements=RaidActionRequirements(
            like=True,
            repost=True,
            bookmark=False,
            reply=True,
        ),
        trace_id_factory=trace_id_factory or (lambda: "trace-123"),
    )
    return service, dedupe_store


def test_handle_message_detects_job_for_allowed_sender():
    service, dedupe_store = build_service()

    result = service.handle_message(
        IncomingMessage(
            chat_id=-1001,
            sender_id=77,
            text="Like + Repost now\n\nhttps://x.com/i/status/123",
        )
    )

    assert result.kind == "job_detected"
    assert result.normalized_url == "https://x.com/i/status/123"
    assert result.job is not None
    assert result.job.chat_id == -1001
    assert result.job.sender_id == 77
    assert result.job.raw_url == "https://x.com/i/status/123"
    assert result.job.normalized_url == "https://x.com/i/status/123"
    assert result.job.requirements == RaidActionRequirements(
        like=True,
        repost=True,
        bookmark=False,
        reply=False,
    )
    assert result.job.preset_replies == ("gm", "lfg")
    assert result.job.trace_id == "trace-123"
    assert dedupe_store.contains_calls == ["https://x.com/i/status/123"]
    assert dedupe_store.mark_calls == []


def test_handle_message_returns_duplicate_before_job_creation():
    dedupe_store = TrackingDedupeStore()
    dedupe_store.existing.add("https://x.com/i/status/123")
    trace_invocations: list[str] = []
    service, _ = build_service(
        dedupe_store=dedupe_store,
        trace_id_factory=lambda: trace_invocations.append("called") or "trace-999",
    )

    result = service.handle_message(
        IncomingMessage(
            chat_id=-1001,
            sender_id=42,
            text="Like + Repost now\n\nhttps://x.com/i/status/123",
        )
    )

    assert result.kind == "duplicate"
    assert result.normalized_url == "https://x.com/i/status/123"
    assert result.job is None
    assert trace_invocations == []
    assert dedupe_store.contains_calls == ["https://x.com/i/status/123"]
    assert dedupe_store.mark_calls == []


def test_handle_message_rejects_non_whitelisted_chats():
    service, dedupe_store = build_service()

    result = service.handle_message(
        IncomingMessage(
            chat_id=-9999,
            sender_id=42,
            text="Like + Repost now\n\nhttps://x.com/i/status/123",
        )
    )

    assert result.kind == "chat_rejected"
    assert result.normalized_url is None
    assert result.job is None
    assert dedupe_store.contains_calls == []


def test_handle_message_rejects_wrong_sender_id():
    service, dedupe_store = build_service()

    result = service.handle_message(
        IncomingMessage(
            chat_id=-1001,
            sender_id=777,
            text="Like + Repost now\n\nhttps://x.com/i/status/123",
        )
    )

    assert result.kind == "sender_rejected"
    assert result.normalized_url is None
    assert result.job is None
    assert dedupe_store.contains_calls == []


def test_handle_message_returns_not_a_raid_for_non_matching_text():
    service, dedupe_store = build_service()

    result = service.handle_message(
        IncomingMessage(
            chat_id=-1001,
            sender_id=42,
            text="hello world no raid markers here",
        )
    )

    assert result.kind == "not_a_raid"
    assert result.normalized_url is None
    assert result.job is None
    assert dedupe_store.contains_calls == []
