from __future__ import annotations

from raidbot.browser.backends import BrowserBackend, ShouldContinue
from raidbot.browser.executors.base import RaidExecutor
from raidbot.browser.models import RaidActionJob, RaidExecutionResult


class BrowserPipeline:
    def __init__(self, backend: BrowserBackend, executor: RaidExecutor) -> None:
        self._backend = backend
        self._executor = executor
        self.executor_name = getattr(executor, "name", executor.__class__.__name__)

    def execute(
        self,
        job: RaidActionJob,
        *,
        should_continue: ShouldContinue | None = None,
    ) -> RaidExecutionResult:
        if should_continue is None:
            return self._backend.execute(job, self._executor)
        return self._backend.execute(
            job,
            self._executor,
            should_continue=should_continue,
        )
