from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from raidbot.browser.backends import LaunchOnlyBrowserBackend
from raidbot.browser.executors.noop import NoOpRaidExecutor
from raidbot.browser.pipeline import BrowserPipeline
from raidbot.chrome import ChromeOpener
from raidbot.dedupe import InMemoryOpenedUrlStore
from raidbot.desktop.chrome_profiles import detect_chrome_environment
from raidbot.desktop.models import (
    ActivityEntry,
    BotRuntimeState,
    DesktopAppConfig,
    DesktopAppState,
    TelegramConnectionState,
)
from raidbot.desktop.storage import DesktopStorage
from raidbot.models import MessageOutcome, RaidDetectionResult, RaidExecutionResult
from raidbot.service import RaidService
from raidbot.telegram_client import TelegramRaidListener


EmitEvent = Callable[[dict[str, Any]], None]
NowFactory = Callable[[], datetime]


class DesktopBotWorker:
    def __init__(
        self,
        config: DesktopAppConfig,
        storage: DesktopStorage,
        emit_event: EmitEvent,
        service_factory: Callable[[DesktopAppConfig], Any] | None = None,
        pipeline_factory: Callable[[DesktopAppConfig], Any] | None = None,
        listener_factory: Callable[..., Any] | None = None,
        chrome_environment_factory: Callable[[], Any] = detect_chrome_environment,
        now: NowFactory = datetime.utcnow,
    ) -> None:
        self.config = config
        self.storage = storage
        self.emit_event = emit_event
        self.service_factory = service_factory
        self.pipeline_factory = pipeline_factory
        self.listener_factory = listener_factory or TelegramRaidListener
        self.chrome_environment_factory = chrome_environment_factory
        self.now = now

        self.state = self.storage.load_state()
        self._dedupe_store = InMemoryOpenedUrlStore()
        self._service: Any | None = None
        self._pipeline: Any | None = None
        self._listener: Any | None = None
        self._restart_requested = False
        self._stop_requested = False

    async def run(self) -> None:
        self._stop_requested = False

        while True:
            self._restart_requested = False
            try:
                self._service = self._build_service(self.config)
                self._pipeline = self._build_pipeline(self.config)
                self._listener = self._build_listener(self.config)
                self._set_bot_state(BotRuntimeState.starting)
                await self._listener.run_forever()
            except Exception as exc:
                self._handle_run_failure(exc)
                raise

            if self._restart_requested and not self._stop_requested:
                self._set_connection_state(TelegramConnectionState.reconnecting)
                continue

            if self.state.connection_state is not TelegramConnectionState.disconnected:
                self._set_connection_state(TelegramConnectionState.disconnected)
            if self.state.bot_state is not BotRuntimeState.stopped:
                self._set_bot_state(BotRuntimeState.stopped)
            break

    async def stop(self) -> None:
        self._stop_requested = True
        if self._listener is None:
            self._set_bot_state(BotRuntimeState.stopped)
            return

        self._set_bot_state(BotRuntimeState.stopping)
        await self._listener.stop()
        self._set_bot_state(BotRuntimeState.stopped)

    async def apply_config(self, config: DesktopAppConfig) -> None:
        telegram_changed = self._telegram_config_changed(config)
        self.config = config

        if telegram_changed:
            self._restart_requested = True
            if self._listener is not None:
                await self._listener.stop()
            return

        if self._service is not None:
            self._service.allowed_chat_ids = set(config.whitelisted_chat_ids)
            self._service.allowed_sender_ids = set(config.allowed_sender_ids)
            if hasattr(self._service, "preset_replies"):
                self._service.preset_replies = tuple(config.preset_replies)

        self._update_pipeline_profile_directory(config.chrome_profile_directory)

    def _handle_message(self, message) -> Any:
        if self._is_inactive():
            return MessageOutcome(action="ignored", reason="bot_inactive")

        if self._service is None:
            raise RuntimeError("DesktopBotWorker service is not initialized")
        if self._pipeline is None:
            raise RuntimeError("DesktopBotWorker pipeline is not initialized")

        detection = self._service.handle_message(message)
        if detection.kind != "job_detected" or detection.job is None:
            self._record_detection_result(detection)
            return detection

        self._record_detection_result(detection)
        execution = self._pipeline.execute(
            detection.job,
            should_continue=self._can_start_executor,
        )
        if execution.handed_off:
            self._dedupe_store.mark_if_new(detection.job.normalized_url)
        self._record_execution_result(detection, execution)
        return execution

    def _handle_connection_state_change(self, state: str) -> None:
        connection_state = TelegramConnectionState(state)
        self._set_connection_state(connection_state)
        if (
            connection_state is TelegramConnectionState.connected
            and self.state.bot_state is BotRuntimeState.starting
        ):
            self._set_bot_state(BotRuntimeState.running)

    def _record_detection_result(self, detection: RaidDetectionResult) -> None:
        if detection.kind == "job_detected":
            self._record_activity(
                "raid_detected",
                reason=detection.kind,
                url=detection.normalized_url,
            )
            return
        self._record_activity(
            detection.kind,
            reason=detection.kind,
            url=detection.normalized_url,
        )

    def _record_execution_result(
        self,
        detection: RaidDetectionResult,
        execution: RaidExecutionResult,
    ) -> None:
        url = detection.normalized_url
        kind = execution.kind

        if kind == "browser_startup_failure":
            self._record_activity(
                "browser_session_failed",
                reason=kind,
                url=url,
                emit_error=True,
            )
            return

        if kind in {"navigation_failure", "page_ready_timeout"}:
            self._record_activity(
                "browser_session_failed",
                reason=kind,
                url=url,
                emit_error=True,
            )
            self._record_activity("session_closed", reason=kind, url=url)
            return

        if kind in {
            "cancelled_before_executor",
            "executor_not_configured",
            "executor_succeeded",
            "executor_failed",
            "session_close_failure",
        }:
            self._record_activity("browser_session_opened", reason=kind, url=url)

        if kind in {
            "cancelled_before_executor",
            "executor_succeeded",
            "executor_failed",
            "session_close_failure",
        }:
            self._record_activity("page_ready", reason=kind, url=url)

        if kind == "executor_not_configured":
            self._record_activity("executor_not_configured", reason=kind, url=url)
            return

        if kind == "cancelled_before_executor":
            self._record_activity("cancelled_before_executor", reason=kind, url=url)
            self._record_activity("session_closed", reason=kind, url=url)
            return

        if kind == "executor_succeeded":
            self._record_activity("executor_succeeded", reason=kind, url=url)
            self._record_activity("session_closed", reason=kind, url=url)
            return

        if kind == "executor_failed":
            self._record_activity(
                "executor_failed",
                reason=kind,
                url=url,
                emit_error=True,
            )
            self._record_activity("session_closed", reason=kind, url=url)
            return

        if kind == "session_close_failure":
            self._record_activity(
                "browser_session_failed",
                reason=kind,
                url=url,
                emit_error=True,
            )
            return

        self._record_activity(kind, reason=kind, url=url)

    def _record_activity(
        self,
        action: str,
        *,
        reason: str | None = None,
        url: str | None = None,
        emit_error: bool = False,
    ) -> None:
        timestamp = self.now()
        if action == "browser_session_opened":
            self.state.raids_opened += 1
            self.state.last_successful_raid_open_at = timestamp.isoformat()
        elif action == "duplicate":
            self.state.duplicates_skipped += 1
        elif action == "sender_rejected":
            self.state.non_matching_skipped += 1
            self.state.sender_rejected += 1
        elif action in {"not_a_raid", "chat_rejected"}:
            self.state.non_matching_skipped += 1
        elif action == "browser_session_failed":
            self.state.browser_session_failed += 1
            self.state.open_failures += 1
            self.state.last_error = reason
        elif action == "page_ready":
            self.state.page_ready += 1
        elif action == "executor_not_configured":
            self.state.executor_not_configured += 1
        elif action == "executor_succeeded":
            self.state.executor_succeeded += 1
        elif action == "executor_failed":
            self.state.executor_failed += 1
            self.state.last_error = reason
        elif action == "session_closed":
            self.state.session_closed += 1

        entry = ActivityEntry(
            timestamp=timestamp,
            action=action,
            url=url,
            reason=reason,
        )
        self.state.activity = [*self.state.activity, entry][-200:]
        self.storage.save_state(self.state)
        self._emit("stats_changed", state=self.state)
        self._emit("activity_added", entry=entry)
        if emit_error:
            self._emit("error", message=reason or action)

    def _build_service(self, config: DesktopAppConfig) -> Any:
        if self.service_factory is not None:
            return self.service_factory(config)

        if not config.allowed_sender_ids:
            raise ValueError("At least one allowed sender ID is required before starting the bot")

        return RaidService(
            allowed_chat_ids=set(config.whitelisted_chat_ids),
            allowed_sender_ids=set(config.allowed_sender_ids),
            dedupe_store=self._dedupe_store,
            preset_replies=config.preset_replies,
        )

    def _build_pipeline(self, config: DesktopAppConfig) -> Any:
        if self.pipeline_factory is not None:
            return self.pipeline_factory(config)

        chrome_environment = self.chrome_environment_factory()
        opener = ChromeOpener(
            chrome_path=chrome_environment.chrome_path,
            user_data_dir=chrome_environment.user_data_dir,
            profile_directory=config.chrome_profile_directory,
        )
        if config.browser_mode != "launch-only":
            raise ValueError(f"Unsupported browser mode: {config.browser_mode}")
        if config.executor_name != "noop":
            raise ValueError(f"Unsupported executor: {config.executor_name}")

        return BrowserPipeline(
            LaunchOnlyBrowserBackend(opener),
            NoOpRaidExecutor(),
        )

    def _build_listener(self, config: DesktopAppConfig) -> Any:
        listener = self.listener_factory(
            api_id=config.telegram_api_id,
            api_hash=config.telegram_api_hash,
            session_path=str(config.telegram_session_path),
            on_message=self._handle_message,
            on_connection_state_change=self._handle_connection_state_change,
        )
        if hasattr(listener, "on_message"):
            listener.on_message = self._handle_message
        if hasattr(listener, "on_connection_state_change"):
            listener.on_connection_state_change = self._handle_connection_state_change
        return listener

    def _telegram_config_changed(self, config: DesktopAppConfig) -> bool:
        return (
            self.config.telegram_api_id != config.telegram_api_id
            or self.config.telegram_api_hash != config.telegram_api_hash
            or self.config.telegram_session_path != config.telegram_session_path
        )

    def _can_start_executor(self) -> bool:
        return not self._is_inactive()

    def _is_inactive(self) -> bool:
        return (
            self._stop_requested
            or self._restart_requested
            or self.state.bot_state is BotRuntimeState.stopping
        )

    def _update_pipeline_profile_directory(self, profile_directory: str) -> None:
        if self._pipeline is None:
            return

        backend = getattr(self._pipeline, "_backend", None)
        for attribute_name in ("_launcher", "launcher", "opener"):
            launcher = getattr(backend, attribute_name, None)
            if launcher is not None and hasattr(launcher, "profile_directory"):
                launcher.profile_directory = profile_directory
                return

    def _set_bot_state(self, state: BotRuntimeState) -> None:
        self.state.bot_state = state
        self.storage.save_state(self.state)
        self._emit("bot_state_changed", state=state.value)

    def _set_connection_state(self, state: TelegramConnectionState) -> None:
        self.state.connection_state = state
        self.storage.save_state(self.state)
        self._emit("connection_state_changed", state=state.value)

    def _emit(self, event_type: str, **payload: Any) -> None:
        self.emit_event({"type": event_type, **payload})

    def _handle_run_failure(self, exc: Exception) -> None:
        self.state.last_error = str(exc)
        self._set_bot_state(BotRuntimeState.error)
        self._emit("error", message=self.state.last_error)
