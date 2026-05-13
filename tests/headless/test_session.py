from __future__ import annotations

from pathlib import Path

import pytest

from raidbot.desktop.chrome_profiles import ChromeEnvironment, ChromeProfile
from raidbot.headless.models import HeadlessAuthState


class _FakePage:
    def __init__(self) -> None:
        self.goto_calls: list[str] = []

    def goto(self, url: str) -> None:
        self.goto_calls.append(url)


class _FakeContext:
    def __init__(self, *, storage_state_error: Exception | None = None) -> None:
        self.page = _FakePage()
        self.pages = [self.page]
        self.closed = False
        self.storage_state_paths: list[str] = []
        self.storage_state_error = storage_state_error

    def new_page(self):
        self.page = _FakePage()
        self.pages.append(self.page)
        return self.page

    def close(self) -> None:
        self.closed = True

    def storage_state(self, *, path: str) -> dict[str, object]:
        self.storage_state_paths.append(path)
        if self.storage_state_error is not None:
            raise self.storage_state_error
        Path(path).write_text("{}", encoding="utf-8")
        return {}


class _FakeBrowser:
    def __init__(self) -> None:
        self.new_context_calls: list[str] = []
        self.context = _FakeContext()
        self.closed = False

    def new_context(self, *, storage_state: str):
        self.new_context_calls.append(storage_state)
        return self.context

    def close(self) -> None:
        self.closed = True


class _FakeChromium:
    def __init__(self, *, storage_state_error: Exception | None = None) -> None:
        self.persistent_calls: list[tuple[str, bool, str | None, tuple[str, ...]]] = []
        self.launch_calls: list[tuple[bool, str | None]] = []
        self.persistent_context = _FakeContext(storage_state_error=storage_state_error)
        self.browser = _FakeBrowser()

    def launch_persistent_context(
        self,
        user_data_dir: str,
        *,
        headless: bool,
        channel: str | None = None,
        args: list[str] | None = None,
    ):
        self.persistent_calls.append((user_data_dir, headless, channel, tuple(args or ())))
        Path(user_data_dir).mkdir(parents=True, exist_ok=True)
        return self.persistent_context

    def launch(self, *, headless: bool, channel: str | None = None):
        self.launch_calls.append((headless, channel))
        return self.browser


class _FakePlaywrightManager:
    def __init__(self, *, storage_state_error: Exception | None = None) -> None:
        self.chromium = _FakeChromium(storage_state_error=storage_state_error)
        self.exit_calls: list[tuple[object, object, object]] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.exit_calls.append((exc_type, exc, tb))
        return False


def test_session_bootstrap_launches_headed_persistent_context(tmp_path) -> None:
    from raidbot.headless.session import PlaywrightSessionManager

    playwright_manager = _FakePlaywrightManager()
    session_manager = PlaywrightSessionManager(
        user_data_dir=tmp_path / "profile",
        playwright_factory=lambda: playwright_manager,
    )

    session = session_manager.launch_bootstrap_context()

    assert playwright_manager.chromium.persistent_calls == [
        (str(tmp_path / "profile"), False, "chrome", ())
    ]
    assert session.page.goto_calls == ["https://x.com/home"]


def test_session_runtime_launches_headless_browser_with_imported_auth_state(
    tmp_path,
) -> None:
    from raidbot.headless.session import PlaywrightSessionManager

    auth_state_path = tmp_path / "headless" / "auth-state.json"
    auth_state_path.parent.mkdir(parents=True)
    auth_state_path.write_text("{}", encoding="utf-8")
    playwright_manager = _FakePlaywrightManager()
    session_manager = PlaywrightSessionManager(
        user_data_dir=tmp_path / "profile",
        auth_state_path=auth_state_path,
        playwright_factory=lambda: playwright_manager,
    )

    session = session_manager.open_runtime_session()

    assert playwright_manager.chromium.launch_calls == [(True, "chrome")]
    assert playwright_manager.chromium.browser.new_context_calls == [str(auth_state_path)]
    assert session.page.goto_calls == ["https://x.com/home"]


def test_session_auth_state_returns_authenticated_when_auth_artifact_exists(tmp_path) -> None:
    from raidbot.headless.session import PlaywrightSessionManager

    auth_state_path = tmp_path / "headless" / "auth-state.json"
    auth_state_path.parent.mkdir(parents=True)
    auth_state_path.write_text("{}", encoding="utf-8")
    session_manager = PlaywrightSessionManager(
        user_data_dir=tmp_path / "profile",
        auth_state_path=auth_state_path,
    )

    auth_state = session_manager.get_auth_state()

    assert auth_state == HeadlessAuthState(status="authenticated")


def test_session_auth_state_returns_needs_login_when_auth_artifact_missing(tmp_path) -> None:
    from raidbot.headless.session import PlaywrightSessionManager

    session_manager = PlaywrightSessionManager(
        user_data_dir=tmp_path / "profile",
        auth_state_path=tmp_path / "headless" / "auth-state.json",
    )

    auth_state = session_manager.get_auth_state()

    assert auth_state == HeadlessAuthState(
        status="needs_login",
        detail="x_auth_required",
    )


def test_session_auth_state_returns_authenticated_when_probe_passes(tmp_path) -> None:
    from raidbot.headless.session import PlaywrightSessionManager

    auth_state_path = tmp_path / "headless" / "auth-state.json"
    auth_state_path.parent.mkdir(parents=True)
    auth_state_path.write_text("{}", encoding="utf-8")
    playwright_manager = _FakePlaywrightManager()
    session_manager = PlaywrightSessionManager(
        user_data_dir=tmp_path / "profile",
        auth_state_path=auth_state_path,
        playwright_factory=lambda: playwright_manager,
        auth_probe=lambda _page: True,
    )

    auth_state = session_manager.get_auth_state()

    assert auth_state == HeadlessAuthState(status="authenticated")
    assert playwright_manager.chromium.launch_calls == [(True, "chrome")]


def test_session_auth_state_returns_needs_login_when_probe_fails(tmp_path) -> None:
    from raidbot.headless.session import PlaywrightSessionManager

    auth_state_path = tmp_path / "headless" / "auth-state.json"
    auth_state_path.parent.mkdir(parents=True)
    auth_state_path.write_text("{}", encoding="utf-8")
    playwright_manager = _FakePlaywrightManager()
    session_manager = PlaywrightSessionManager(
        user_data_dir=tmp_path / "profile",
        auth_state_path=auth_state_path,
        playwright_factory=lambda: playwright_manager,
        auth_probe=lambda _page: False,
    )

    auth_state = session_manager.get_auth_state()

    assert auth_state == HeadlessAuthState(
        status="needs_login",
        detail="x_auth_required",
    )


def test_session_close_releases_playwright_manager(tmp_path) -> None:
    from raidbot.headless.session import PlaywrightSessionManager

    playwright_manager = _FakePlaywrightManager()
    session_manager = PlaywrightSessionManager(
        user_data_dir=tmp_path / "profile",
        playwright_factory=lambda: playwright_manager,
    )

    session = session_manager.launch_bootstrap_context()
    session.close()

    assert playwright_manager.chromium.persistent_context.closed is True
    assert playwright_manager.exit_calls == [(None, None, None)]


def test_session_import_auth_uses_desktop_profile_and_writes_headless_auth_state(
    tmp_path,
) -> None:
    from raidbot.headless.session import PlaywrightSessionManager

    chrome_user_data_dir = tmp_path / "chrome-user-data"
    (chrome_user_data_dir / "Profile 3").mkdir(parents=True)
    auth_state_path = tmp_path / "headless" / "auth-state.json"
    playwright_manager = _FakePlaywrightManager()
    chrome_environment = ChromeEnvironment(
        chrome_path=tmp_path / "Chrome" / "chrome.exe",
        user_data_dir=chrome_user_data_dir,
        profiles=[ChromeProfile(directory_name="Profile 3", label="Raid")],
    )
    session_manager = PlaywrightSessionManager(
        user_data_dir=tmp_path / "profile",
        auth_state_path=auth_state_path,
        playwright_factory=lambda: playwright_manager,
        chrome_environment_factory=lambda: chrome_environment,
        chrome_process_check=lambda: False,
    )

    auth_state = session_manager.import_auth_from_desktop_profile("Profile 3")

    assert playwright_manager.chromium.persistent_calls == [
        (
            str(chrome_user_data_dir),
            False,
            "chrome",
            ("--profile-directory=Profile 3",),
        )
    ]
    assert auth_state_path.exists()
    assert auth_state == HeadlessAuthState(status="authenticated")


def test_session_import_auth_refuses_when_chrome_is_running(tmp_path) -> None:
    from raidbot.headless.session import PlaywrightSessionManager

    session_manager = PlaywrightSessionManager(
        user_data_dir=tmp_path / "profile",
        auth_state_path=tmp_path / "headless" / "auth-state.json",
        chrome_process_check=lambda: True,
    )

    with pytest.raises(RuntimeError, match="Close Google Chrome before importing X auth"):
        session_manager.import_auth_from_desktop_profile("Profile 3")


def test_session_import_auth_failure_preserves_existing_auth_artifact(tmp_path) -> None:
    from raidbot.headless.session import PlaywrightSessionManager

    chrome_user_data_dir = tmp_path / "chrome-user-data"
    (chrome_user_data_dir / "Profile 3").mkdir(parents=True)
    auth_state_path = tmp_path / "headless" / "auth-state.json"
    auth_state_path.parent.mkdir(parents=True)
    auth_state_path.write_text('{"cookies":["old"]}', encoding="utf-8")
    playwright_manager = _FakePlaywrightManager(
        storage_state_error=RuntimeError("import_failed")
    )
    chrome_environment = ChromeEnvironment(
        chrome_path=tmp_path / "Chrome" / "chrome.exe",
        user_data_dir=chrome_user_data_dir,
        profiles=[ChromeProfile(directory_name="Profile 3", label="Raid")],
    )
    session_manager = PlaywrightSessionManager(
        user_data_dir=tmp_path / "profile",
        auth_state_path=auth_state_path,
        playwright_factory=lambda: playwright_manager,
        chrome_environment_factory=lambda: chrome_environment,
        chrome_process_check=lambda: False,
    )

    with pytest.raises(RuntimeError, match="import_failed"):
        session_manager.import_auth_from_desktop_profile("Profile 3")

    assert auth_state_path.read_text(encoding="utf-8") == '{"cookies":["old"]}'
