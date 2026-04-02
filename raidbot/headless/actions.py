from __future__ import annotations

from typing import Any

from raidbot.browser.models import RaidActionJob


class PlaywrightXActionExecutor:
    def execute(
        self,
        page: Any,
        job: RaidActionJob,
        action_names: tuple[str, ...],
    ) -> tuple[str, ...]:
        page.goto(job.normalized_url)
        completed: list[str] = []
        for action_name in action_names:
            handler = getattr(self, f"_do_{action_name}", None)
            if handler is None:
                raise RuntimeError(f"unsupported_action:{action_name}")
            handler(page, job)
            completed.append(action_name)
        return tuple(completed)

    def _do_reply(self, page: Any, job: RaidActionJob) -> None:
        reply_text = job.preset_replies[0] if job.preset_replies else "gm"
        page.get_by_test_id("reply").click()
        page.locator('[data-testid="tweetTextarea_0"]').fill(reply_text)
        page.get_by_test_id("tweetButton").click()

    def _do_like(self, page: Any, _job: RaidActionJob) -> None:
        page.get_by_test_id("like").click()

    def _do_repost(self, page: Any, _job: RaidActionJob) -> None:
        page.get_by_test_id("retweet").click()
        page.get_by_role("menuitem", name="Repost").click()

    def _do_bookmark(self, page: Any, _job: RaidActionJob) -> None:
        page.get_by_test_id("bookmark").click()
