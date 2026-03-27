from __future__ import annotations

from dataclasses import dataclass

from raidbot.chrome import ChromeOpener
from raidbot.dedupe import InMemoryOpenedUrlStore
from raidbot.service import RaidService
from raidbot.telegram_client import TelegramRaidListener


@dataclass
class Runtime:
    service: RaidService
    listener: TelegramRaidListener


def build_runtime(settings) -> Runtime:
    opener = ChromeOpener(
        chrome_path=settings.chrome_path,
        user_data_dir=settings.chrome_user_data_dir,
        profile_directory=settings.chrome_profile_directory,
    )
    service = RaidService(
        allowed_chat_ids=settings.telegram_chat_whitelist,
        allowed_sender_id=settings.raidar_sender_id,
        opener=opener,
        dedupe_store=InMemoryOpenedUrlStore(),
    )
    listener = TelegramRaidListener(
        api_id=settings.telegram_api_id,
        api_hash=settings.telegram_api_hash,
        session_path=str(settings.telegram_session_path),
        on_message=service.handle_message,
    )
    return Runtime(service=service, listener=listener)
