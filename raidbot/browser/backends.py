from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from raidbot.browser.executors.base import RaidExecutor
from raidbot.browser.models import RaidActionJob, RaidExecutionResult


ShouldContinue = Callable[[], bool]


class BrowserSession(Protocol):
    def navigate(self, url: str) -> None:
        ...

    def wait_until_ready(self) -> bool:
        ...

    def close(self) -> None:
        ...


class BrowserBackend(Protocol):
    def execute(self, job: RaidActionJob, executor: RaidExecutor) -> RaidExecutionResult:
        ...


class BrowserLauncher(Protocol):
    def open(self, url: str) -> None:
        ...


class LaunchOnlyBrowserBackend:
    def __init__(self, launcher: BrowserLauncher) -> None:
        self._launcher = launcher

    def execute(
        self,
        job: RaidActionJob,
        executor: RaidExecutor,
        *,
        should_continue: ShouldContinue | None = None,
    ) -> RaidExecutionResult:
        _ = (executor, should_continue)
        try:
            self._launcher.open(job.normalized_url)
        except Exception:
            return RaidExecutionResult(kind="browser_startup_failure", handed_off=False)
        return RaidExecutionResult(kind="executor_not_configured", handed_off=True)


class ControlledSessionBrowserBackend:
    def __init__(self, session_factory: Callable[[], BrowserSession]) -> None:
        self._session_factory = session_factory

    def execute(
        self,
        job: RaidActionJob,
        executor: RaidExecutor,
        *,
        should_continue: ShouldContinue | None = None,
    ) -> RaidExecutionResult:
        try:
            session = self._session_factory()
        except Exception:
            return RaidExecutionResult(kind="browser_startup_failure", handed_off=False)

        try:
            session.navigate(job.normalized_url)
        except Exception:
            return self._close_with_fallback(
                session,
                RaidExecutionResult(kind="navigation_failure", handed_off=False),
            )

        try:
            page_ready = session.wait_until_ready()
        except Exception:
            page_ready = False

        if not page_ready:
            return self._close_with_fallback(
                session,
                RaidExecutionResult(kind="page_ready_timeout", handed_off=False),
            )

        if should_continue is not None and not should_continue():
            return self._close_with_fallback(
                session,
                RaidExecutionResult(kind="cancelled_before_executor", handed_off=False),
            )

        try:
            execution_result = executor.execute(job, session)
        except Exception:
            execution_result = RaidExecutionResult(kind="executor_failed", handed_off=True)

        return self._close_with_fallback(session, execution_result)

    def _close_with_fallback(
        self,
        session: BrowserSession,
        result: RaidExecutionResult,
    ) -> RaidExecutionResult:
        try:
            session.close()
        except Exception:
            return RaidExecutionResult(
                kind="session_close_failure",
                handed_off=result.handed_off,
            )
        return result
