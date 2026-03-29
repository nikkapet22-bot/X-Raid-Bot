from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
import time
from typing import Any

from raidbot.browser.backends import LaunchOnlyBrowserBackend
from raidbot.browser.executors.noop import NoOpRaidExecutor
from raidbot.browser.pipeline import BrowserPipeline
from raidbot.chrome import ChromeOpener
from raidbot.dedupe import InMemoryOpenedUrlStore
from raidbot.desktop.bot_actions.sequence import build_bot_action_sequence
from raidbot.desktop.chrome_profiles import detect_chrome_environment
from raidbot.desktop.automation.autorun import AutoRunProcessor, PendingRaidWorkItem
from raidbot.desktop.automation.runtime import AutomationRuntime
from raidbot.desktop.automation.windowing import find_opened_raid_window
from raidbot.desktop.models import (
    ActivityEntry,
    BotRuntimeState,
    DesktopAppConfig,
    DesktopAppState,
    TelegramConnectionState,
)
from raidbot.desktop.storage import DesktopStorage
from raidbot.models import (
    MessageOutcome,
    RaidActionRequirements,
    RaidDetectionResult,
    RaidExecutionResult,
)
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
        automation_runtime_factory: Callable[[EmitEvent], Any] | None = None,
        chrome_opener_factory: Callable[..., Any] | None = None,
        chrome_environment_factory: Callable[[], Any] = detect_chrome_environment,
        manual_run_active: Callable[[], bool] | None = None,
        auto_run_wait: Callable[[float], None] | None = None,
        now: NowFactory = datetime.utcnow,
    ) -> None:
        self.config = config
        self.storage = storage
        self.emit_event = emit_event
        self.service_factory = service_factory
        self.pipeline_factory = pipeline_factory
        self.listener_factory = listener_factory or TelegramRaidListener
        self.automation_runtime_factory = automation_runtime_factory
        self.chrome_opener_factory = chrome_opener_factory
        self.chrome_environment_factory = chrome_environment_factory
        self.manual_run_active = manual_run_active or (lambda: False)
        self.auto_run_wait = auto_run_wait or time.sleep
        self.now = now

        self.state = self.storage.load_state()
        self._dedupe_store = InMemoryOpenedUrlStore()
        self._service: Any | None = None
        self._pipeline: Any | None = None
        self._listener: Any | None = None
        self._automation_runtime: Any | None = None
        self._automation_processor: AutoRunProcessor | None = None
        self._chrome_opener: Any | None = None
        self._automation_reserved_urls: set[str] = set()
        self._active_auto_sequence_id: str | None = None
        self._bot_action_sequence_error: str | None = None
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
        if self._automation_runtime is not None and hasattr(
            self._automation_runtime, "request_stop"
        ):
            self._automation_runtime.request_stop()
        if self._listener is None:
            self._set_bot_state(BotRuntimeState.stopped)
            return

        self._set_bot_state(BotRuntimeState.stopping)
        await self._listener.stop()
        self._set_bot_state(BotRuntimeState.stopped)

    async def apply_config(self, config: DesktopAppConfig) -> None:
        telegram_changed = self._telegram_config_changed(config)
        profile_changed = self.config.chrome_profile_directory != config.chrome_profile_directory
        self.config = config

        if profile_changed:
            self._chrome_opener = None

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
            if hasattr(self._service, "default_requirements"):
                self._service.default_requirements = self._default_requirements(config)

        self._update_pipeline_profile_directory(config.chrome_profile_directory)

    def _handle_message(self, message) -> Any:
        if self._is_inactive():
            return MessageOutcome(action="ignored", reason="bot_inactive")

        if self._service is None:
            raise RuntimeError("DesktopBotWorker service is not initialized")

        detection = self._service.handle_message(message)
        if detection.kind != "job_detected" or detection.job is None:
            self._record_detection_result(detection)
            return detection

        self._record_detection_result(detection)
        if detection.job.normalized_url in self._automation_reserved_urls:
            duplicate = RaidDetectionResult(
                kind="duplicate",
                normalized_url=detection.job.normalized_url,
            )
            self._record_detection_result(duplicate)
            return duplicate
        if not self._auto_run_requested():
            return self._handle_detected_raid_via_pipeline(detection)
        processor = self._ensure_automation_processor()
        item = PendingRaidWorkItem(
            normalized_url=detection.job.normalized_url,
            trace_id=detection.job.trace_id,
        )
        admitted = processor.admit(item)
        if admitted:
            self._automation_reserved_urls.add(detection.job.normalized_url)
            self._record_activity(
                "auto_queued",
                reason="auto_queued",
                url=detection.job.normalized_url,
            )
            self._drain_automation_queue()
        return detection

    def resume_automation_queue(self) -> None:
        processor = self._automation_processor
        if processor is None:
            return
        if not self._auto_run_requested():
            return
        if processor.state == "paused":
            processor.resume()
            self._sync_automation_status()
            return
        if processor.queue_length:
            self._drain_automation_queue()

    def clear_automation_queue(self) -> None:
        processor = self._automation_processor
        if processor is None:
            return
        if processor.state != "paused" and not processor.queue_length:
            return
        for pending_item in processor.pending_items:
            self._automation_reserved_urls.discard(pending_item.normalized_url)
        processor.clear()
        self._sync_automation_status()

    def notify_manual_automation_finished(self) -> None:
        processor = self._automation_processor
        if processor is None or not self._auto_run_requested():
            return
        if processor.state != "queued" or not processor.queue_length:
            return
        self._drain_automation_queue()

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

    def _ensure_automation_processor(self) -> AutoRunProcessor:
        if self._automation_processor is not None:
            return self._automation_processor

        self._automation_runtime = self._build_automation_runtime()
        self._automation_processor = AutoRunProcessor(
            auto_run_enabled=self._auto_run_requested,
            default_sequence_id=self._bot_action_sequence_id,
            pre_open_check=lambda _item: self._snapshot_target_windows(),
            open_raid=self._open_automation_raid,
            execute_raid=self._execute_automation_sequence,
            close_raid=self._close_automation_window,
            on_success=self._record_automation_success,
            on_failure=self._record_automation_failure,
            on_status=self._update_automation_status,
        )
        return self._automation_processor

    def _build_automation_runtime(self) -> Any:
        if self.automation_runtime_factory is not None:
            return self.automation_runtime_factory(self._receive_automation_runtime_event)
        return AutomationRuntime(emit_event=self._receive_automation_runtime_event)

    def _receive_automation_runtime_event(self, event: dict[str, Any]) -> None:
        self._emit("automation_runtime_event", event=event)

    def _snapshot_target_windows(self):
        runtime = self._automation_runtime
        if runtime is None:
            return ()
        return tuple(runtime.list_target_windows())

    def _bot_action_sequence_id(self) -> str | None:
        sequence = self._build_active_bot_action_sequence()
        if sequence is None:
            return None
        return sequence.id

    def _build_active_bot_action_sequence(self):
        enabled_slots = tuple(slot for slot in self.config.bot_action_slots if slot.enabled)
        if not enabled_slots:
            self._bot_action_sequence_error = "bot_action_not_configured"
            return None
        if any(slot.template_path is None or not slot.template_path.exists() for slot in enabled_slots):
            self._bot_action_sequence_error = "captured_image_missing"
            return None
        self._bot_action_sequence_error = None
        return build_bot_action_sequence(enabled_slots)

    def _auto_run_requested(self) -> bool:
        return bool(
            self.config.auto_run_enabled
            or any(slot.enabled for slot in self.config.bot_action_slots)
        )

    def _translate_automation_reason(self, reason: str | None) -> str | None:
        if reason != "default_sequence_missing":
            return reason
        return self._bot_action_sequence_error or "bot_action_not_configured"

    def _open_automation_raid(
        self,
        item: PendingRaidWorkItem,
        previous_windows,
    ):
        runtime = self._automation_runtime
        if runtime is None:
            raise RuntimeError("automation_runtime_unavailable")
        opener = self._build_chrome_opener()
        context = opener.open_raid_window(item.normalized_url)
        if self.config.auto_run_settle_ms > 0:
            self.auto_run_wait(self.config.auto_run_settle_ms / 1000.0)
        opened_window = find_opened_raid_window(
            list(previous_windows or ()),
            runtime.list_target_windows(),
        )
        if opened_window is None:
            raise RuntimeError("target_window_not_found")
        self._dedupe_store.mark_if_new(item.normalized_url)
        self._automation_reserved_urls.discard(item.normalized_url)
        return replace(context, window_handle=opened_window.handle)

    def _execute_automation_sequence(
        self,
        _item: PendingRaidWorkItem,
        context,
        sequence_id: str,
    ) -> tuple[bool, str | None]:
        runtime = self._automation_runtime
        if runtime is None:
            return False, "automation_runtime_unavailable"
        sequence = self._build_active_bot_action_sequence()
        if sequence is None or sequence.id != sequence_id:
            return False, self._translate_automation_reason("default_sequence_missing")
        if context.window_handle is None:
            return False, "target_window_not_found"
        self._record_activity(
            "automation_started",
            reason="automation_started",
            url=context.normalized_url,
        )
        self._active_auto_sequence_id = sequence_id
        self._emit(
            "automation_run_started",
            sequence_id=sequence_id,
            url=context.normalized_url,
            window_handle=context.window_handle,
        )
        result = runtime.run_sequence(
            sequence,
            selected_window_handle=context.window_handle,
        )
        status = getattr(result, "status", None)
        failure_reason = getattr(result, "failure_reason", None)
        if status == "completed":
            return True, None
        return False, failure_reason or "automation_execution_failed"

    def _close_automation_window(self, context) -> None:
        runtime = self._automation_runtime
        if runtime is None:
            return
        runner = getattr(runtime, "_active_runner", None)
        input_driver = getattr(runner, "input_driver", None)
        if input_driver is None or not hasattr(input_driver, "close_active_window"):
            return
        input_driver.close_active_window()

    def _record_automation_success(
        self,
        item: PendingRaidWorkItem,
        _context,
    ) -> None:
        self._record_activity(
            "automation_succeeded",
            reason="automation_succeeded",
            url=item.normalized_url,
        )
        self._record_activity(
            "session_closed",
            reason="automation_succeeded",
            url=item.normalized_url,
        )
        self._emit(
            "automation_run_succeeded",
            sequence_id=self._active_auto_sequence_id,
            url=item.normalized_url,
        )
        self._active_auto_sequence_id = None

    def _record_automation_failure(
        self,
        item: PendingRaidWorkItem,
        reason: str,
        context,
    ) -> None:
        reason = self._translate_automation_reason(reason) or "automation_execution_failed"
        self._automation_reserved_urls.discard(item.normalized_url)
        self._record_activity(
            "automation_failed",
            reason=reason,
            url=item.normalized_url,
            emit_error=True,
            count_open_failure=(
                context is not None or reason in {"browser_startup_failure", "chrome_open_failed"}
            ),
        )
        if context is not None and self._active_auto_sequence_id is not None:
            self._emit(
                "automation_run_failed",
                sequence_id=self._active_auto_sequence_id,
                url=item.normalized_url,
                reason=reason,
            )
            self._active_auto_sequence_id = None

    def _update_automation_status(
        self,
        state: str,
        queue_length: int,
        current_url: str | None,
        last_error: str | None,
    ) -> None:
        last_error = self._translate_automation_reason(last_error)
        previous_state = self.state.automation_queue_state
        previous_length = self.state.automation_queue_length
        previous_url = self.state.automation_current_url

        self.state.automation_queue_state = state
        self.state.automation_queue_length = queue_length
        self.state.automation_current_url = current_url
        self.state.automation_last_error = last_error
        self.storage.save_state(self.state)
        self._emit("stats_changed", state=self.state)

        if previous_state != state:
            self._emit("automation_queue_state_changed", state=state)
        if previous_length != queue_length:
            self._emit("automation_queue_length_changed", length=queue_length)
        if previous_url != current_url:
            self._emit("automation_current_url_changed", url=current_url)

    def _drain_automation_queue(self) -> None:
        processor = self._automation_processor
        if processor is None:
            return
        while processor.queue_length and self._auto_run_requested():
            if self.manual_run_active():
                break
            if processor.state == "paused":
                break
            progressed = processor.process_next()
            if not progressed:
                break

    def _sync_automation_status(self) -> None:
        processor = self._automation_processor
        if processor is None:
            return
        self._update_automation_status(
            processor.state,
            processor.queue_length,
            processor.current_url,
            processor.last_error,
        )

    def _handle_detected_raid_via_pipeline(
        self,
        detection: RaidDetectionResult,
    ) -> RaidDetectionResult:
        if self._pipeline is None or detection.job is None:
            raise RuntimeError("DesktopBotWorker pipeline is not initialized")
        execution = self._pipeline.execute(
            detection.job,
            should_continue=self._can_start_executor,
        )
        if getattr(execution, "handed_off", False):
            self._dedupe_store.mark_if_new(detection.job.normalized_url)
        self._record_execution_result(detection, execution)
        return detection

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
        count_open_failure: bool = True,
    ) -> None:
        timestamp = self.now()
        if action == "browser_session_opened":
            self.state.raids_opened += 1
            self.state.last_successful_raid_open_at = timestamp.isoformat()
        elif action == "automation_started":
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
        elif action == "automation_failed":
            if count_open_failure:
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
            default_requirements=self._default_requirements(config),
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

    def _build_chrome_opener(self) -> Any:
        if self._chrome_opener is not None:
            return self._chrome_opener
        chrome_environment = self.chrome_environment_factory()
        if chrome_environment is None:
            raise RuntimeError("Chrome environment is unavailable")
        if self.chrome_opener_factory is not None:
            self._chrome_opener = self.chrome_opener_factory(
                chrome_path=chrome_environment.chrome_path,
                user_data_dir=chrome_environment.user_data_dir,
                profile_directory=self.config.chrome_profile_directory,
            )
            return self._chrome_opener
        self._chrome_opener = ChromeOpener(
            chrome_path=chrome_environment.chrome_path,
            user_data_dir=chrome_environment.user_data_dir,
            profile_directory=self.config.chrome_profile_directory,
        )
        return self._chrome_opener

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

    def _default_requirements(self, config: DesktopAppConfig) -> RaidActionRequirements:
        return RaidActionRequirements(
            like=config.default_action_like,
            repost=config.default_action_repost,
            bookmark=config.default_action_bookmark,
            reply=config.default_action_reply,
        )

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
