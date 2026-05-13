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


def _build_job(*, require_reply: bool = False) -> RaidActionJob:
    return RaidActionJob(
        normalized_url="https://x.com/i/status/123",
        raw_url="x.com/i/status/123",
        chat_id=1001,
        sender_id=999,
        requirements=RaidActionRequirements(
            reply=require_reply,
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
        completed_actions=("like", "bookmark"),
    )
    assert action_executor.calls == [("like", "bookmark")]
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


def test_runner_skips_reply_required_raid_as_unsupported_for_now() -> None:
    from raidbot.headless.runner import HeadlessRaidRunner

    session_manager = _FakeSessionManager(HeadlessAuthState(status="authenticated"))
    action_executor = _FakeActionExecutor()
    runner = HeadlessRaidRunner(
        session_manager=session_manager,
        action_executor=action_executor,
        enabled_actions=HeadlessActionToggles(),
    )

    result = runner.run(_build_job(require_reply=True))

    assert result == HeadlessRunResult(
        url="https://x.com/i/status/123",
        success=False,
        reason="unsupported_for_now",
        completed_actions=(),
    )
    assert action_executor.calls == []
    assert session_manager.open_calls == 0


class _FakeLocator:
    def __init__(self, label: str, calls: list[tuple[str, str]]) -> None:
        self.label = label
        self.calls = calls

    def click(self) -> None:
        self.calls.append((self.label, "click"))


class _FakeActionPage:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.goto_calls: list[str] = []

    def goto(self, url: str) -> None:
        self.goto_calls.append(url)

    def get_by_test_id(self, test_id: str) -> _FakeLocator:
        self.calls.append(("get_by_test_id", test_id))
        return _FakeLocator(f"test_id:{test_id}", self.calls)

    def get_by_role(self, role: str, *, name: str) -> _FakeLocator:
        self.calls.append(("get_by_role", f"{role}:{name}"))
        return _FakeLocator(f"role:{role}:{name}", self.calls)


def test_action_executor_uses_expected_like_repost_bookmark_locator_flow() -> None:
    from raidbot.headless.actions import PlaywrightXActionExecutor

    page = _FakeActionPage()
    executor = PlaywrightXActionExecutor()

    completed = executor.execute(
        page,
        _build_job(),
        ("like", "repost", "bookmark"),
    )

    assert completed == ("like", "repost", "bookmark")
    assert page.goto_calls == ["https://x.com/i/status/123"]
    assert page.calls == [
        ("get_by_test_id", "like"),
        ("test_id:like", "click"),
        ("get_by_test_id", "retweet"),
        ("test_id:retweet", "click"),
        ("get_by_role", "menuitem:Repost"),
        ("role:menuitem:Repost", "click"),
        ("get_by_test_id", "bookmark"),
        ("test_id:bookmark", "click"),
    ]
