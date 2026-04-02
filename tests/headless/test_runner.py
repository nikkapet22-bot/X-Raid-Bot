from __future__ import annotations

from raidbot.browser.models import RaidActionJob, RaidActionRequirements
from raidbot.headless.models import HeadlessActionToggles, HeadlessAuthState, HeadlessRunResult


class _FakePage:
    pass


class _FakeSession:
    def __init__(self) -> None:
        self.page = _FakePage()
        self.closed = False

    def close(self) -> None:
        self.closed = True


class _FakeSessionManager:
    def __init__(self, auth_state: HeadlessAuthState) -> None:
        self.auth_state = auth_state
        self.session = _FakeSession()
        self.open_calls = 0

    def get_auth_state(self) -> HeadlessAuthState:
        return self.auth_state

    def open_runtime_session(self):
        self.open_calls += 1
        return self.session


class _FakeActionExecutor:
    def __init__(self, failure_on: str | None = None) -> None:
        self.failure_on = failure_on
        self.calls: list[tuple[str, ...]] = []

    def execute(self, page, job: RaidActionJob, action_names: tuple[str, ...]) -> tuple[str, ...]:
        self.calls.append(action_names)
        if self.failure_on is not None:
            raise RuntimeError(self.failure_on)
        return action_names


def _build_job() -> RaidActionJob:
    return RaidActionJob(
        normalized_url="https://x.com/i/status/123",
        raw_url="x.com/i/status/123",
        chat_id=1001,
        sender_id=999,
        requirements=RaidActionRequirements(
            reply=True,
            like=True,
            repost=True,
            bookmark=True,
        ),
        preset_replies=("gm",),
        trace_id="raid-1",
    )


def test_runner_executes_enabled_actions_in_order() -> None:
    from raidbot.headless.runner import HeadlessRaidRunner

    session_manager = _FakeSessionManager(HeadlessAuthState(status="authenticated"))
    action_executor = _FakeActionExecutor()
    runner = HeadlessRaidRunner(
        session_manager=session_manager,
        action_executor=action_executor,
        enabled_actions=HeadlessActionToggles(
            reply=True,
            like=True,
            repost=False,
            bookmark=True,
        ),
    )

    result = runner.run(_build_job())

    assert result == HeadlessRunResult(
        url="https://x.com/i/status/123",
        success=True,
        reason="completed",
        completed_actions=("reply", "like", "bookmark"),
    )
    assert action_executor.calls == [("reply", "like", "bookmark")]
    assert session_manager.session.closed is True


def test_runner_returns_auth_failure_when_x_login_missing() -> None:
    from raidbot.headless.runner import HeadlessRaidRunner

    session_manager = _FakeSessionManager(
        HeadlessAuthState(status="needs_login", detail="x_auth_required")
    )
    action_executor = _FakeActionExecutor()
    runner = HeadlessRaidRunner(
        session_manager=session_manager,
        action_executor=action_executor,
        enabled_actions=HeadlessActionToggles(),
    )

    result = runner.run(_build_job())

    assert result == HeadlessRunResult(
        url="https://x.com/i/status/123",
        success=False,
        reason="x_auth_required",
        completed_actions=(),
    )
    assert session_manager.open_calls == 0


def test_runner_returns_structured_failure_when_action_execution_breaks() -> None:
    from raidbot.headless.runner import HeadlessRaidRunner

    session_manager = _FakeSessionManager(HeadlessAuthState(status="authenticated"))
    action_executor = _FakeActionExecutor(failure_on="like_button_not_found")
    runner = HeadlessRaidRunner(
        session_manager=session_manager,
        action_executor=action_executor,
        enabled_actions=HeadlessActionToggles(),
    )

    result = runner.run(_build_job())

    assert result == HeadlessRunResult(
        url="https://x.com/i/status/123",
        success=False,
        reason="like_button_not_found",
        completed_actions=(),
    )
    assert session_manager.session.closed is True
