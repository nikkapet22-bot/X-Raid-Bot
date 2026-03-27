from __future__ import annotations

from dataclasses import dataclass

from raidbot.browser.backends import (
    ControlledSessionBrowserBackend,
    LaunchOnlyBrowserBackend,
)
from raidbot.browser.executors import NoOpRaidExecutor, RaidExecutor
from raidbot.browser.models import (
    RaidActionJob,
    RaidActionRequirements,
    RaidExecutionResult,
)
from raidbot.browser.pipeline import BrowserPipeline


def build_job() -> RaidActionJob:
    return RaidActionJob(
        normalized_url="https://x.com/i/status/123",
        raw_url="https://x.com/i/status/123",
        chat_id=-1001,
        sender_id=42,
        requirements=RaidActionRequirements(
            like=True,
            repost=True,
            bookmark=False,
            reply=True,
        ),
        preset_replies=("gm",),
        trace_id="raid-1",
    )


class FakeBackend:
    def __init__(self, result: RaidExecutionResult) -> None:
        self.result = result
        self.calls: list[tuple[RaidActionJob, object | None]] = []

    def execute(
        self,
        job: RaidActionJob,
        executor: RaidExecutor,
        *,
        should_continue=None,
    ) -> RaidExecutionResult:
        self.calls.append((job, should_continue))
        return self.result


class FakeLauncher:
    def __init__(self, raises: Exception | None = None) -> None:
        self.raises = raises
        self.opened_urls: list[str] = []

    def open(self, url: str) -> None:
        if self.raises is not None:
            raise self.raises
        self.opened_urls.append(url)


class FakeSession:
    def __init__(
        self,
        *,
        ready: bool = True,
        navigate_error: Exception | None = None,
        close_error: Exception | None = None,
    ) -> None:
        self.ready = ready
        self.navigate_error = navigate_error
        self.close_error = close_error
        self.events: list[object] = []

    def navigate(self, url: str) -> None:
        self.events.append(("navigate", url))
        if self.navigate_error is not None:
            raise self.navigate_error

    def wait_until_ready(self) -> bool:
        self.events.append("wait_until_ready")
        return self.ready

    def close(self) -> None:
        self.events.append("close")
        if self.close_error is not None:
            raise self.close_error


@dataclass
class RecordingExecutor:
    result: RaidExecutionResult
    calls: list[tuple[RaidActionJob, FakeSession]]

    def __init__(self, result: RaidExecutionResult) -> None:
        self.result = result
        self.calls = []

    def execute(self, job: RaidActionJob, session: FakeSession) -> RaidExecutionResult:
        self.calls.append((job, session))
        return self.result


class TrackingDedupeStore:
    def __init__(self) -> None:
        self.mark_calls: list[str] = []
        self._seen: set[str] = set()

    def mark_if_new(self, url: str) -> bool:
        self.mark_calls.append(url)
        if url in self._seen:
            return False
        self._seen.add(url)
        return True


def _execute_and_mark_duplicate_boundary(
    pipeline: BrowserPipeline,
    job: RaidActionJob,
    dedupe_store: TrackingDedupeStore,
) -> RaidExecutionResult:
    result = pipeline.execute(job)
    if result.handed_off:
        dedupe_store.mark_if_new(job.normalized_url)
    return result


def test_pipeline_returns_backend_result_and_preserves_handoff_flag() -> None:
    job = build_job()
    backend = FakeBackend(
        RaidExecutionResult(kind="executor_not_configured", handed_off=True)
    )
    pipeline = BrowserPipeline(backend=backend, executor=NoOpRaidExecutor())

    result = pipeline.execute(job)

    assert result.kind == "executor_not_configured"
    assert result.handed_off is True
    assert backend.calls == [(job, None)]


def test_pipeline_passes_cancellation_callable_to_backend() -> None:
    job = build_job()
    backend = FakeBackend(
        RaidExecutionResult(kind="executor_not_configured", handed_off=True)
    )
    pipeline = BrowserPipeline(backend=backend, executor=NoOpRaidExecutor())

    def should_continue() -> bool:
        return True

    pipeline.execute(job, should_continue=should_continue)

    assert backend.calls == [(job, should_continue)]


def test_pipeline_omits_cancellation_callable_when_not_provided() -> None:
    job = build_job()

    class SimpleBackend:
        def __init__(self) -> None:
            self.calls: list[tuple[RaidActionJob, RaidExecutor]] = []

        def execute(
            self, job: RaidActionJob, executor: RaidExecutor
        ) -> RaidExecutionResult:
            self.calls.append((job, executor))
            return RaidExecutionResult(kind="executor_not_configured", handed_off=True)

    backend = SimpleBackend()
    executor = NoOpRaidExecutor()
    pipeline = BrowserPipeline(backend=backend, executor=executor)

    result = pipeline.execute(job)

    assert result.kind == "executor_not_configured"
    assert result.handed_off is True
    assert backend.calls == [(job, executor)]


def test_handoff_flag_controls_duplicate_marking_boundary() -> None:
    job = build_job()
    handed_off_backend = FakeBackend(
        RaidExecutionResult(kind="executor_not_configured", handed_off=True)
    )
    not_handed_off_backend = FakeBackend(
        RaidExecutionResult(kind="browser_startup_failure", handed_off=False)
    )
    handed_off_pipeline = BrowserPipeline(
        backend=handed_off_backend, executor=NoOpRaidExecutor()
    )
    not_handed_off_pipeline = BrowserPipeline(
        backend=not_handed_off_backend, executor=NoOpRaidExecutor()
    )
    dedupe_store = TrackingDedupeStore()

    failed_result = _execute_and_mark_duplicate_boundary(
        not_handed_off_pipeline, job, dedupe_store
    )
    first_handoff = _execute_and_mark_duplicate_boundary(
        handed_off_pipeline, job, dedupe_store
    )
    second_handoff = _execute_and_mark_duplicate_boundary(
        handed_off_pipeline, job, dedupe_store
    )

    assert failed_result.handed_off is False
    assert first_handoff.handed_off is True
    assert second_handoff.handed_off is True
    assert dedupe_store.mark_calls == [
        "https://x.com/i/status/123",
        "https://x.com/i/status/123",
    ]


def test_launch_only_backend_marks_handoff_when_launch_succeeds() -> None:
    job = build_job()
    backend = LaunchOnlyBrowserBackend(launcher=FakeLauncher())

    result = backend.execute(job, NoOpRaidExecutor())

    assert result.kind == "executor_not_configured"
    assert result.handed_off is True


def test_launch_only_backend_reports_startup_failure() -> None:
    job = build_job()
    backend = LaunchOnlyBrowserBackend(launcher=FakeLauncher(raises=RuntimeError("boom")))

    result = backend.execute(job, NoOpRaidExecutor())

    assert result.kind == "browser_startup_failure"
    assert result.handed_off is False


def test_noop_executor_returns_not_configured_result() -> None:
    executor = NoOpRaidExecutor()

    result = executor.execute(build_job(), session=object())

    assert result.kind == "executor_not_configured"
    assert result.handed_off is True


def test_controlled_session_backend_reports_browser_startup_failure() -> None:
    job = build_job()

    def raising_factory() -> FakeSession:
        raise RuntimeError("cannot create session")

    backend = ControlledSessionBrowserBackend(session_factory=raising_factory)

    result = backend.execute(job, NoOpRaidExecutor())

    assert result.kind == "browser_startup_failure"
    assert result.handed_off is False


def test_controlled_session_backend_reports_navigation_failure() -> None:
    job = build_job()
    session = FakeSession(navigate_error=RuntimeError("navigation failed"))
    backend = ControlledSessionBrowserBackend(session_factory=lambda: session)

    result = backend.execute(job, NoOpRaidExecutor())

    assert result.kind == "navigation_failure"
    assert result.handed_off is False
    assert session.events == [("navigate", job.normalized_url), "close"]


def test_controlled_session_backend_reports_page_ready_timeout() -> None:
    job = build_job()
    session = FakeSession(ready=False)
    backend = ControlledSessionBrowserBackend(session_factory=lambda: session)

    result = backend.execute(job, NoOpRaidExecutor())

    assert result.kind == "page_ready_timeout"
    assert result.handed_off is False
    assert session.events == [
        ("navigate", job.normalized_url),
        "wait_until_ready",
        "close",
    ]


def test_controlled_session_backend_skips_executor_when_cancelled_before_executor() -> None:
    job = build_job()
    session = FakeSession(ready=True)
    executor = RecordingExecutor(
        RaidExecutionResult(kind="executor_succeeded", handed_off=True)
    )
    backend = ControlledSessionBrowserBackend(session_factory=lambda: session)

    result = backend.execute(job, executor, should_continue=lambda: False)

    assert result.kind == "cancelled_before_executor"
    assert result.handed_off is False
    assert executor.calls == []
    assert session.events == [
        ("navigate", job.normalized_url),
        "wait_until_ready",
        "close",
    ]


def test_controlled_session_backend_passes_through_executor_result() -> None:
    job = build_job()
    session = FakeSession(ready=True)
    executor = RecordingExecutor(
        RaidExecutionResult(kind="executor_succeeded", handed_off=True)
    )
    backend = ControlledSessionBrowserBackend(session_factory=lambda: session)

    result = backend.execute(job, executor, should_continue=lambda: True)

    assert result.kind == "executor_succeeded"
    assert result.handed_off is True
    assert executor.calls == [(job, session)]
    assert session.events == [
        ("navigate", job.normalized_url),
        "wait_until_ready",
        "close",
    ]


def test_controlled_session_backend_reports_session_close_failure_after_handoff() -> None:
    job = build_job()
    session = FakeSession(ready=True, close_error=RuntimeError("close failed"))
    executor = RecordingExecutor(
        RaidExecutionResult(kind="executor_not_configured", handed_off=True)
    )
    backend = ControlledSessionBrowserBackend(session_factory=lambda: session)

    result = backend.execute(job, executor, should_continue=lambda: True)

    assert result.kind == "session_close_failure"
    assert result.handed_off is True
    assert executor.calls == [(job, session)]
    assert session.events == [
        ("navigate", job.normalized_url),
        "wait_until_ready",
        "close",
    ]
