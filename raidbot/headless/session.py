from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
from typing import Any, Callable

from raidbot.desktop.chrome_profiles import detect_chrome_environment
from raidbot.headless.models import HeadlessAuthState


def _default_playwright_factory():
    from playwright.sync_api import sync_playwright

    return sync_playwright()


def _is_chrome_running() -> bool:
    try:
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq chrome.exe"],
            capture_output=True,
            text=True,
            check=False,
            creationflags=creation_flags,
        )
    except Exception:
        return False
    output = f"{result.stdout or ''}\n{result.stderr or ''}".lower()
    return "chrome.exe" in output


@dataclass
class HeadlessBrowserSession:
    context: Any
    page: Any
    browser: Any | None = None
    playwright_manager: Any | None = None
    _closed: bool = False

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self.context.close()
        finally:
            try:
                if self.browser is not None:
                    self.browser.close()
            finally:
                if self.playwright_manager is not None:
                    self.playwright_manager.__exit__(None, None, None)


class PlaywrightSessionManager:
    def __init__(
        self,
        *,
        user_data_dir: Path,
        auth_state_path: Path | None = None,
        playwright_factory: Callable[[], Any] | None = None,
        chrome_environment_factory: Callable[[], Any] | None = None,
        chrome_process_check: Callable[[], bool] | None = None,
        auth_probe: Callable[[Any], bool] | None = None,
        start_url: str = "https://x.com/home",
        browser_channel: str = "chrome",
    ) -> None:
        self.user_data_dir = user_data_dir
        self.auth_state_path = Path(auth_state_path) if auth_state_path is not None else (
            self.user_data_dir.parent / "auth-state.json"
        )
        self._playwright_factory = playwright_factory or _default_playwright_factory
        self._chrome_environment_factory = (
            chrome_environment_factory or detect_chrome_environment
        )
        self._chrome_process_check = chrome_process_check or _is_chrome_running
        self._auth_probe = auth_probe
        self._start_url = start_url
        self._browser_channel = browser_channel

    def launch_bootstrap_context(self) -> HeadlessBrowserSession:
        return self._launch_persistent_session(headless=False, user_data_dir=self.user_data_dir)

    def open_runtime_session(self) -> HeadlessBrowserSession:
        if not self._has_auth_artifact():
            raise RuntimeError("x_auth_required")
        playwright_manager = self._playwright_factory()
        playwright = playwright_manager.__enter__()
        browser = playwright.chromium.launch(
            headless=True,
            channel=self._browser_channel,
        )
        context = browser.new_context(storage_state=str(self.auth_state_path))
        page = context.new_page()
        page.goto(self._start_url)
        return HeadlessBrowserSession(
            context=context,
            page=page,
            browser=browser,
            playwright_manager=playwright_manager,
        )

    def get_auth_state(self) -> HeadlessAuthState:
        if not self._has_auth_artifact():
            return HeadlessAuthState(status="needs_login", detail="x_auth_required")
        if self._auth_probe is None:
            return HeadlessAuthState(status="authenticated")

        session = self.open_runtime_session()
        try:
            if self._auth_probe(session.page):
                return HeadlessAuthState(status="authenticated")
            return HeadlessAuthState(status="needs_login", detail="x_auth_required")
        finally:
            session.close()

    def import_auth_from_desktop_profile(self, profile_directory: str) -> HeadlessAuthState:
        if self._chrome_process_check():
            raise RuntimeError("Close Google Chrome before importing X auth")
        chrome_environment = self._chrome_environment_factory()
        profile_directory = str(profile_directory).strip()
        if not any(
            profile.directory_name == profile_directory
            for profile in getattr(chrome_environment, "profiles", ())
        ):
            raise RuntimeError(f"Chrome profile not found: {profile_directory}")
        profile_path = Path(chrome_environment.user_data_dir) / profile_directory
        if not profile_path.exists():
            raise RuntimeError(f"Chrome profile directory not found: {profile_path}")

        self.auth_state_path.parent.mkdir(parents=True, exist_ok=True)
        temp_auth_state_path = self.auth_state_path.with_suffix(".tmp.json")
        if temp_auth_state_path.exists():
            temp_auth_state_path.unlink()

        session = self._launch_persistent_session(
            headless=False,
            user_data_dir=Path(chrome_environment.user_data_dir),
            args=[f"--profile-directory={profile_directory}"],
            start_url="",
        )
        try:
            session.context.storage_state(path=str(temp_auth_state_path))
            temp_auth_state_path.replace(self.auth_state_path)
        except Exception:
            if temp_auth_state_path.exists():
                temp_auth_state_path.unlink()
            raise
        finally:
            session.close()

        return self.get_auth_state()

    def _launch_persistent_session(
        self,
        *,
        headless: bool,
        user_data_dir: Path,
        args: list[str] | None = None,
        start_url: str | None = None,
    ) -> HeadlessBrowserSession:
        user_data_dir.mkdir(parents=True, exist_ok=True)
        playwright_manager = self._playwright_factory()
        playwright = playwright_manager.__enter__()
        context = playwright.chromium.launch_persistent_context(
            str(user_data_dir),
            headless=headless,
            channel=self._browser_channel,
            args=args or [],
        )
        page = context.pages[0] if getattr(context, "pages", []) else context.new_page()
        target_url = self._start_url if start_url is None else start_url
        if target_url:
            page.goto(target_url)
        return HeadlessBrowserSession(
            context=context,
            page=page,
            playwright_manager=playwright_manager,
        )

    def _has_auth_artifact(self) -> bool:
        return self.auth_state_path.exists() and self.auth_state_path.stat().st_size > 0
