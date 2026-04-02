from __future__ import annotations

from pathlib import Path

from raidbot.desktop.models import DesktopAppConfig
from raidbot.desktop.storage import DesktopStorage
from raidbot.headless.models import HeadlessActionToggles, HeadlessSettings


def test_headless_config_loads_shared_desktop_config(tmp_path) -> None:
    from raidbot.headless.config import HeadlessConfigStore

    desktop_storage = DesktopStorage(tmp_path)
    desktop_storage.save_config(
        DesktopAppConfig(
            telegram_api_id=123456,
            telegram_api_hash="api-hash",
            telegram_session_path=Path("sessions/raid.session"),
            telegram_phone_number="+15555550123",
            whitelisted_chat_ids=[1001, 1002],
            allowed_sender_ids=[111, 222],
            allowed_sender_entries=("@raidar", "@delugeraidbot"),
            chrome_profile_directory="Default",
            preset_replies=("gm",),
        )
    )

    store = HeadlessConfigStore(tmp_path)
    shared = store.load_shared_config()

    assert shared.telegram_api_id == 123456
    assert shared.allowed_sender_ids == [111, 222]
    assert shared.whitelisted_chat_ids == [1001, 1002]
    assert shared.preset_replies == ("gm",)


def test_headless_config_defaults_enable_all_actions(tmp_path) -> None:
    from raidbot.headless.config import HeadlessConfigStore

    store = HeadlessConfigStore(tmp_path)

    settings = store.load_settings()

    assert settings == HeadlessSettings(
        enabled_actions=HeadlessActionToggles(
            reply=True,
            like=True,
            repost=True,
            bookmark=True,
        )
    )


def test_headless_config_round_trips_headless_only_settings(tmp_path) -> None:
    from raidbot.headless.config import HeadlessConfigStore

    store = HeadlessConfigStore(tmp_path)
    settings = HeadlessSettings(
        enabled_actions=HeadlessActionToggles(
            reply=False,
            like=True,
            repost=False,
            bookmark=True,
        )
    )

    store.save_settings(settings)

    loaded = store.load_settings()

    assert loaded == settings


def test_headless_config_uses_dedicated_playwright_profile_dir(tmp_path) -> None:
    from raidbot.headless.config import HeadlessConfigStore

    store = HeadlessConfigStore(tmp_path)

    assert store.playwright_user_data_dir == tmp_path / "headless" / "playwright-profile"
