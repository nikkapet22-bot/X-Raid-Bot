from __future__ import annotations

from pathlib import Path

from raidbot.browser.models import RaidActionJob
from raidbot.desktop.models import DesktopAppConfig
from raidbot.desktop.storage import DesktopStorage
from raidbot.models import IncomingMessage


def test_headless_listener_emits_job_from_shared_configured_filtering(tmp_path) -> None:
    from raidbot.headless.config import HeadlessConfigStore
    from raidbot.headless.listener import HeadlessRaidListenerAdapter

    DesktopStorage(tmp_path).save_config(
        DesktopAppConfig(
            telegram_api_id=123456,
            telegram_api_hash="api-hash",
            telegram_session_path=Path("sessions/raid.session"),
            telegram_phone_number="+15555550123",
            whitelisted_chat_ids=[1001],
            allowed_sender_ids=[424242],
            allowed_sender_entries=("@raidar",),
            chrome_profile_directory="Default",
            preset_replies=("gm",),
            default_action_like=True,
            default_action_repost=True,
            default_action_reply=False,
            default_action_bookmark=False,
        )
    )
    store = HeadlessConfigStore(tmp_path)
    seen_jobs: list[RaidActionJob] = []
    listener = HeadlessRaidListenerAdapter(
        shared_config=store.load_shared_config(),
        on_job=seen_jobs.append,
    )

    result = listener.handle_message(
        IncomingMessage(
            chat_id=1001,
            sender_id=424242,
            text="Like + repost x.com/i/status/12345",
            has_video=True,
        )
    )

    assert result.kind == "job_detected"
    assert len(seen_jobs) == 1
    assert seen_jobs[0].normalized_url == "https://x.com/i/status/12345"


def test_headless_listener_ignores_non_matching_messages(tmp_path) -> None:
    from raidbot.headless.config import HeadlessConfigStore
    from raidbot.headless.listener import HeadlessRaidListenerAdapter

    DesktopStorage(tmp_path).save_config(
        DesktopAppConfig(
            telegram_api_id=123456,
            telegram_api_hash="api-hash",
            telegram_session_path=Path("sessions/raid.session"),
            telegram_phone_number="+15555550123",
            whitelisted_chat_ids=[1001],
            allowed_sender_ids=[424242],
            allowed_sender_entries=("@raidar",),
            chrome_profile_directory="Default",
        )
    )
    store = HeadlessConfigStore(tmp_path)
    seen_jobs: list[RaidActionJob] = []
    listener = HeadlessRaidListenerAdapter(
        shared_config=store.load_shared_config(),
        on_job=seen_jobs.append,
    )

    result = listener.handle_message(
        IncomingMessage(
            chat_id=1001,
            sender_id=999999,
            text="x.com/i/status/12345",
            has_video=True,
        )
    )

    assert result.kind == "sender_rejected"
    assert seen_jobs == []


def test_headless_listener_builds_real_listener_from_shared_credentials(tmp_path) -> None:
    from raidbot.headless.config import HeadlessConfigStore
    from raidbot.headless.listener import HeadlessRaidListenerAdapter

    captured_kwargs = {}

    class FakeListener:
        def __init__(self, **kwargs):
            captured_kwargs.update(kwargs)

    DesktopStorage(tmp_path).save_config(
        DesktopAppConfig(
            telegram_api_id=123456,
            telegram_api_hash="api-hash",
            telegram_session_path=Path("sessions/raid.session"),
            telegram_phone_number="+15555550123",
            whitelisted_chat_ids=[1001],
            allowed_sender_ids=[424242],
            allowed_sender_entries=("@raidar",),
            chrome_profile_directory="Default",
        )
    )
    store = HeadlessConfigStore(tmp_path)
    listener = HeadlessRaidListenerAdapter(
        shared_config=store.load_shared_config(),
        on_job=lambda _job: None,
        listener_factory=FakeListener,
    )

    listener.build_listener()

    assert captured_kwargs["api_id"] == 123456
    assert captured_kwargs["api_hash"] == "api-hash"
    assert captured_kwargs["session_path"].endswith("sessions\\raid.session")
