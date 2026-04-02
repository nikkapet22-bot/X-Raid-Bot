from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from raidbot.headless.models import HeadlessAuthState


def _default_playwright_factory():
    from playwright.sync_api import sync_playwright

    return sync_playwright()


@dataclass
class HeadlessBrowserSession:
    context: Any
    page: Any

    def close(self) -> None:
        self.context.close()


class PlaywrightSessionManager:
    def __init__(
        self,
        *,
        user_data_dir: Path,
        playwright_factory: Callable[[], Any] | None = None,
        auth_probe: Callable[[Any], bool] | None = None,
        start_url: str = "https://x.com/home",
    ) -> None:
        self.user_data_dir = user_data_dir
        self._playwright_factory = playwright_factory or _default_playwright_factory
        self._auth_probe = auth_probe
        self._start_url = start_url

    def launch_bootstrap_context(self) -> HeadlessBrowserSession:
        return self._launch_persistent_session(headless=False)

    def open_runtime_session(self) -> HeadlessBrowserSession:
        return self._launch_persistent_session(headless=True)

    def get_auth_state(self) -> HeadlessAuthState:
        if self._auth_probe is None:
            has_state = self.user_data_dir.exists() and any(self.user_data_dir.iterdir())
            if has_state:
                return HeadlessAuthState(status="authenticated")
            return HeadlessAuthState(status="needs_login", detail="x_auth_required")

        session = self.open_runtime_session()
        try:
            if self._auth_probe(session.page):
                return HeadlessAuthState(status="authenticated")
            return HeadlessAuthState(status="needs_login", detail="x_auth_required")
        finally:
            session.close()

    def _launch_persistent_session(self, *, headless: bool) -> HeadlessBrowserSession:
        self.user_data_dir.mkdir(parents=True, exist_ok=True)
        playwright_manager = self._playwright_factory()
        playwright = playwright_manager.__enter__()
        context = playwright.chromium.launch_persistent_context(
            str(self.user_data_dir),
            headless=headless,
        )
        page = context.pages[0] if getattr(context, "pages", []) else context.new_page()
        page.goto(self._start_url)
        return HeadlessBrowserSession(context=context, page=page)
