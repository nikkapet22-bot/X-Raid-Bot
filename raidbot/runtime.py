from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable

from raidbot.chrome import ChromeOpener
from raidbot.browser.backends import LaunchOnlyBrowserBackend
from raidbot.browser.executors.noop import NoOpRaidExecutor
from raidbot.browser.pipeline import BrowserPipeline
from raidbot.models import IncomingMessage
from raidbot.dedupe import InMemoryOpenedUrlStore
from raidbot.service import RaidService
from raidbot.telegram_client import TelegramRaidListener


@dataclass
class Runtime:
    service: RaidService
    pipeline: BrowserPipeline
    listener: TelegramRaidListener
    dedupe_store: InMemoryOpenedUrlStore
    message_handler: Callable[[IncomingMessage], object]


def build_runtime(settings) -> Runtime:
    dedupe_store = InMemoryOpenedUrlStore()
    service = RaidService(
        allowed_chat_ids=settings.telegram_chat_whitelist,
        allowed_sender_ids=settings.allowed_sender_ids,
        dedupe_store=dedupe_store,
        preset_replies=settings.preset_replies,
    )

    backend = _build_browser_backend(settings)
    executor = _build_executor(settings)
    pipeline = BrowserPipeline(backend, executor)

    def handle_message(message: IncomingMessage) -> object:
        detection_result = service.handle_message(message)
        if detection_result.kind != "job_detected" or detection_result.job is None:
            return detection_result

        execution_result = pipeline.execute(detection_result.job)
        if execution_result.handed_off:
            dedupe_store.mark_if_new(detection_result.job.normalized_url)
        return execution_result

    listener = TelegramRaidListener(
        api_id=settings.telegram_api_id,
        api_hash=settings.telegram_api_hash,
        session_path=str(settings.telegram_session_path),
        on_message=handle_message,
    )
    return Runtime(
        service=service,
        pipeline=pipeline,
        listener=listener,
        dedupe_store=dedupe_store,
        message_handler=handle_message,
    )


def _build_browser_backend(settings):
    if settings.browser_mode == "launch-only":
        opener = ChromeOpener(
            chrome_path=settings.chrome_path,
            user_data_dir=settings.chrome_user_data_dir,
            profile_directory=settings.chrome_profile_directory,
        )
        return LaunchOnlyBrowserBackend(opener)
    raise ValueError(f"Unsupported browser mode: {settings.browser_mode}")


def _build_executor(settings):
    if settings.executor_name == "noop":
        return NoOpRaidExecutor()
    raise ValueError(f"Unsupported executor: {settings.executor_name}")
