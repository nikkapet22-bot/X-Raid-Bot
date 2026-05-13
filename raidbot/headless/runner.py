from __future__ import annotations

from raidbot.browser.models import RaidActionJob
from raidbot.headless.models import (
    HeadlessActionToggles,
    HeadlessAuthState,
    HeadlessRunResult,
)


class HeadlessRaidRunner:
    def __init__(
        self,
        *,
        session_manager,
        action_executor,
        enabled_actions: HeadlessActionToggles,
    ) -> None:
        self._session_manager = session_manager
        self._action_executor = action_executor
        self._enabled_actions = enabled_actions
        self._busy = False

    def set_enabled_actions(self, enabled_actions: HeadlessActionToggles) -> None:
        self._enabled_actions = enabled_actions

    def run(self, job: RaidActionJob) -> HeadlessRunResult:
        if self._busy:
            return HeadlessRunResult(
                url=job.normalized_url,
                success=False,
                reason="runner_busy",
                completed_actions=(),
            )
        if job.requirements.reply:
            return HeadlessRunResult(
                url=job.normalized_url,
                success=False,
                reason="unsupported_for_now",
                completed_actions=(),
            )
        auth_state: HeadlessAuthState = self._session_manager.get_auth_state()
        if auth_state.status != "authenticated":
            return HeadlessRunResult(
                url=job.normalized_url,
                success=False,
                reason=auth_state.detail or auth_state.status,
                completed_actions=(),
            )
        self._busy = True
        session = self._session_manager.open_runtime_session()
        try:
            action_names = self._resolve_actions(job)
            completed = self._action_executor.execute(session.page, job, action_names)
            return HeadlessRunResult(
                url=job.normalized_url,
                success=True,
                reason="completed",
                completed_actions=completed,
            )
        except Exception as exc:
            return HeadlessRunResult(
                url=job.normalized_url,
                success=False,
                reason=str(exc).strip() or "headless_execution_failed",
                completed_actions=(),
            )
        finally:
            session.close()
            self._busy = False

    def _resolve_actions(self, job: RaidActionJob) -> tuple[str, ...]:
        action_names: list[str] = []
        if job.requirements.reply and self._enabled_actions.reply:
            action_names.append("reply")
        if job.requirements.like and self._enabled_actions.like:
            action_names.append("like")
        if job.requirements.repost and self._enabled_actions.repost:
            action_names.append("repost")
        if job.requirements.bookmark and self._enabled_actions.bookmark:
            action_names.append("bookmark")
        return tuple(action_names)
