from __future__ import annotations

from collections.abc import Callable

from raidbot.browser.models import RaidActionRequirements, RaidDetectionResult
from raidbot.dedupe import InMemoryOpenedUrlStore
from raidbot.desktop.models import DesktopAppConfig
from raidbot.models import IncomingMessage, RaidActionJob
from raidbot.service import RaidService
from raidbot.telegram_client import TelegramRaidListener


class HeadlessRaidListenerAdapter:
    def __init__(
        self,
        *,
        shared_config: DesktopAppConfig,
        on_job: Callable[[RaidActionJob], None],
        listener_factory=TelegramRaidListener,
        dedupe_store=None,
    ) -> None:
        self.shared_config = shared_config
        self._on_job = on_job
        self._on_detection = None
        self._listener_factory = listener_factory
        self._service = RaidService(
            allowed_chat_ids=set(shared_config.whitelisted_chat_ids),
            allowed_sender_ids=set(shared_config.allowed_sender_ids),
            dedupe_store=dedupe_store or InMemoryOpenedUrlStore(),
            preset_replies=shared_config.preset_replies,
            default_requirements=RaidActionRequirements(
                like=shared_config.default_action_like,
                repost=shared_config.default_action_repost,
                bookmark=shared_config.default_action_bookmark,
                reply=shared_config.default_action_reply,
            ),
        )

    def handle_message(self, message: IncomingMessage) -> RaidDetectionResult:
        result = self._service.handle_message(message)
        if self._on_detection is not None:
            self._on_detection(result)
        if result.kind == "job_detected" and result.job is not None:
            self._on_job(result.job)
        return result

    def set_job_consumer(self, on_job: Callable[[RaidActionJob], None]) -> None:
        self._on_job = on_job

    def set_detection_callback(self, callback: Callable[[RaidDetectionResult], None]) -> None:
        self._on_detection = callback

    def build_listener(self):
        return self._listener_factory(
            api_id=self.shared_config.telegram_api_id,
            api_hash=self.shared_config.telegram_api_hash,
            session_path=str(self.shared_config.telegram_session_path),
            on_message=self.handle_message,
        )
