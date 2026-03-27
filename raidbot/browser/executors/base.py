from __future__ import annotations

from typing import Any, Protocol

from raidbot.browser.models import RaidActionJob, RaidExecutionResult


class RaidExecutor(Protocol):
    def execute(self, job: RaidActionJob, session: Any) -> RaidExecutionResult:
        ...
