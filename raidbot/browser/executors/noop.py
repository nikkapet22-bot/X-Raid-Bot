from __future__ import annotations

from typing import Any

from raidbot.browser.executors.base import RaidExecutor
from raidbot.browser.models import RaidActionJob, RaidExecutionResult


class NoOpRaidExecutor(RaidExecutor):
    name = "noop"

    def execute(self, job: RaidActionJob, session: Any) -> RaidExecutionResult:
        _ = (job, session)
        return RaidExecutionResult(kind="executor_not_configured", handed_off=True)
