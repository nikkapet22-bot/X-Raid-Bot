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
    default_requirements: RaidActionRequirements | None = None,
) -> tuple[RaidService, TrackingDedupeStore]:
    dedupe_store = dedupe_store or TrackingDedupeStore()
    service = RaidService(
        allowed_chat_ids={-1001},
        allowed_sender_ids={42, 77},
        dedupe_store=dedupe_store,
        preset_replies=("gm", "lfg"),
        default_requirements=default_requirements
        or RaidActionRequirements(
            like=False,
            repost=False,
            bookmark=False,
            reply=False,
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
            has_video=True,
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
            has_video=True,
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


def test_handle_message_returns_sender_rejected_reason_for_wrong_sender_id():
    service, dedupe_store = build_service()

    result = service.handle_message(
        IncomingMessage(
            chat_id=-1001,
            sender_id=777,
            text="Like + Repost now\n\nhttps://x.com/i/status/123",
        )
    )

    assert result.kind == "sender_rejected"
    assert result.reason == "sender_id=777 not in allowlist"
    assert result.normalized_url is None
    assert result.job is None
    assert dedupe_store.contains_calls == []


def test_handle_message_returns_missing_action_markers_reason_for_non_matching_text():
    service, dedupe_store = build_service()

    result = service.handle_message(
        IncomingMessage(
            chat_id=-1001,
            sender_id=42,
            text="hello world no raid markers here",
        )
    )

    assert result.kind == "not_a_raid"
    assert result.reason == "missing_action_markers"
    assert result.normalized_url is None
    assert result.job is None
    assert dedupe_store.contains_calls == []


def test_service_contract_rejects_legacy_single_sender_argument():
    dedupe_store = TrackingDedupeStore()

    try:
        RaidService(
            allowed_chat_ids={-1001},
            allowed_sender_id=42,
            dedupe_store=dedupe_store,
        )
    except TypeError as exc:
        assert "allowed_sender_id" in str(exc)
    else:
        raise AssertionError("Expected TypeError for legacy allowed_sender_id argument")


def test_handle_message_merges_default_requirements_into_detected_job():
    service, _dedupe_store = build_service(
        default_requirements=RaidActionRequirements(
            like=False,
            repost=False,
            bookmark=True,
            reply=True,
        )
    )

    result = service.handle_message(
        IncomingMessage(
            chat_id=-1001,
            sender_id=42,
            text="Likes 10 | 8 [%]\n\nhttps://x.com/i/status/555",
            has_video=True,
        )
    )

    assert result.kind == "job_detected"
    assert result.job is not None
    assert result.job.requirements == RaidActionRequirements(
        like=True,
        repost=False,
        bookmark=True,
        reply=True,
    )


def test_handle_message_returns_missing_video_reason_for_parsed_link_without_video() -> None:
    service, dedupe_store = build_service()

    result = service.handle_message(
        IncomingMessage(
            chat_id=-1001,
            sender_id=42,
            text="Like + Repost now\n\nhttps://x.com/i/status/123",
            has_video=False,
        )
    )

    assert result.kind == "not_a_raid"
    assert result.reason == "missing_video"
    assert result.normalized_url is None
    assert result.job is None
    assert dedupe_store.contains_calls == []


def test_handle_message_returns_missing_status_url_reason() -> None:
    service, dedupe_store = build_service()

    result = service.handle_message(
        IncomingMessage(
            chat_id=-1001,
            sender_id=42,
            text="Like + Repost now but no tweet link here",
            has_video=True,
        )
    )

    assert result.kind == "not_a_raid"
    assert result.reason == "missing_status_url"
    assert result.normalized_url is None
    assert result.job is None
    assert dedupe_store.contains_calls == []


def test_handle_message_returns_missing_action_markers_reason_when_status_url_exists() -> None:
    service, dedupe_store = build_service()

    result = service.handle_message(
        IncomingMessage(
            chat_id=-1001,
            sender_id=42,
            text="Check this out\n\nhttps://x.com/i/status/123",
            has_video=True,
        )
    )

    assert result.kind == "not_a_raid"
    assert result.reason == "missing_action_markers"
    assert result.normalized_url is None
    assert result.job is None
    assert dedupe_store.contains_calls == []
