from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

from raidbot.desktop.automation.windowing import WindowInfo


@dataclass(frozen=True)
class PendingRaidWorkItem:
    normalized_url: str
    trace_id: str


@dataclass(frozen=True)
class OpenedRaidContext:
    normalized_url: str
    opened_at: float
    window_handle: int | None
    profile_directory: str


class AutoRunProcessor:
    def __init__(
        self,
        *,
        auto_run_enabled: Callable[[], bool],
        default_sequence_id: Callable[[], str | None],
        pre_open_check: Callable[[PendingRaidWorkItem], WindowInfo | None],
        open_raid: Callable[[PendingRaidWorkItem, WindowInfo], OpenedRaidContext],
        execute_raid: Callable[
            [PendingRaidWorkItem, OpenedRaidContext, str],
            tuple[bool, str | None],
        ],
        close_raid: Callable[[OpenedRaidContext], None],
        on_success: Callable[[PendingRaidWorkItem, OpenedRaidContext], None] | None = None,
        on_failure: Callable[[PendingRaidWorkItem, str, OpenedRaidContext | None], None]
        | None = None,
        on_status: Callable[[str, int, str | None, str | None], None] | None = None,
    ) -> None:
        self._auto_run_enabled = auto_run_enabled
        self._default_sequence_id = default_sequence_id
        self._pre_open_check = pre_open_check
        self._open_raid = open_raid
        self._execute_raid = execute_raid
        self._close_raid = close_raid
        self._on_success = on_success or (lambda _item, _context: None)
        self._on_failure = on_failure or (lambda _item, _reason, _context: None)
        self._on_status = on_status or (lambda _state, _length, _url, _error: None)
        self._pending: deque[PendingRaidWorkItem] = deque()
        self._state = "idle"
        self._current_url: str | None = None
        self._last_error: str | None = None

    @property
    def state(self) -> str:
        return self._state

    @property
    def queue_length(self) -> int:
        return len(self._pending)

    @property
    def pending_items(self) -> tuple[PendingRaidWorkItem, ...]:
        return tuple(self._pending)

    @property
    def current_url(self) -> str | None:
        return self._current_url

    @property
    def last_error(self) -> str | None:
        return self._last_error

    def admit(self, item: PendingRaidWorkItem) -> bool:
        if not self._auto_run_enabled():
            self._reject(item, "auto_run_disabled")
            return False
        if self._state == "paused":
            self._reject(item, "auto_run_paused")
            return False
        if not self._default_sequence_id():
            self._last_error = "default_sequence_missing"
            if self._state != "running":
                self._state = "paused"
            self._on_failure(item, self._last_error, None)
            self._emit_status()
            return False

        self._pending.append(item)
        if self._state != "running":
            self._state = "queued"
        self._emit_status()
        return True

    def process_next(self) -> bool:
        if self._state in {"paused", "running"} or not self._pending:
            return False
        if not self._auto_run_enabled():
            self._last_error = "auto_run_disabled"
            self._on_failure(self._pending[0], self._last_error, None)
            self._emit_status()
            return False

        sequence_id = self._default_sequence_id()
        if not sequence_id:
            self._last_error = "default_sequence_missing"
            self._state = "paused"
            self._on_failure(self._pending[0], self._last_error, None)
            self._emit_status()
            return False

        item = self._pending.popleft()
        owned_window = self._pre_open_check(item)
        if owned_window is None:
            return self._pause_failed_item(item, "target_window_not_found")

        try:
            opened_context = self._open_raid(item, owned_window)
        except Exception as exc:
            return self._pause_failed_item(
                item,
                self._reason_from_exception(exc, "chrome_open_failed"),
            )

        self._state = "running"
        self._current_url = item.normalized_url
        self._last_error = None
        self._emit_status()

        try:
            succeeded, failure_reason = self._execute_raid(item, opened_context, sequence_id)
        except Exception as exc:
            return self._pause_failed_item(
                item,
                self._reason_from_exception(exc, "autorun_execution_failed"),
                opened_context,
            )

        if not succeeded:
            return self._pause_failed_item(
                item,
                failure_reason or "autorun_execution_failed",
                opened_context,
            )

        self._close_raid(opened_context)
        self._on_success(item, opened_context)
        self._current_url = None
        self._last_error = None
        self._state = "queued" if self._pending else "idle"
        self._emit_status()
        return True

    def _reject(self, item: PendingRaidWorkItem, reason: str) -> None:
        self._last_error = reason
        self._on_failure(item, reason, None)
        self._emit_status()

    def _pause_failed_item(
        self,
        item: PendingRaidWorkItem,
        reason: str,
        context: OpenedRaidContext | None = None,
    ) -> bool:
        self._state = "paused"
        self._current_url = None
        self._last_error = reason
        self._on_failure(item, reason, context)
        self._emit_status()
        return False

    def _emit_status(self) -> None:
        self._on_status(self._state, self.queue_length, self._current_url, self._last_error)

    def _reason_from_exception(self, exc: Exception, fallback: str) -> str:
        message = str(exc).strip()
        return message or fallback
