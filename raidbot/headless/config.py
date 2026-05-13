from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from raidbot.desktop.models import DesktopAppConfig
from raidbot.desktop.storage import DesktopStorage, default_base_dir
from raidbot.headless.models import HeadlessActionToggles, HeadlessSettings


class HeadlessConfigStore:
    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or default_base_dir()
        self.desktop_storage = DesktopStorage(self.base_dir)
        self.headless_dir = self.base_dir / "headless"
        self.settings_path = self.headless_dir / "config.json"
        self.auth_state_path = self.headless_dir / "auth-state.json"
        self.playwright_user_data_dir = self.headless_dir / "playwright-profile"

    def load_shared_config(self) -> DesktopAppConfig:
        return self.desktop_storage.load_config()

    def load_settings(self) -> HeadlessSettings:
        if not self.settings_path.exists():
            return HeadlessSettings()
        data = json.loads(self.settings_path.read_text(encoding="utf-8"))
        return self._settings_from_data(data)

    def save_settings(self, settings: HeadlessSettings) -> None:
        self.headless_dir.mkdir(parents=True, exist_ok=True)
        self.settings_path.write_text(
            json.dumps(self._settings_to_data(settings), indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def _settings_to_data(self, settings: HeadlessSettings) -> dict[str, Any]:
        return {
            "chrome_profile_directory": settings.chrome_profile_directory,
            "enabled_actions": {
                "reply": settings.enabled_actions.reply,
                "like": settings.enabled_actions.like,
                "repost": settings.enabled_actions.repost,
                "bookmark": settings.enabled_actions.bookmark,
            }
        }

    def _settings_from_data(self, data: dict[str, Any]) -> HeadlessSettings:
        enabled_actions = data.get("enabled_actions") or {}
        return HeadlessSettings(
            enabled_actions=HeadlessActionToggles(
                reply=bool(enabled_actions.get("reply", True)),
                like=bool(enabled_actions.get("like", True)),
                repost=bool(enabled_actions.get("repost", True)),
                bookmark=bool(enabled_actions.get("bookmark", True)),
            ),
            chrome_profile_directory=(
                str(data.get("chrome_profile_directory")).strip()
                if data.get("chrome_profile_directory") is not None
                and str(data.get("chrome_profile_directory")).strip()
                else None
            ),
        )
