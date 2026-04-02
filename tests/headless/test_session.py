from __future__ import annotations

from pathlib import Path

from raidbot.headless.models import HeadlessAuthState


class _FakePage:
    def __init__(self) -> None:
        self.goto_calls: list[str] = []

    def goto(self, url: str) -> None:
        self.goto_calls.append(url)


class _FakeContext:
    def __init__(self) -> None:
        self.page = _FakePage()
        self.pages = [self.page]
        self.closed = False

    def new_page(self):
        self.page = _FakePage()
        self.pages.append(self.page)
        return self.page

    def close(self) -> None:
        self.closed = True


class _FakeChromium:
    def __init__(self) -> None:
        self.calls: list[tuple[str, bool]] = []
        self.context = _FakeContext()

    def launch_persistent_context(self, user_data_dir: str, *, headless: bool):
        self.calls.append((user_data_dir, headless))
        Path(user_data_dir).mkdir(parents=True, exist_ok=True)
        return self.context


class _FakePlaywrightManager:
    def __init__(self) -> None:
        self.chromium = _FakeChromium()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_session_bootstrap_launches_headed_persistent_context(tmp_path) -> None:
    from raidbot.headless.session import PlaywrightSessionManager

    playwright_manager = _FakePlaywrightManager()
    session_manager = PlaywrightSessionManager(
        user_data_dir=tmp_path / "profile",
        playwright_factory=lambda: playwright_manager,
    )

    session = session_manager.launch_bootstrap_context()

    assert playwright_manager.chromium.calls == [
        (str(tmp_path / "profile"), False)
    ]
    assert session.page.goto_calls == ["https://x.com/home"]


def test_session_auth_state_returns_authenticated_when_probe_passes(tmp_path) -> None:
    from raidbot.headless.session import PlaywrightSessionManager

    playwright_manager = _FakePlaywrightManager()
    session_manager = PlaywrightSessionManager(
        user_data_dir=tmp_path / "profile",
        playwright_factory=lambda: playwright_manager,
        auth_probe=lambda _page: True,
    )

    auth_state = session_manager.get_auth_state()

    assert auth_state == HeadlessAuthState(status="authenticated")


def test_session_auth_state_returns_needs_login_when_probe_fails(tmp_path) -> None:
    from raidbot.headless.session import PlaywrightSessionManager

    playwright_manager = _FakePlaywrightManager()
    session_manager = PlaywrightSessionManager(
        user_data_dir=tmp_path / "profile",
        playwright_factory=lambda: playwright_manager,
        auth_probe=lambda _page: False,
    )

    auth_state = session_manager.get_auth_state()

    assert auth_state == HeadlessAuthState(
        status="needs_login",
        detail="x_auth_required",
    )
