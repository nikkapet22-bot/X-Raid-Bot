from __future__ import annotations

from raidbot.desktop.automation.autorun import (
    AutoRunProcessor,
    OpenedRaidContext,
    PendingRaidWorkItem,
)
from raidbot.desktop.automation.windowing import WindowInfo, find_existing_chrome_window


def build_item(url: str = "https://x.com/i/status/123", trace_id: str = "raid-1") -> PendingRaidWorkItem:
    return PendingRaidWorkItem(normalized_url=url, trace_id=trace_id)


def build_window(handle: int = 7, title: str = "RaidBot - Chrome", last_focused_at: float = 1.0) -> WindowInfo:
    return WindowInfo(
        handle=handle,
        title=title,
        bounds=(0, 0, 100, 100),
        last_focused_at=last_focused_at,
    )


class FakeWindowManager:
    def __init__(self, windows: list[WindowInfo]) -> None:
        self.windows = list(windows)

    def list_chrome_windows(self) -> list[WindowInfo]:
        return list(self.windows)


def test_find_existing_chrome_window_returns_none_when_no_window_is_available() -> None:
    window = find_existing_chrome_window(FakeWindowManager([]))

    assert window is None


def test_autorun_processor_admits_items_fifo_without_opening_them() -> None:
    opened: list[str] = []
    processor = AutoRunProcessor(
        auto_run_enabled=lambda: True,
        default_sequence_id=lambda: "seq-1",
        pre_open_check=lambda _item: build_window(),
        open_raid=lambda item, window: opened.append(f"{item.normalized_url}:{window.handle}"),
        execute_raid=lambda _item, _context, _sequence_id: (True, None),
        close_raid=lambda _context: None,
    )

    first = build_item("https://x.com/i/status/100", trace_id="raid-100")
    second = build_item("https://x.com/i/status/200", trace_id="raid-200")

    assert processor.admit(first) is True
    assert processor.admit(second) is True
    assert processor.state == "queued"
    assert processor.queue_length == 2
    assert processor.pending_items == (first, second)
    assert opened == []


def test_autorun_processor_rejects_disabled_and_paused_admission_without_opening() -> None:
    opened: list[str] = []
    failures: list[tuple[str, str]] = []
    auto_run_enabled = {"value": False}
    default_sequence = {"value": "seq-1"}
    processor = AutoRunProcessor(
        auto_run_enabled=lambda: auto_run_enabled["value"],
        default_sequence_id=lambda: default_sequence["value"],
        pre_open_check=lambda _item: build_window(),
        open_raid=lambda item, window: opened.append(f"{item.normalized_url}:{window.handle}"),
        execute_raid=lambda _item, _context, _sequence_id: (True, None),
        close_raid=lambda _context: None,
        on_failure=lambda item, reason, _context: failures.append((item.trace_id, reason)),
    )

    disabled_item = build_item(trace_id="disabled")
    paused_item = build_item(trace_id="paused")

    assert processor.admit(disabled_item) is False
    assert failures == [("disabled", "auto_run_disabled")]
    assert opened == []

    auto_run_enabled["value"] = True
    default_sequence["value"] = None

    assert processor.admit(paused_item) is False
    assert processor.state == "paused"
    assert failures[-1] == ("paused", "default_sequence_missing")
    assert opened == []


def test_autorun_processor_missing_default_sequence_pauses_without_enqueuing() -> None:
    failures: list[str] = []
    processor = AutoRunProcessor(
        auto_run_enabled=lambda: True,
        default_sequence_id=lambda: None,
        pre_open_check=lambda _item: build_window(),
        open_raid=lambda _item, _window: (_ for _ in ()).throw(AssertionError("open should not be called")),
        execute_raid=lambda _item, _context, _sequence_id: (True, None),
        close_raid=lambda _context: None,
        on_failure=lambda _item, reason, _context: failures.append(reason),
    )

    admitted = processor.admit(build_item())

    assert admitted is False
    assert processor.state == "paused"
    assert processor.queue_length == 0
    assert failures == ["default_sequence_missing"]


def test_autorun_processor_pauses_when_pre_open_validation_fails_closed() -> None:
    opened: list[str] = []
    failures: list[str] = []
    processor = AutoRunProcessor(
        auto_run_enabled=lambda: True,
        default_sequence_id=lambda: "seq-1",
        pre_open_check=lambda _item: None,
        open_raid=lambda item, window: opened.append(f"{item.normalized_url}:{window.handle}"),
        execute_raid=lambda _item, _context, _sequence_id: (True, None),
        close_raid=lambda _context: None,
        on_failure=lambda _item, reason, _context: failures.append(reason),
    )
    item = build_item()

    assert processor.admit(item) is True

    processed = processor.process_next()

    assert processed is False
    assert processor.state == "paused"
    assert processor.queue_length == 0
    assert failures == ["target_window_not_found"]
    assert opened == []


def test_autorun_processor_success_transitions_running_to_idle_and_closes_context() -> None:
    statuses: list[tuple[str, int, str | None, str | None]] = []
    successes: list[tuple[str, int]] = []
    closes: list[int] = []
    processor = AutoRunProcessor(
        auto_run_enabled=lambda: True,
        default_sequence_id=lambda: "seq-1",
        pre_open_check=lambda _item: build_window(handle=11),
        open_raid=lambda item, window: OpenedRaidContext(
            normalized_url=item.normalized_url,
            opened_at=1.5,
            window_handle=window.handle,
            profile_directory="Profile 3",
        ),
        execute_raid=lambda _item, _context, sequence_id: (sequence_id == "seq-1", None),
        close_raid=lambda context: closes.append(context.window_handle),
        on_success=lambda item, context: successes.append((item.trace_id, context.window_handle)),
        on_status=lambda state, queue_length, current_url, last_error: statuses.append(
            (state, queue_length, current_url, last_error)
        ),
    )
    item = build_item()

    assert processor.admit(item) is True

    processed = processor.process_next()

    assert processed is True
    assert processor.state == "idle"
    assert processor.queue_length == 0
    assert processor.current_url is None
    assert successes == [("raid-1", 11)]
    assert closes == [11]
    assert statuses == [
        ("queued", 1, None, None),
        ("running", 0, "https://x.com/i/status/123", None),
        ("idle", 0, None, None),
    ]


def test_autorun_processor_failure_pauses_and_leaves_context_open() -> None:
    statuses: list[tuple[str, int, str | None, str | None]] = []
    failures: list[tuple[str, str, int | None]] = []
    closes: list[int] = []
    processor = AutoRunProcessor(
        auto_run_enabled=lambda: True,
        default_sequence_id=lambda: "seq-1",
        pre_open_check=lambda _item: build_window(handle=12),
        open_raid=lambda item, window: OpenedRaidContext(
            normalized_url=item.normalized_url,
            opened_at=2.0,
            window_handle=window.handle,
            profile_directory="Profile 3",
        ),
        execute_raid=lambda _item, _context, _sequence_id: (False, "image_match_not_found"),
        close_raid=lambda context: closes.append(context.window_handle),
        on_failure=lambda item, reason, context: failures.append(
            (item.trace_id, reason, getattr(context, "window_handle", None))
        ),
        on_status=lambda state, queue_length, current_url, last_error: statuses.append(
            (state, queue_length, current_url, last_error)
        ),
    )
    item = build_item()

    assert processor.admit(item) is True

    processed = processor.process_next()

    assert processed is False
    assert processor.state == "paused"
    assert processor.queue_length == 0
    assert processor.current_url is None
    assert processor.last_error == "image_match_not_found"
    assert failures == [("raid-1", "image_match_not_found", 12)]
    assert closes == []
    assert statuses == [
        ("queued", 1, None, None),
        ("running", 0, "https://x.com/i/status/123", None),
        ("paused", 0, None, "image_match_not_found"),
    ]
