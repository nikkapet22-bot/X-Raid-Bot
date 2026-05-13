from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
import random
import time
from typing import Any

from raidbot.browser.backends import LaunchOnlyBrowserBackend
from raidbot.browser.executors.noop import NoOpRaidExecutor
from raidbot.browser.pipeline import BrowserPipeline
from raidbot.chrome import ChromeOpener, OpenedRaidContext
from raidbot.dedupe import InMemoryOpenedUrlStore
from raidbot.desktop.bot_actions.sequence import (
    build_bot_action_sequence,
    build_slot_1_preset_chooser,
)
from raidbot.desktop.chrome_profiles import detect_chrome_environment
from raidbot.desktop.automation.autorun import (
    AutoRunProcessor,
    PendingRaidWorkItem,
    UserPauseRequested,
)
from raidbot.desktop.automation.models import AutomationSequence, AutomationStep
from raidbot.desktop.automation.runtime import AutomationRuntime
from raidbot.desktop.automation.windowing import find_opened_raid_window
from raidbot.desktop.models import (
    ActivityEntry,
    BotRuntimeState,
    DesktopAppConfig,
    DesktopAppState,
    RaidProfileConfig,
    RaidProfileState,
    SuccessfulProfileRun,
    TelegramConnectionState,
    apply_dashboard_metric_reset,
    raid_profile_allows_slot,
    raid_profile_has_any_actions_enabled,
)
from raidbot.desktop.storage import DesktopStorage
from raidbot.models import (
    IncomingMessage,
    MessageOutcome,
    RaidActionRequirements,
    RaidDetectionResult,
    RaidExecutionResult,
)

_PAGE_READY_POST_MATCH_DELAY_SECONDS = 0.5
_PAGE_READY_MAX_SEARCH_SECONDS = 12.0
_PAGE_EXIT_MAX_SEARCH_SECONDS = 1.0
_WINDOW_CLOSE_CONFIRM_SECONDS = 0.75
_WINDOW_CLOSE_CONFIRM_POLL_SECONDS = 0.05
_TROUBLESHOOT_STEP_SEARCH_SECONDS = 5.0
_TROUBLESHOOT_STEP_SETTLE_SECONDS = 5.0
_TROUBLESHOOT_POST_RECOVERY_SETTLE_SECONDS = 5.0
_WARMUP_HOME_URL = "https://x.com"
_WARMUP_FEED_URL = "https://x.com/BRICSinfo"
_WARMUP_PAGE_SETTLE_SECONDS = 1.0
_WARMUP_HOME_HOLD_SEGMENTS = (
    ("pagedown", 5.0),
    ("pageup", 2.0),
    ("pagedown", 3.0),
)
_WARMUP_FEED_HOLD_SEGMENTS = (("pagedown", 4.0),)
_PAUSE_WAIT_POLL_SECONDS = 0.1
_HELD_KEY_REPEAT_INTERVAL_SECONDS = 0.2
from raidbot.service import RaidService
from raidbot.telegram_client import TelegramRaidListener


EmitEvent = Callable[[dict[str, Any]], None]
NowFactory = Callable[[], datetime]
_DEDUPED_ACTIVITY_ACTIONS = {
    "automation_started",
    "automation_succeeded",
    "browser_session_opened",
    "page_ready",
    "executor_not_configured",
    "executor_succeeded",
    "executor_failed",
    "session_closed",
}
_SUCCESSFUL_PROFILE_RUN_LIMIT = 5000


@dataclass(frozen=True)
class PausedProfileRunSnapshot:
    profile_directory: str
    mode: str
    window_handle: int | None
    started: bool = False
    sequence: AutomationSequence | None = None
    next_step_index: int = 0
    next_step_phase: str | None = None
    remaining_hold_segments: tuple[tuple[str, float], ...] = ()


@dataclass(frozen=True)
class PausedExecutionSnapshot:
    source: str
    item: PendingRaidWorkItem
    sequence_id: str
    ordered_profile_directories: tuple[str, ...]
    next_profile_index: int
    profile_snapshot: PausedProfileRunSnapshot | None
    raid_opened: bool
    raid_succeeded: bool
    recovery_performed: bool
    failure_recorded: bool
    last_failure_reason: str | None


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
        telegram_setup_service_factory: Callable[[DesktopAppConfig], Any] | None = None,
        chrome_environment_factory: Callable[[], Any] = detect_chrome_environment,
        manual_run_active: Callable[[], bool] | None = None,
        auto_run_wait: Callable[[float], None] | None = None,
        profile_shuffle: Callable[[list[Any]], None] | None = None,
        action_shuffle: Callable[[list[Any]], None] | None = None,
        now: NowFactory = datetime.now,
    ) -> None:
        self.config = config
        self.storage = storage
        self.emit_event = emit_event
        self.service_factory = service_factory
        self.pipeline_factory = pipeline_factory
        self.listener_factory = listener_factory or TelegramRaidListener
        self.automation_runtime_factory = automation_runtime_factory
        self.chrome_opener_factory = chrome_opener_factory
        self.telegram_setup_service_factory = (
            telegram_setup_service_factory or self._default_telegram_setup_service_factory
        )
        self.chrome_environment_factory = chrome_environment_factory
        self.manual_run_active = manual_run_active or (lambda: False)
        self.auto_run_wait = auto_run_wait or time.sleep
        self.profile_shuffle = profile_shuffle or random.shuffle
        self.action_shuffle = action_shuffle or random.shuffle
        self.now = now

        self.state = self.storage.load_state()
        self._dedupe_store = InMemoryOpenedUrlStore()
        self._restore_dedupe_store_from_state()
        self._service: Any | None = None
        self._pipeline: Any | None = None
        self._listener: Any | None = None
        self._automation_runtime: Any | None = None
        self._automation_processor: AutoRunProcessor | None = None
        self._chrome_opener: Any | None = None
        self._chrome_openers: dict[str, Any] = {}
        self._automation_reserved_urls: set[str] = set()
        self._active_auto_sequence_id: str | None = None
        self._bot_action_sequence_error: str | None = None
        self._automation_failure_already_recorded = False
        self._restart_requested = False
        self._stop_requested = False
        self._pause_requested = False
        self._user_paused = False
        self._paused_execution: PausedExecutionSnapshot | None = None
        self._active_execution_source: str | None = None
        self._active_execution_url: str | None = None
        self._pending_profile_run_starts: dict[tuple[str, str], datetime] = {}
        self._sync_raid_profile_states(save=False, emit=False)

    def _restore_dedupe_store_from_state(self) -> None:
        for entry in self.state.activity:
            url = getattr(entry, "url", None)
            action = getattr(entry, "action", None)
            if not url or action not in _DEDUPED_ACTIVITY_ACTIONS:
                continue
            self._dedupe_store.mark_if_new(url)

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
        self._pause_requested = False
        self._user_paused = False
        self._paused_execution = None
        self._active_execution_url = None
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
        profile_changed = (
            self.config.chrome_profile_directory != config.chrome_profile_directory
            or self.config.raid_profiles != config.raid_profiles
        )
        self.config = config

        if profile_changed:
            self._chrome_opener = None
            self._chrome_openers = {}
        self._sync_raid_profile_states(save=True, emit=True)

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
        if (
            detection.kind == "job_detected"
            and detection.job is not None
            and self._dedupe_store.contains(detection.job.normalized_url)
        ):
            detection = RaidDetectionResult(
                kind="duplicate",
                normalized_url=detection.job.normalized_url,
                reason="duplicate",
            )
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
            if self._user_paused:
                processor.suspend()
                self._sync_automation_status()
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

    def toggle_pause_resume(self) -> None:
        if self._pause_requested or self._user_paused:
            self._resume_after_user_pause()
            return
        self._pause_requested = True
        runtime = self._automation_runtime
        if runtime is not None and hasattr(runtime, "request_stop"):
            runtime.request_stop()
        if self._active_execution_source is not None:
            self._update_user_pause_status(
                self._active_execution_url or self.state.automation_current_url
            )
            return
        self._enter_user_paused_idle_state()

    def notify_manual_automation_finished(self) -> None:
        processor = self._automation_processor
        if processor is None or not self._auto_run_requested():
            return
        if processor.state != "queued" or not processor.queue_length:
            return
        self._drain_automation_queue()

    def _resume_after_user_pause(self) -> None:
        snapshot = self._paused_execution
        if snapshot is None:
            self._pause_requested = False
            self._user_paused = False
            processor = self._automation_processor
            if processor is not None:
                processor.resume()
                self._sync_automation_status()
            else:
                self._update_automation_status("idle", 0, None, None)
            return

        self._pause_requested = False
        if snapshot.source == "auto":
            processor = self._automation_processor
            if processor is None:
                raise RuntimeError("Automation queue unavailable")
            processor.resume()
            self._sync_automation_status()
            return

        self._run_paused_manual_execution(snapshot)

    def _run_paused_manual_execution(self, snapshot: PausedExecutionSnapshot) -> None:
        runtime = self._automation_runtime
        if runtime is None:
            raise RuntimeError("Automation runtime unavailable")
        if not snapshot.ordered_profile_directories:
            raise RuntimeError("Paused manual execution is incomplete")
        profile_directory = snapshot.ordered_profile_directories[0]
        profile = self._find_profile_by_directory(profile_directory)
        if profile is None:
            raise RuntimeError(f"Unknown raid profile: {profile_directory}")
        self._active_execution_source = "manual"
        self._active_execution_url = snapshot.item.normalized_url
        try:
            succeeded, failure_reason = self._execute_profiles_for_item(
                source="manual",
                item=snapshot.item,
                runtime=runtime,
                sequence_id=snapshot.sequence_id,
                ordered_profiles=[profile],
            )
        except UserPauseRequested:
            self._update_user_pause_status(snapshot.item.normalized_url)
            return
        finally:
            self._active_execution_source = None
            self._active_execution_url = None
        if not succeeded:
            raise RuntimeError(
                self._translate_automation_reason(failure_reason)
                or failure_reason
                or "automation_execution_failed"
            )
        self._recover_automation_queue_after_manual_success()
        if self._automation_processor is None:
            self._update_automation_status("idle", 0, None, None)
            return
        self._sync_automation_status()

    def _update_user_pause_status(self, current_url: str | None) -> None:
        processor = self._automation_processor
        queue_length = processor.queue_length if processor is not None else 0
        self._update_automation_status("suspended", queue_length, current_url, None)

    def _enter_user_paused_idle_state(self) -> None:
        self._user_paused = True
        processor = self._automation_processor
        if processor is not None:
            processor.suspend()
            self._sync_automation_status()
            return
        self._update_automation_status("suspended", 0, None, None)

    def _consume_matching_paused_execution(
        self,
        *,
        source: str,
        item: PendingRaidWorkItem,
    ) -> PausedExecutionSnapshot | None:
        snapshot = self._paused_execution
        if snapshot is None:
            return None
        if snapshot.source != source:
            return None
        if snapshot.item != item:
            return None
        self._paused_execution = None
        self._user_paused = False
        return snapshot

    def _store_paused_execution(self, snapshot: PausedExecutionSnapshot) -> None:
        self._paused_execution = snapshot
        self._user_paused = True
        self._pause_requested = False

    def _find_runtime_window_by_handle(self, runtime: Any, handle: int | None) -> Any | None:
        if handle is None:
            return None
        for window in runtime.list_target_windows():
            if getattr(window, "handle", None) == handle:
                return window
        return None

    def _wait_for_runtime_window_to_close(
        self,
        runtime: Any,
        handle: int | None,
        *,
        timeout_seconds: float = _WINDOW_CLOSE_CONFIRM_SECONDS,
    ) -> bool:
        if handle is None:
            return True
        deadline = time.monotonic() + max(0.0, timeout_seconds)
        while True:
            if self._find_runtime_window_by_handle(runtime, handle) is None:
                return True
            remaining_seconds = deadline - time.monotonic()
            if remaining_seconds <= 0:
                return False
            time.sleep(min(_WINDOW_CLOSE_CONFIRM_POLL_SECONDS, remaining_seconds))

    def _find_profile_by_directory(self, profile_directory: str) -> RaidProfileConfig | None:
        return next(
            (
                profile
                for profile in self.config.raid_profiles
                if profile.profile_directory == profile_directory
            ),
            None,
        )

    def _raise_if_pause_requested(
        self,
        snapshot: PausedProfileRunSnapshot | None = None,
    ) -> None:
        if not self._pause_requested:
            return
        raise UserPauseRequested(snapshot=snapshot)

    def _wait_or_pause(
        self,
        seconds: float,
        *,
        snapshot: PausedProfileRunSnapshot | None = None,
    ) -> None:
        self._raise_if_pause_requested(snapshot)
        if self.auto_run_wait is time.sleep:
            remaining_seconds = max(0.0, float(seconds))
            while remaining_seconds > 0.0:
                interval_seconds = min(_PAUSE_WAIT_POLL_SECONDS, remaining_seconds)
                self.auto_run_wait(interval_seconds)
                remaining_seconds -= interval_seconds
                self._raise_if_pause_requested(snapshot)
            return
        self.auto_run_wait(seconds)
        self._raise_if_pause_requested(snapshot)

    def _recover_automation_queue_after_manual_success(self) -> None:
        processor = self._automation_processor
        if processor is None or not self._auto_run_requested():
            return
        if processor.state == "paused":
            processor.clear()
            self._sync_automation_status()
            return
        if processor.state == "queued" and processor.queue_length:
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
        reason = detection.reason or detection.kind
        if detection.kind == "job_detected":
            self._record_activity(
                "raid_detected",
                reason=reason,
                url=detection.normalized_url,
            )
            return
        self._record_activity(
            detection.kind,
            reason=reason,
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
        if self._user_paused:
            self._automation_processor.suspend()
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
        build_result = self._build_active_bot_action_sequence_result()
        if build_result is None:
            return None
        return build_result.sequence.id

    def _build_active_bot_action_sequence_result(
        self,
        *,
        choose_preset=None,
        profile: RaidProfileConfig | None = None,
    ):
        enabled_slots = [
            slot
            for slot in self.config.bot_action_slots
            if slot.enabled
            and (profile is None or raid_profile_allows_slot(profile, slot.key))
        ]
        if not enabled_slots:
            self._bot_action_sequence_error = "bot_action_not_configured"
            return None
        if any(slot.template_path is None or not slot.template_path.exists() for slot in enabled_slots):
            self._bot_action_sequence_error = "captured_image_missing"
            return None
        self._bot_action_sequence_error = None
        enabled_slots = self._order_bot_action_slots_for_execution(
            enabled_slots,
            randomize=profile is not None,
        )
        if choose_preset is None:
            return build_bot_action_sequence(
                enabled_slots,
                slot_1_finish_delay_seconds=self.config.slot_1_finish_delay_seconds,
                slot_1_obstruction_template_path=self._slot_1_obstruction_template_path(),
                reorder_slot_1_last=True,
            )
        return build_bot_action_sequence(
            enabled_slots,
            slot_1_finish_delay_seconds=self.config.slot_1_finish_delay_seconds,
            slot_1_obstruction_template_path=self._slot_1_obstruction_template_path(),
            choose_preset=choose_preset,
                reorder_slot_1_last=True,
            )

    def _order_bot_action_slots_for_execution(
        self,
        slots: list[Any],
        *,
        randomize: bool,
    ) -> list[Any]:
        reply_slots = [slot for slot in slots if getattr(slot, "key", None) == "slot_1_r"]
        non_reply_slots = [
            slot for slot in slots if getattr(slot, "key", None) != "slot_1_r"
        ]
        if randomize:
            self.action_shuffle(non_reply_slots)
        return [*non_reply_slots, *reply_slots]

    def _build_active_bot_action_sequence(self):
        build_result = self._build_active_bot_action_sequence_result()
        if build_result is None:
            return None
        return build_result.sequence

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
        _previous_windows,
    ):
        self._dedupe_store.mark_if_new(item.normalized_url)
        self._automation_reserved_urls.discard(item.normalized_url)
        return OpenedRaidContext(
            normalized_url=item.normalized_url,
            opened_at=time.monotonic(),
            window_handle=None,
            profile_directory=self.config.chrome_profile_directory,
        )

    def _ordered_profiles_from_snapshot(
        self,
        snapshot: PausedExecutionSnapshot,
    ) -> list[RaidProfileConfig]:
        profiles: list[RaidProfileConfig] = []
        for profile_directory in snapshot.ordered_profile_directories:
            profile = self._find_profile_by_directory(profile_directory)
            if profile is not None:
                profiles.append(profile)
        return profiles

    def _execute_profiles_for_item(
        self,
        *,
        source: str,
        item: PendingRaidWorkItem,
        runtime: Any,
        sequence_id: str,
        ordered_profiles: list[RaidProfileConfig],
    ) -> tuple[bool, str | None]:
        paused_execution = self._consume_matching_paused_execution(
            source=source,
            item=item,
        )
        if paused_execution is not None:
            ordered_profiles = self._ordered_profiles_from_snapshot(paused_execution)
            start_index = paused_execution.next_profile_index
            raid_opened = paused_execution.raid_opened
            raid_succeeded = paused_execution.raid_succeeded
            recovery_performed = paused_execution.recovery_performed
            failure_recorded = paused_execution.failure_recorded
            last_failure_reason = paused_execution.last_failure_reason
        else:
            start_index = 0
            raid_opened = False
            raid_succeeded = False
            recovery_performed = False
            failure_recorded = False
            last_failure_reason: str | None = None

        if not ordered_profiles:
            return False, "all_profiles_blocked"

        preset_chooser = build_slot_1_preset_chooser()
        for profile_index, profile in enumerate(ordered_profiles[start_index:], start=start_index):
            profile_snapshot = (
                paused_execution.profile_snapshot
                if paused_execution is not None and profile_index == start_index
                else None
            )
            try:
                if self._profile_runs_warmup(profile):
                    outcome, opened, failure_reason = self._execute_warmup_for_profile(
                        item,
                        profile,
                        runtime=runtime,
                        resume_snapshot=profile_snapshot,
                    )
                else:
                    sequence = (
                        profile_snapshot.sequence
                        if profile_snapshot is not None and profile_snapshot.sequence is not None
                        else None
                    )
                    if sequence is None:
                        profile_sequence = self._build_active_bot_action_sequence_result(
                            choose_preset=preset_chooser,
                            profile=profile,
                        )
                        sequence = (
                            profile_sequence.sequence if profile_sequence is not None else None
                        )
                    if sequence is None:
                        last_failure_reason = self._translate_automation_reason(
                            "default_sequence_missing"
                        ) or "bot_action_not_configured"
                        self._record_raid_profile_failure(
                            item,
                            profile,
                            last_failure_reason,
                            sequence_id=sequence_id,
                        )
                        failure_recorded = True
                        continue
                    outcome, opened, failure_reason = self._execute_raid_for_profile(
                        item,
                        profile,
                        sequence=sequence,
                        runtime=runtime,
                        sequence_id=sequence_id,
                        resume_snapshot=profile_snapshot,
                    )
            except UserPauseRequested as exc:
                self._store_paused_execution(
                    PausedExecutionSnapshot(
                        source=source,
                        item=item,
                        sequence_id=sequence_id,
                        ordered_profile_directories=tuple(
                            current.profile_directory for current in ordered_profiles
                        ),
                        next_profile_index=profile_index,
                        profile_snapshot=exc.snapshot,
                        raid_opened=raid_opened,
                        raid_succeeded=raid_succeeded,
                        recovery_performed=recovery_performed,
                        failure_recorded=failure_recorded,
                        last_failure_reason=last_failure_reason,
                    )
                )
                raise
            if opened and not raid_opened:
                self._record_whole_raid_opened()
                raid_opened = True
            if outcome == "failed":
                last_failure_reason = failure_reason
                failure_recorded = True
                if failure_reason == "window_not_focusable":
                    break
                continue
            if outcome == "recovered":
                recovery_performed = True
                continue
            raid_succeeded = True

        if raid_succeeded or (recovery_performed and not failure_recorded):
            self._record_whole_raid_completed()
            return True, None

        self._record_whole_raid_failed()
        self._automation_failure_already_recorded = failure_recorded
        return False, last_failure_reason or "automation_execution_failed"

    def _execute_automation_sequence(
        self,
        item: PendingRaidWorkItem,
        _context,
        sequence_id: str,
    ) -> tuple[bool, str | None]:
        runtime = self._automation_runtime
        if runtime is None:
            return False, "automation_runtime_unavailable"
        self._automation_failure_already_recorded = False
        build_result = self._build_active_bot_action_sequence_result()
        if build_result is None or build_result.sequence.id != sequence_id:
            return False, self._translate_automation_reason("default_sequence_missing")
        for warning in build_result.warnings:
            self._emit(
                "automation_runtime_event",
                event={
                    "type": "slot_skipped",
                    "step_index": warning.slot_index,
                    "reason": warning.reason,
                },
            )
        eligible_profiles = self._shuffled_eligible_raid_profiles()
        self._active_execution_source = "auto"
        self._active_execution_url = item.normalized_url
        try:
            return self._execute_profiles_for_item(
                source="auto",
                item=item,
                runtime=runtime,
                sequence_id=sequence_id,
                ordered_profiles=eligible_profiles,
            )
        finally:
            self._active_execution_source = None
            self._active_execution_url = None

    def _execute_raid_for_profile(
        self,
        item: PendingRaidWorkItem,
        profile: RaidProfileConfig,
        *,
        sequence,
        runtime: Any,
        sequence_id: str,
        resume_snapshot: PausedProfileRunSnapshot | None = None,
    ) -> tuple[str, bool, str | None]:
        sequence_snapshot = lambda start_step_index=0, started=False, mode="page_ready", step_phase=None: PausedProfileRunSnapshot(
            profile_directory=profile.profile_directory,
            mode=mode,
            window_handle=getattr(opened_window, "handle", None),
            started=started,
            sequence=sequence,
            next_step_index=start_step_index,
            next_step_phase=step_phase,
        )
        if resume_snapshot is not None:
            opened_window = self._find_runtime_window_by_handle(
                runtime,
                resume_snapshot.window_handle,
            )
            if opened_window is None:
                failure_reason = "target_window_not_found"
                self._record_raid_profile_failure(
                    item,
                    profile,
                    failure_reason,
                    sequence_id=sequence_id,
                )
                return "failed", True, failure_reason
            start_step_index = (
                int(resume_snapshot.next_step_index)
                if resume_snapshot.mode == "sequence"
                else 0
            )
            started = bool(resume_snapshot.started)
            start_step_phase = (
                str(resume_snapshot.next_step_phase).strip()
                if resume_snapshot.next_step_phase is not None
                else None
            )
        else:
            previous_windows = tuple(runtime.list_target_windows())
            profile_context, opened_window, open_failure_reason = self._open_raid_for_profile(
                item,
                profile,
                previous_windows,
            )
            if (
                open_failure_reason is not None
                or profile_context is None
                or opened_window is None
            ):
                failure_reason = open_failure_reason or "target_window_not_found"
                self._record_raid_profile_failure(
                    item,
                    profile,
                    failure_reason,
                    sequence_id=sequence_id,
                )
                return "failed", False, failure_reason
            start_step_index = 0
            started = False
            start_step_phase = None

        if resume_snapshot is None or resume_snapshot.mode != "sequence":
            page_ready_failure_reason, scroll_anchor = self._wait_for_page_ready(
                runtime,
                opened_window,
            )
            if page_ready_failure_reason == "stopped":
                raise UserPauseRequested(snapshot=sequence_snapshot(started=started))
            if page_ready_failure_reason is not None:
                if page_ready_failure_reason == "page_ready_not_found":
                    troubleshoot_failure_reason = self._run_cldf_troubleshoot(
                        runtime,
                        opened_window,
                    )
                    if troubleshoot_failure_reason is None:
                        self._wait_or_pause(
                            _TROUBLESHOOT_POST_RECOVERY_SETTLE_SECONDS,
                            snapshot=sequence_snapshot(started=False),
                        )
                        close_failure_reason = self._close_automation_window_for_profile(
                            runtime,
                            opened_window,
                        )
                        if close_failure_reason is not None:
                            self._record_raid_profile_failure(
                                item,
                                profile,
                                close_failure_reason,
                                sequence_id=sequence_id,
                            )
                            return "failed", True, close_failure_reason
                        self._record_raid_profile_recovered(item, profile)
                        return "recovered", True, None
                    if troubleshoot_failure_reason == "stopped":
                        raise UserPauseRequested(snapshot=sequence_snapshot(started=started))
                    page_ready_failure_reason = troubleshoot_failure_reason
                self._record_raid_profile_failure(
                    item,
                    profile,
                    page_ready_failure_reason,
                    sequence_id=sequence_id,
                )
                return "failed", True, page_ready_failure_reason
            anchor_failure_reason = self._move_cursor_to_scroll_anchor(
                runtime,
                opened_window,
                scroll_anchor,
            )
            if anchor_failure_reason is not None:
                self._record_raid_profile_failure(
                    item,
                    profile,
                    anchor_failure_reason,
                    sequence_id=sequence_id,
                )
                return "failed", True, anchor_failure_reason
            self._raise_if_pause_requested(sequence_snapshot(started=started))

        if not started:
            started_at = self.now()
            self._mark_profile_run_started(
                item.normalized_url,
                profile.profile_directory,
                started_at=started_at,
            )
            self._record_activity(
                "automation_started",
                reason="automation_started",
                url=item.normalized_url,
                profile_directory=profile.profile_directory,
                timestamp=started_at,
            )
            self._emit(
                "automation_run_started",
                sequence_id=sequence_id,
                url=item.normalized_url,
                window_handle=opened_window.handle,
                profile_directory=profile.profile_directory,
            )
            started = True
        try:
            result = self._run_sequence_with_runtime_resume(
                runtime,
                sequence,
                selected_window_handle=opened_window.handle,
                start_step_index=start_step_index,
                start_step_phase=start_step_phase,
            )
        except Exception as exc:
            failure_reason = self._reason_from_exception(
                exc,
                "automation_execution_failed",
            )
            self._record_raid_profile_failure(
                item,
                profile,
                failure_reason,
                sequence_id=sequence_id,
            )
            return "failed", True, failure_reason
        status = getattr(result, "status", None)
        failure_reason = getattr(result, "failure_reason", None)
        if status == "stopped":
            raise UserPauseRequested(
                snapshot=sequence_snapshot(
                    start_step_index=max(0, int(getattr(result, "step_index", 0) or 0)),
                    started=started,
                    mode="sequence",
                    step_phase=getattr(result, "step_phase", None),
                )
            )
        if status != "completed":
            failure_reason = failure_reason or "automation_execution_failed"
            self._record_raid_profile_failure(
                item,
                profile,
                failure_reason,
                sequence_id=sequence_id,
            )
            return "failed", True, failure_reason

        close_failure_reason = self._close_automation_window_for_profile(
            runtime,
            opened_window,
            try_page_exit=True,
        )
        if close_failure_reason is not None:
            self._record_raid_profile_failure(
                item,
                profile,
                close_failure_reason,
                sequence_id=sequence_id,
            )
            return "failed", True, close_failure_reason

        self._record_raid_profile_success(
            item,
            profile,
            sequence_id=sequence_id,
        )
        return "succeeded", True, None

    def _close_automation_window(self, _context) -> None:
        return

    def _record_automation_success(
        self,
        _item: PendingRaidWorkItem,
        _context,
    ) -> None:
        self._active_auto_sequence_id = None

    def _record_automation_failure(
        self,
        item: PendingRaidWorkItem,
        reason: str,
        context,
    ) -> None:
        if self._automation_failure_already_recorded:
            self._automation_failure_already_recorded = False
            self._active_auto_sequence_id = None
            return
        reason = self._translate_automation_reason(reason) or "automation_execution_failed"
        self._automation_reserved_urls.discard(item.normalized_url)
        self._record_activity(
            "automation_failed",
            reason=reason,
            url=item.normalized_url,
            emit_error=True,
            count_open_failure=(
                (
                    context is not None
                    and reason not in {"all_profiles_blocked", "auto_run_paused"}
                )
                or reason in {"browser_startup_failure", "chrome_open_failed"}
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

    async def run_raid_now_for_profile(self, profile_directory: str) -> None:
        paused_snapshot = self._paused_execution
        if (
            paused_snapshot is not None
            and paused_snapshot.source == "manual"
            and paused_snapshot.ordered_profile_directories
            and paused_snapshot.ordered_profile_directories[0] == profile_directory
        ):
            self._run_paused_manual_execution(paused_snapshot)
            return

        profile = self._find_profile_by_directory(profile_directory)
        if profile is None:
            raise ValueError(f"Unknown raid profile: {profile_directory}")
        if not (self._profile_runs_warmup(profile) or raid_profile_has_any_actions_enabled(profile)):
            raise ValueError("Profile has no enabled actions configured")
        runtime = self._automation_runtime
        if runtime is None:
            self._ensure_automation_processor()
            runtime = self._automation_runtime
        if runtime is None:
            raise RuntimeError("Automation runtime unavailable")

        detection = await self._find_latest_valid_recent_raid()
        if detection is None or detection.job is None:
            raise ValueError("No recent valid raid found")

        item = PendingRaidWorkItem(
            normalized_url=detection.job.normalized_url,
            trace_id=detection.job.trace_id,
        )
        self._dedupe_store.mark_if_new(item.normalized_url)
        service_dedupe_store = getattr(self._service, "dedupe_store", None)
        if service_dedupe_store is not None and service_dedupe_store is not self._dedupe_store:
            service_dedupe_store.mark_if_new(item.normalized_url)
        self._active_execution_source = "manual"
        self._active_execution_url = item.normalized_url
        try:
            succeeded, failure_reason = self._execute_profiles_for_item(
                source="manual",
                item=item,
                runtime=runtime,
                sequence_id="raid-now",
                ordered_profiles=[profile],
            )
        except UserPauseRequested:
            self._update_user_pause_status(item.normalized_url)
            return
        finally:
            self._active_execution_source = None
            self._active_execution_url = None
        if not succeeded:
            raise RuntimeError(
                self._translate_automation_reason(failure_reason)
                or failure_reason
                or "automation_execution_failed"
            )
        self._recover_automation_queue_after_manual_success()
        if self._automation_processor is None:
            self._update_automation_status("idle", 0, None, None)
            return
        self._sync_automation_status()

    def reset_dashboard_metric(self, metric_key: str) -> None:
        self.state = apply_dashboard_metric_reset(
            self.state,
            metric_key,
            now=self.now(),
        )
        self._persist_state_snapshot()

    def reset_raid_profile(self, profile_directory: str) -> None:
        normalized_directory = str(profile_directory).strip()
        if not normalized_directory:
            return
        profile = next(
            (
                configured_profile
                for configured_profile in self.config.raid_profiles
                if configured_profile.profile_directory == normalized_directory
            ),
            None,
        )
        if profile is None:
            return
        self._set_raid_profile_state(profile, status="green", last_error=None)

    async def reset_all_raid_profiles(
        self,
        raid_on_restart_enabled: bool = False,
    ) -> None:
        for profile in self.config.raid_profiles:
            self._set_raid_profile_state(profile, status="green", last_error=None)
        if not raid_on_restart_enabled:
            return

        runtime = self._automation_runtime
        if runtime is None:
            self._ensure_automation_processor()
            runtime = self._automation_runtime
        if runtime is None:
            raise RuntimeError("Automation runtime unavailable")

        detection = await self._find_latest_valid_recent_raid()
        if detection is None or detection.job is None:
            raise ValueError("No recent valid raid found")

        ordered_profiles = self._profiles_missing_success_for_url(
            detection.job.normalized_url,
            tuple(
                profile
                for profile in self.config.raid_profiles
                if profile.enabled and self._profile_has_runnable_mode(profile)
            ),
        )
        if not ordered_profiles:
            raise ValueError("All profiles already raided latest raid")

        item = PendingRaidWorkItem(
            normalized_url=detection.job.normalized_url,
            trace_id=detection.job.trace_id,
        )
        self._dedupe_store.mark_if_new(item.normalized_url)
        service_dedupe_store = getattr(self._service, "dedupe_store", None)
        if service_dedupe_store is not None and service_dedupe_store is not self._dedupe_store:
            service_dedupe_store.mark_if_new(item.normalized_url)
        self._active_execution_source = "manual"
        self._active_execution_url = item.normalized_url
        try:
            succeeded, failure_reason = self._execute_profiles_for_item(
                source="manual",
                item=item,
                runtime=runtime,
                sequence_id="restart-all",
                ordered_profiles=ordered_profiles,
            )
        except UserPauseRequested:
            self._update_user_pause_status(item.normalized_url)
            return
        finally:
            self._active_execution_source = None
            self._active_execution_url = None
        if not succeeded:
            raise RuntimeError(
                self._translate_automation_reason(failure_reason)
                or failure_reason
                or "automation_execution_failed"
            )
        self._recover_automation_queue_after_manual_success()
        if self._automation_processor is None:
            self._update_automation_status("idle", 0, None, None)
            return
        self._sync_automation_status()

    def _eligible_raid_profiles(self) -> tuple[RaidProfileConfig, ...]:
        profile_states_by_directory = {
            profile_state.profile_directory: profile_state
            for profile_state in self.state.raid_profile_states
        }
        return tuple(
            profile
            for profile in self.config.raid_profiles
            if profile.enabled
            and self._profile_has_runnable_mode(profile)
            and profile_states_by_directory.get(profile.profile_directory) is not None
            and profile_states_by_directory[profile.profile_directory].status != "red"
        )

    def _shuffled_eligible_raid_profiles(self) -> tuple[RaidProfileConfig, ...]:
        profiles = list(self._eligible_raid_profiles())
        self.profile_shuffle(profiles)
        return tuple(profiles)

    def _profile_runs_warmup(self, profile: RaidProfileConfig) -> bool:
        return bool(getattr(profile, "warmup_enabled", False))

    def _current_warmup_cycle_step(self, profile: RaidProfileConfig) -> int:
        cycle_index = getattr(profile, "warmup_cycle_index", 0)
        try:
            normalized = int(cycle_index)
        except (TypeError, ValueError):
            normalized = 0
        return normalized if normalized in {0, 1, 2} else 0

    def _current_warmup_completed_cycles(self, profile: RaidProfileConfig) -> int:
        completed_cycles = getattr(profile, "warmup_completed_cycles", 0)
        try:
            normalized = int(completed_cycles)
        except (TypeError, ValueError):
            normalized = 0
        return min(max(normalized, 0), 20)

    def _advance_warmup_cycle(self, profile: RaidProfileConfig) -> None:
        next_cycle_index = (self._current_warmup_cycle_step(profile) + 1) % 3
        profile.warmup_cycle_index = next_cycle_index
        self._persist_runtime_config()

    def _complete_warmup_cycle(self, profile: RaidProfileConfig) -> None:
        completed_cycles = self._current_warmup_completed_cycles(profile) + 1
        if completed_cycles >= 20:
            profile.warmup_enabled = False
            profile.warmup_cycle_index = 0
            profile.warmup_completed_cycles = 0
            profile.reply_enabled = True
            profile.like_enabled = True
            profile.repost_enabled = True
            profile.bookmark_enabled = False
        else:
            profile.warmup_cycle_index = 0
            profile.warmup_completed_cycles = completed_cycles
        self._persist_runtime_config()

    def _persist_runtime_config(self) -> None:
        self.storage.save_config(self.config)
        self._emit("config_changed", config=self.config)

    def _profile_has_runnable_mode(self, profile: RaidProfileConfig) -> bool:
        if self._profile_runs_warmup(profile):
            return True
        return bool(
            raid_profile_has_any_actions_enabled(profile)
            and any(
                slot.enabled and raid_profile_allows_slot(profile, slot.key)
                for slot in self.config.bot_action_slots
            )
        )

    def _profiles_missing_success_for_url(
        self,
        normalized_url: str,
        profiles: tuple[RaidProfileConfig, ...],
    ) -> tuple[RaidProfileConfig, ...]:
        succeeded_profile_directories = {
            str(entry.profile_directory)
            for entry in self.state.activity
            if entry.action == "automation_succeeded"
            and entry.url == normalized_url
            and entry.profile_directory is not None
        }
        return tuple(
            profile
            for profile in profiles
            if profile.profile_directory not in succeeded_profile_directories
        )

    def _open_url_in_new_window_for_profile(
        self,
        profile: RaidProfileConfig,
        url: str,
        previous_windows,
    ) -> tuple[Any | None, Any | None, str | None]:
        runtime = self._automation_runtime
        if runtime is None:
            return None, None, "automation_runtime_unavailable"
        opener = self._build_chrome_opener_for_profile(profile.profile_directory)
        try:
            context = opener.open_raid_window(url)
        except Exception as exc:
            return None, None, self._reason_from_exception(exc, "chrome_open_failed")
        if self.config.auto_run_settle_ms > 0:
            self.auto_run_wait(self.config.auto_run_settle_ms / 1000.0)
        current_windows = runtime.list_target_windows()
        opened_window = find_opened_raid_window(
            list(previous_windows or ()),
            current_windows,
        )
        if opened_window is None and len(current_windows) == 1:
            opened_window = current_windows[0]
        if opened_window is None:
            return context, None, "target_window_not_found"
        window_manager = getattr(runtime, "window_manager", None)
        if window_manager is not None and hasattr(window_manager, "maximize_window"):
            try:
                window_manager.maximize_window(opened_window)
            except Exception:
                pass
        if window_manager is not None and hasattr(window_manager, "ensure_interactable_window"):
            try:
                interaction = window_manager.ensure_interactable_window(opened_window)
            except Exception:
                interaction = None
            if interaction is None or not getattr(interaction, "success", False):
                return context, None, "window_not_focusable"
            interacted_window = getattr(interaction, "window", None)
            if interacted_window is not None:
                opened_window = interacted_window
        return replace(context, window_handle=opened_window.handle), opened_window, None

    def _open_raid_for_profile(
        self,
        item: PendingRaidWorkItem,
        profile: RaidProfileConfig,
        previous_windows,
    ) -> tuple[Any | None, Any | None, str | None]:
        return self._open_url_in_new_window_for_profile(
            profile,
            item.normalized_url,
            previous_windows,
        )

    def _open_url_in_existing_profile_window(
        self,
        profile: RaidProfileConfig,
        url: str,
        *,
        window_handle: int | None,
    ) -> str | None:
        opener = self._build_chrome_opener_for_profile(profile.profile_directory)
        try:
            opener.open(url, window_handle=window_handle)
        except Exception as exc:
            return self._reason_from_exception(exc, "chrome_open_failed")
        if self.config.auto_run_settle_ms > 0:
            self.auto_run_wait(self.config.auto_run_settle_ms / 1000.0)
        return None

    def _wait_for_page_ready(
        self,
        runtime: Any,
        opened_window: Any,
    ) -> tuple[str | None, tuple[int, int] | None]:
        template_path = self.config.page_ready_template_path
        if template_path is None:
            return None, None
        if not hasattr(runtime, "wait_for_step_match"):
            return "automation_runtime_unavailable", None
        if not template_path.exists():
            return "page_ready_not_found", None
        result = runtime.wait_for_step_match(
            AutomationStep(
                name="page_ready",
                template_path=template_path,
                match_threshold=0.9,
                max_search_seconds=_PAGE_READY_MAX_SEARCH_SECONDS,
                max_scroll_attempts=0,
                scroll_amount=-120,
                max_click_attempts=1,
                post_click_settle_ms=0,
            ),
            opened_window.handle,
            require_interactable_window=False,
        )
        status = getattr(result, "status", None)
        if status == "dry_run_match_found":
            self.auto_run_wait(_PAGE_READY_POST_MATCH_DELAY_SECONDS)
            return None, self._resolve_page_ready_anchor(opened_window, getattr(result, "match", None))
        if status == "stopped":
            return "stopped", None
        failure_reason = getattr(result, "failure_reason", None)
        if failure_reason in {None, "match_not_found"}:
            return "page_ready_not_found", None
        return failure_reason, None

    def _run_sequence_with_runtime_resume(
        self,
        runtime: Any,
        sequence: AutomationSequence,
        *,
        selected_window_handle: int | None,
        start_step_index: int = 0,
        start_step_phase: str | None = None,
    ) -> Any:
        if start_step_index <= 0 and not start_step_phase:
            return runtime.run_sequence(
                sequence,
                selected_window_handle=selected_window_handle,
            )
        try:
            return runtime.run_sequence(
                sequence,
                selected_window_handle=selected_window_handle,
                start_step_index=start_step_index,
                start_step_phase=start_step_phase,
            )
        except TypeError:
            if start_step_phase:
                raise
            resumed_sequence = replace(
                sequence,
                steps=sequence.steps[start_step_index:],
            )
            return runtime.run_sequence(
                resumed_sequence,
                selected_window_handle=selected_window_handle,
            )

    def _storage_base_dir(self) -> Path:
        return Path(getattr(self.storage, "base_dir", Path(".")))

    def _troubleshoot_template_relative_path(
        self,
        group_key: str,
        item_index: int,
    ) -> Path:
        normalized_group_key = str(group_key).strip().lower() or "troubleshoot"
        return (
            Path("bot_actions")
            / "troubleshoot"
            / f"{normalized_group_key}_{item_index + 1}.png"
        )

    def _troubleshoot_template_path(
        self,
        group_key: str,
        item_index: int,
    ) -> Path:
        return self._storage_base_dir() / self._troubleshoot_template_relative_path(
            group_key,
            item_index,
        )

    def _slot_1_obstruction_template_path(self) -> Path | None:
        template_path = self._troubleshoot_template_path("black_box", 0)
        return template_path if template_path.exists() else None

    def _build_troubleshoot_sequence(
        self,
        *,
        group_key: str,
        item_index: int,
        template_path: Path,
    ) -> AutomationSequence:
        step_number = item_index + 1
        return AutomationSequence(
            id=f"troubleshoot-{group_key}-{step_number}",
            name=f"Troubleshoot {str(group_key).upper()} {step_number}",
            steps=[
                AutomationStep(
                    name=f"{group_key}_{step_number}",
                    template_path=template_path,
                    match_threshold=0.9,
                    max_search_seconds=_TROUBLESHOOT_STEP_SEARCH_SECONDS,
                    max_scroll_attempts=0,
                    scroll_amount=-120,
                    max_click_attempts=1,
                    post_click_settle_ms=int(_TROUBLESHOOT_STEP_SETTLE_SECONDS * 1000),
                )
            ],
        )

    def _run_troubleshoot_step(
        self,
        runtime: Any,
        opened_window: Any,
        *,
        group_key: str,
        item_index: int,
    ) -> str | None:
        template_path = self._troubleshoot_template_path(group_key, item_index)
        step_prefix = f"troubleshoot_{group_key}_{item_index + 1}"
        if not template_path.exists():
            return f"{step_prefix}_missing"
        sequence = self._build_troubleshoot_sequence(
            group_key=group_key,
            item_index=item_index,
            template_path=template_path,
        )
        try:
            result = runtime.run_sequence(
                sequence,
                selected_window_handle=opened_window.handle,
            )
        except Exception as exc:
            return self._reason_from_exception(exc, f"{step_prefix}_runtime_error")
        if getattr(result, "status", None) == "completed":
            return None
        failure_reason = getattr(result, "failure_reason", None)
        if failure_reason in {None, "match_not_found"}:
            return f"{step_prefix}_not_found"
        return str(failure_reason)

    def _run_cldf_troubleshoot(
        self,
        runtime: Any,
        opened_window: Any,
    ) -> str | None:
        for item_index in range(3):
            failure_reason = self._run_troubleshoot_step(
                runtime,
                opened_window,
                group_key="cldf",
                item_index=item_index,
            )
            if failure_reason is not None:
                return failure_reason
            if item_index == 0:
                page_ready_failure_reason, _scroll_anchor = self._wait_for_page_ready(
                    runtime,
                    opened_window,
                )
                if page_ready_failure_reason is None:
                    return None
                if page_ready_failure_reason != "page_ready_not_found":
                    return page_ready_failure_reason
        return None

    def _resolve_page_ready_anchor(
        self,
        opened_window: Any,
        match: Any | None,
    ) -> tuple[int, int] | None:
        if match is None or not hasattr(match, "center_x") or not hasattr(match, "center_y"):
            return None
        left, top, _right, _bottom = opened_window.bounds
        return left + int(match.center_x), top + int(match.center_y)

    def _move_cursor_to_scroll_anchor(
        self,
        runtime: Any,
        opened_window: Any,
        anchor_point: tuple[int, int] | None,
    ) -> str | None:
        if not hasattr(runtime, "move_cursor"):
            return None
        if anchor_point is None:
            left, top, right, bottom = opened_window.bounds
            anchor_point = ((left + right) // 2, (top + bottom) // 2)
        try:
            runtime.move_cursor(anchor_point)
        except Exception as exc:
            return self._reason_from_exception(exc, "window_not_focusable")
        return None

    def _resolve_runtime_input_driver(self, runtime: Any) -> Any | None:
        runner = getattr(runtime, "_active_runner", None)
        input_driver = getattr(runner, "input_driver", None)
        if input_driver is not None:
            return input_driver
        input_driver = getattr(runtime, "input_driver", None)
        if input_driver is not None:
            return input_driver
        input_driver_factory = getattr(runtime, "input_driver_factory", None)
        if callable(input_driver_factory):
            try:
                return input_driver_factory()
            except Exception:
                return None
        return None

    def _scroll_active_window(self, runtime: Any, amounts: list[int]) -> str | None:
        input_driver = self._resolve_runtime_input_driver(runtime)
        if input_driver is None or not hasattr(input_driver, "scroll"):
            return "automation_runtime_unavailable"
        try:
            for amount in amounts:
                input_driver.scroll(amount)
        except Exception as exc:
            return self._reason_from_exception(exc, "window_not_focusable")
        return None

    def _hold_key_in_active_window(
        self,
        runtime: Any,
        *,
        key: str,
        seconds: float,
        pause_snapshot_factory: Callable[[float], PausedProfileRunSnapshot] | None = None,
    ) -> str | None:
        input_driver = self._resolve_runtime_input_driver(runtime)
        if input_driver is None or not hasattr(input_driver, "key_down") or not hasattr(
            input_driver, "key_up"
        ):
            return "automation_runtime_unavailable"
        normalized_key = str(key).lower()
        try:
            input_driver.key_down(normalized_key)
        except Exception as exc:
            return self._reason_from_exception(exc, "window_not_focusable")
        remaining_seconds = max(0.0, float(seconds))
        repeat_elapsed = 0.0
        release_failure_reason: str | None = None
        try:
            while remaining_seconds > 0.0:
                self._raise_if_pause_requested(
                    pause_snapshot_factory(remaining_seconds)
                    if pause_snapshot_factory is not None
                    else None
                )
                interval_seconds = min(_PAUSE_WAIT_POLL_SECONDS, remaining_seconds)
                self.auto_run_wait(interval_seconds)
                remaining_seconds = max(0.0, remaining_seconds - interval_seconds)
                repeat_elapsed += interval_seconds
                if (
                    remaining_seconds > 0.0
                    and repeat_elapsed >= _HELD_KEY_REPEAT_INTERVAL_SECONDS
                ):
                    self._raise_if_pause_requested(
                        pause_snapshot_factory(remaining_seconds)
                        if pause_snapshot_factory is not None
                        else None
                    )
                    input_driver.key_down(normalized_key)
                    repeat_elapsed = 0.0
            self._raise_if_pause_requested(
                pause_snapshot_factory(remaining_seconds)
                if pause_snapshot_factory is not None
                else None
            )
        finally:
            try:
                input_driver.key_up(normalized_key)
            except Exception as exc:
                release_failure_reason = self._reason_from_exception(exc, "window_not_focusable")
        if release_failure_reason is not None:
            return release_failure_reason
        return None

    def _run_warmup_hold_block(
        self,
        runtime: Any,
        opened_window: Any,
        *,
        segments: tuple[tuple[str, float], ...],
        pause_snapshot_factory: Callable[
            [tuple[tuple[str, float], ...]],
            PausedProfileRunSnapshot,
        ]
        | None = None,
    ) -> str | None:
        page_ready_failure_reason, scroll_anchor = self._wait_for_page_ready(
            runtime,
            opened_window,
        )
        if page_ready_failure_reason == "stopped":
            raise UserPauseRequested(
                snapshot=(
                    pause_snapshot_factory(tuple(segments))
                    if pause_snapshot_factory is not None
                    else None
                )
            )
        if page_ready_failure_reason is not None:
            return page_ready_failure_reason
        anchor_failure_reason = self._move_cursor_to_scroll_anchor(
            runtime,
            opened_window,
            scroll_anchor,
        )
        if anchor_failure_reason is not None:
            return anchor_failure_reason
        self._wait_or_pause(
            _WARMUP_PAGE_SETTLE_SECONDS,
            snapshot=(
                pause_snapshot_factory(tuple(segments))
                if pause_snapshot_factory is not None
                else None
            ),
        )
        for index, (key, seconds) in enumerate(segments):
            remaining_segments = tuple(segments[index + 1 :])

            def snapshot_for_remaining_duration(
                remaining_duration: float,
                *,
                current_key: str = key,
                trailing_segments: tuple[tuple[str, float], ...] = remaining_segments,
            ) -> PausedProfileRunSnapshot | None:
                if pause_snapshot_factory is None:
                    return None
                return pause_snapshot_factory(
                    ((current_key, remaining_duration),) + trailing_segments
                )

            hold_failure_reason = self._hold_key_in_active_window(
                runtime,
                key=key,
                seconds=seconds,
                pause_snapshot_factory=snapshot_for_remaining_duration,
            )
            if hold_failure_reason is not None:
                return hold_failure_reason
        return None

    def _close_automation_window_for_profile(
        self,
        runtime: Any,
        opened_window: Any,
        *,
        try_page_exit: bool = False,
    ) -> str | None:
        window_manager = getattr(runtime, "window_manager", None)
        if window_manager is not None and hasattr(window_manager, "ensure_interactable_window"):
            try:
                interaction = window_manager.ensure_interactable_window(opened_window)
            except Exception:
                interaction = None
            if interaction is None or not getattr(interaction, "success", False):
                return "window_not_focusable"
            opened_window = getattr(interaction, "window", None) or opened_window
        window_handle = getattr(opened_window, "handle", None)
        input_driver = self._resolve_runtime_input_driver(runtime)
        close_failure_reason: str | None = None
        if input_driver is not None and hasattr(input_driver, "close_active_window"):
            try:
                if hasattr(runtime, "_active_handle"):
                    runtime._active_handle = window_handle
                input_driver.close_active_window()
            except Exception as exc:
                close_failure_reason = self._reason_from_exception(exc, "window_close_failed")
            else:
                if self._wait_for_runtime_window_to_close(runtime, window_handle):
                    return None
        else:
            close_failure_reason = "window_close_failed"
        if try_page_exit:
            current_window = self._find_runtime_window_by_handle(runtime, window_handle) or opened_window
            if self._click_page_exit_for_profile(runtime, current_window):
                if self._wait_for_runtime_window_to_close(runtime, window_handle):
                    return None
        return close_failure_reason or "window_close_failed"

    def _click_page_exit_for_profile(
        self,
        runtime: Any,
        opened_window: Any,
    ) -> bool:
        template_path = self.config.page_exit_template_path
        if template_path is None or not template_path.exists():
            return False
        if not hasattr(runtime, "wait_for_step_match"):
            return False
        input_driver = self._resolve_runtime_input_driver(runtime)
        if input_driver is None or not hasattr(input_driver, "move_click"):
            return False
        result = runtime.wait_for_step_match(
            AutomationStep(
                name="page_exit",
                template_path=template_path,
                match_threshold=0.9,
                max_search_seconds=_PAGE_EXIT_MAX_SEARCH_SECONDS,
                max_scroll_attempts=0,
                scroll_amount=-120,
                max_click_attempts=1,
                post_click_settle_ms=0,
            ),
            opened_window.handle,
            require_interactable_window=False,
        )
        if getattr(result, "status", None) != "dry_run_match_found":
            return False
        match = getattr(result, "match", None)
        if match is None or not hasattr(match, "center_x") or not hasattr(match, "center_y"):
            return False
        left, top, _right, _bottom = opened_window.bounds
        point = (left + int(match.center_x), top + int(match.center_y))
        try:
            input_driver.move_click(point, delay_seconds=0.25)
        except Exception:
            return False
        return True

    def _execute_warmup_for_profile(
        self,
        item: PendingRaidWorkItem,
        profile: RaidProfileConfig,
        *,
        runtime: Any,
        resume_snapshot: PausedProfileRunSnapshot | None = None,
    ) -> tuple[str, bool, str | None]:
        if self._current_warmup_cycle_step(profile) == 2:
            return self._execute_warmup_real_action_for_profile(
                item,
                profile,
                runtime=runtime,
                resume_snapshot=resume_snapshot,
            )
        return self._execute_warmup_browse_for_profile(
            item,
            profile,
            runtime=runtime,
            resume_snapshot=resume_snapshot,
        )

    def _execute_warmup_browse_for_profile(
        self,
        item: PendingRaidWorkItem,
        profile: RaidProfileConfig,
        *,
        runtime: Any,
        resume_snapshot: PausedProfileRunSnapshot | None = None,
    ) -> tuple[str, bool, str | None]:
        if resume_snapshot is not None:
            opened_window = self._find_runtime_window_by_handle(
                runtime,
                resume_snapshot.window_handle,
            )
            if opened_window is None:
                failure_reason = "target_window_not_found"
                self._record_raid_profile_failure(
                    item,
                    profile,
                    failure_reason,
                    sequence_id="warmup-mode",
                )
                return "failed", True, failure_reason
            started = bool(resume_snapshot.started)
            current_mode = resume_snapshot.mode
        else:
            previous_windows = tuple(runtime.list_target_windows())
            _context, opened_window, open_failure_reason = self._open_url_in_new_window_for_profile(
                profile,
                _WARMUP_HOME_URL,
                previous_windows,
            )
            if open_failure_reason is not None or opened_window is None:
                failure_reason = open_failure_reason or "target_window_not_found"
                self._record_raid_profile_failure(
                    item,
                    profile,
                    failure_reason,
                    sequence_id="warmup-mode",
                )
                return "failed", False, failure_reason
            started = False
            current_mode = "warmup_home"

        def warmup_snapshot(
            mode: str,
            *,
            remaining_hold_segments: tuple[tuple[str, float], ...] = (),
        ) -> PausedProfileRunSnapshot:
            return PausedProfileRunSnapshot(
                profile_directory=profile.profile_directory,
                mode=mode,
                window_handle=getattr(opened_window, "handle", None),
                started=started,
                remaining_hold_segments=remaining_hold_segments,
            )

        if not started:
            started_at = self.now()
            self._mark_profile_run_started(
                item.normalized_url,
                profile.profile_directory,
                started_at=started_at,
            )
            self._record_activity(
                "automation_started",
                reason="automation_started",
                url=item.normalized_url,
                profile_directory=profile.profile_directory,
                timestamp=started_at,
            )
            self._emit(
                "automation_run_started",
                sequence_id="warmup-mode",
                url=item.normalized_url,
                window_handle=opened_window.handle,
                profile_directory=profile.profile_directory,
            )
            started = True

        if current_mode == "warmup_home":
            warmup_failure_reason = self._run_warmup_hold_block(
                runtime,
                opened_window,
                segments=(
                    resume_snapshot.remaining_hold_segments
                    if resume_snapshot is not None and resume_snapshot.remaining_hold_segments
                    else _WARMUP_HOME_HOLD_SEGMENTS
                ),
                pause_snapshot_factory=lambda remaining: warmup_snapshot(
                    "warmup_home",
                    remaining_hold_segments=remaining,
                ),
            )
            if warmup_failure_reason is not None:
                self._record_raid_profile_failure(
                    item,
                    profile,
                    warmup_failure_reason,
                    sequence_id="warmup-mode",
                )
                return "failed", True, warmup_failure_reason
            current_mode = "warmup_feed_open"

        if current_mode == "warmup_feed_open":
            self._raise_if_pause_requested(warmup_snapshot("warmup_feed_open"))
            open_feed_failure_reason = self._open_url_in_existing_profile_window(
                profile,
                _WARMUP_FEED_URL,
                window_handle=opened_window.handle,
            )
            if open_feed_failure_reason is not None:
                self._record_raid_profile_failure(
                    item,
                    profile,
                    open_feed_failure_reason,
                    sequence_id="warmup-mode",
                )
                return "failed", True, open_feed_failure_reason
            current_mode = "warmup_feed"

        warmup_failure_reason = self._run_warmup_hold_block(
            runtime,
            opened_window,
            segments=(
                resume_snapshot.remaining_hold_segments
                if resume_snapshot is not None
                and current_mode == "warmup_feed"
                and resume_snapshot.remaining_hold_segments
                else _WARMUP_FEED_HOLD_SEGMENTS
            ),
            pause_snapshot_factory=lambda remaining: warmup_snapshot(
                "warmup_feed",
                remaining_hold_segments=remaining,
            ),
        )
        if warmup_failure_reason is not None:
            self._record_raid_profile_failure(
                item,
                profile,
                warmup_failure_reason,
                sequence_id="warmup-mode",
            )
            return "failed", True, warmup_failure_reason

        close_failure_reason = self._close_automation_window_for_profile(
            runtime,
            opened_window,
            try_page_exit=True,
        )
        if close_failure_reason is not None:
            self._record_raid_profile_failure(
                item,
                profile,
                close_failure_reason,
                sequence_id="warmup-mode",
            )
            return "failed", True, close_failure_reason

        self._advance_warmup_cycle(profile)
        self._record_raid_profile_success(
            item,
            profile,
            sequence_id="warmup-mode",
        )
        return "succeeded", True, None

    def _execute_warmup_real_action_for_profile(
        self,
        item: PendingRaidWorkItem,
        profile: RaidProfileConfig,
        *,
        runtime: Any,
        resume_snapshot: PausedProfileRunSnapshot | None = None,
    ) -> tuple[str, bool, str | None]:
        sequence = (
            resume_snapshot.sequence
            if resume_snapshot is not None and resume_snapshot.sequence is not None
            else self._build_warmup_single_action_sequence(profile)
        )
        if sequence is None:
            failure_reason = self._bot_action_sequence_error or "bot_action_not_configured"
            self._record_raid_profile_failure(
                item,
                profile,
                failure_reason,
                sequence_id="warmup-mode",
            )
            return "failed", False, failure_reason

        outcome, opened, failure_reason = self._execute_raid_for_profile(
            item,
            profile,
            sequence=sequence,
            runtime=runtime,
            sequence_id="warmup-mode",
            resume_snapshot=resume_snapshot,
        )
        if outcome != "succeeded":
            return outcome, opened, failure_reason

        self._complete_warmup_cycle(profile)
        return outcome, opened, failure_reason

    def _build_warmup_single_action_sequence(
        self,
        profile: RaidProfileConfig,
    ):
        candidate_slots = [
            slot
            for slot in self.config.bot_action_slots
            if slot.enabled
            and slot.key != "slot_4_b"
            and slot.template_path is not None
            and slot.template_path.exists()
        ]
        if not candidate_slots:
            self._bot_action_sequence_error = "bot_action_not_configured"
            return None
        self.action_shuffle(candidate_slots)
        for slot in candidate_slots:
            build_result = build_bot_action_sequence(
                [slot],
                slot_1_finish_delay_seconds=self.config.slot_1_finish_delay_seconds,
                slot_1_obstruction_template_path=self._slot_1_obstruction_template_path(),
                choose_preset=build_slot_1_preset_chooser(),
                reorder_slot_1_last=False,
            )
            if build_result.sequence.steps:
                self._bot_action_sequence_error = None
                return build_result.sequence
        self._bot_action_sequence_error = "bot_action_not_configured"
        return None

    def _record_raid_profile_success(
        self,
        item: PendingRaidWorkItem,
        profile: RaidProfileConfig,
        *,
        sequence_id: str,
    ) -> None:
        completed_at = self.now()
        duration_seconds = self._finish_profile_run(
            item.normalized_url,
            profile.profile_directory,
            completed_at=completed_at,
        )
        self._append_successful_profile_run(
            SuccessfulProfileRun(
                timestamp=completed_at,
                duration_seconds=duration_seconds,
            )
        )
        self.state.raids_completed += 1
        self._set_raid_profile_state(
            profile,
            status="green",
            last_error=None,
        )
        self._record_activity(
            "automation_succeeded",
            reason="automation_succeeded",
            url=item.normalized_url,
            profile_directory=profile.profile_directory,
            timestamp=completed_at,
        )
        self._record_activity(
            "session_closed",
            reason="automation_succeeded",
            url=item.normalized_url,
            profile_directory=profile.profile_directory,
        )
        self._emit(
            "automation_run_succeeded",
            sequence_id=sequence_id,
            url=item.normalized_url,
            profile_directory=profile.profile_directory,
        )

    def _record_raid_profile_recovered(
        self,
        item: PendingRaidWorkItem,
        profile: RaidProfileConfig,
    ) -> None:
        self._discard_profile_run_start(
            item.normalized_url,
            profile.profile_directory,
        )
        self._set_raid_profile_state(
            profile,
            status="green",
            last_error=None,
        )
        self._record_activity(
            "session_closed",
            reason="troubleshoot_recovered",
            url=item.normalized_url,
            profile_directory=profile.profile_directory,
        )

    def _record_raid_profile_failure(
        self,
        item: PendingRaidWorkItem,
        profile: RaidProfileConfig,
        reason: str,
        *,
        sequence_id: str,
    ) -> None:
        self._discard_profile_run_start(
            item.normalized_url,
            profile.profile_directory,
        )
        translated_reason = self._translate_automation_reason(reason) or "automation_execution_failed"
        self.state.raids_failed += 1
        self._set_raid_profile_state(
            profile,
            status="red",
            last_error=translated_reason,
        )
        self._record_activity(
            "automation_failed",
            reason=translated_reason,
            url=item.normalized_url,
            profile_directory=profile.profile_directory,
            emit_error=True,
            count_open_failure=True,
        )
        self._emit(
            "automation_run_failed",
            sequence_id=sequence_id,
            url=item.normalized_url,
            reason=translated_reason,
            profile_directory=profile.profile_directory,
        )

    def _set_raid_profile_state(
        self,
        profile: RaidProfileConfig,
        *,
        status: str,
        last_error: str | None,
    ) -> None:
        updated_states: list[RaidProfileState] = []
        updated = False
        for profile_state in self.state.raid_profile_states:
            if profile_state.profile_directory != profile.profile_directory:
                updated_states.append(profile_state)
                continue
            updated = True
            updated_states.append(
                RaidProfileState(
                    profile_directory=profile.profile_directory,
                    label=profile.label,
                    status=status,
                    last_error=last_error,
                )
            )
        if not updated:
            updated_states.append(
                RaidProfileState(
                    profile_directory=profile.profile_directory,
                    label=profile.label,
                    status=status,
                    last_error=last_error,
                )
            )
        self.state.raid_profile_states = tuple(updated_states)
        self.storage.save_state(self.state)
        self._emit("stats_changed", state=self.state)

    def _sync_raid_profile_states(self, *, save: bool, emit: bool) -> None:
        existing_states = {
            profile_state.profile_directory: profile_state
            for profile_state in self.state.raid_profile_states
        }
        normalized_states = tuple(
            RaidProfileState(
                profile_directory=profile.profile_directory,
                label=profile.label,
                status=(
                    existing_states[profile.profile_directory].status
                    if profile.profile_directory in existing_states
                    else "green"
                ),
                last_error=(
                    existing_states[profile.profile_directory].last_error
                    if profile.profile_directory in existing_states
                    else None
                ),
            )
            for profile in self.config.raid_profiles
        )
        if normalized_states == self.state.raid_profile_states:
            return
        self.state.raid_profile_states = normalized_states
        if save:
            self.storage.save_state(self.state)
        if emit:
            self._emit("stats_changed", state=self.state)

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
            if processor.state in {"paused", "suspended"} or self._user_paused:
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
        profile_directory: str | None = None,
        emit_error: bool = False,
        count_open_failure: bool = True,
        timestamp: datetime | None = None,
    ) -> None:
        timestamp = timestamp or self.now()
        if action == "raid_detected":
            self.state.raids_detected += 1
        elif action == "browser_session_opened":
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
            self.state.raids_failed += 1
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
            self.state.raids_completed += 1
            self._append_successful_profile_run(
                SuccessfulProfileRun(timestamp=timestamp, duration_seconds=None)
            )
        elif action == "executor_failed":
            self.state.executor_failed += 1
            self.state.raids_failed += 1
            self.state.last_error = reason
        elif action == "session_closed":
            self.state.session_closed += 1

        entry = ActivityEntry(
            timestamp=timestamp,
            action=action,
            url=url,
            reason=reason,
            profile_directory=profile_directory,
        )
        self.state.activity = [*self.state.activity, entry][-200:]
        self._persist_state_snapshot()
        self._emit("activity_added", entry=entry)
        if emit_error:
            self._emit("error", message=reason or action)

    def _mark_profile_run_started(
        self,
        url: str,
        profile_directory: str,
        *,
        started_at: datetime,
    ) -> None:
        self._pending_profile_run_starts[(url, profile_directory)] = started_at

    def _finish_profile_run(
        self,
        url: str,
        profile_directory: str,
        *,
        completed_at: datetime,
    ) -> float | None:
        started_at = self._pending_profile_run_starts.pop((url, profile_directory), None)
        if started_at is None or completed_at < started_at:
            return None
        return (completed_at - started_at).total_seconds()

    def _discard_profile_run_start(
        self,
        url: str,
        profile_directory: str,
    ) -> None:
        self._pending_profile_run_starts.pop((url, profile_directory), None)

    def _append_successful_profile_run(self, entry: SuccessfulProfileRun) -> None:
        self.state.successful_profile_runs = [
            *self.state.successful_profile_runs,
            entry,
        ][-_SUCCESSFUL_PROFILE_RUN_LIMIT:]

    def _record_whole_raid_opened(self) -> None:
        self.state.raids_opened += 1
        self.state.last_successful_raid_open_at = self.now().isoformat()
        self._persist_state_snapshot()

    def _record_whole_raid_completed(self) -> None:
        self._persist_state_snapshot()

    def _record_whole_raid_failed(self) -> None:
        self._persist_state_snapshot()

    def _persist_state_snapshot(self) -> None:
        self.storage.save_state(self.state)
        self._emit("stats_changed", state=self.state)

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

    def _build_recent_raid_lookup_service(self) -> RaidService:
        return RaidService(
            allowed_chat_ids=set(self.config.whitelisted_chat_ids),
            allowed_sender_ids=set(self.config.allowed_sender_ids),
            dedupe_store=InMemoryOpenedUrlStore(),
            preset_replies=self.config.preset_replies,
            default_requirements=self._default_requirements(self.config),
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
        self._chrome_opener = self._build_chrome_opener_for_profile(
            self.config.chrome_profile_directory
        )
        return self._chrome_opener

    def _build_chrome_opener_for_profile(self, profile_directory: str) -> Any:
        cached_opener = self._chrome_openers.get(profile_directory)
        if cached_opener is not None:
            return cached_opener
        chrome_environment = self.chrome_environment_factory()
        if chrome_environment is None:
            raise RuntimeError("Chrome environment is unavailable")
        if self.chrome_opener_factory is not None:
            opener = self.chrome_opener_factory(
                chrome_path=chrome_environment.chrome_path,
                user_data_dir=chrome_environment.user_data_dir,
                profile_directory=profile_directory,
            )
        else:
            opener = ChromeOpener(
                chrome_path=chrome_environment.chrome_path,
                user_data_dir=chrome_environment.user_data_dir,
                profile_directory=profile_directory,
            )
        self._chrome_openers[profile_directory] = opener
        return opener

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

    def _default_telegram_setup_service_factory(self, config: DesktopAppConfig) -> Any:
        from raidbot.desktop.telegram_setup import TelegramSetupService

        return TelegramSetupService(
            api_id=config.telegram_api_id,
            api_hash=config.telegram_api_hash,
            session_path=config.telegram_session_path,
        )

    async def _list_recent_allowed_messages(
        self,
        *,
        message_limit: int = 50,
    ) -> list[IncomingMessage]:
        listener = self._listener
        client = getattr(listener, "client", None)
        if client is None or not hasattr(client, "iter_messages"):
            raise RuntimeError("Telegram recent lookup unavailable")
        ordered_messages: list[tuple[float, int, IncomingMessage]] = []
        insertion_index = 0
        for chat_id in self.config.whitelisted_chat_ids:
            normalized_chat_id = int(chat_id)
            async for message in client.iter_messages(normalized_chat_id, limit=message_limit):
                sender_id = getattr(message, "sender_id", None)
                if sender_id is None:
                    continue
                message_date = getattr(message, "date", None)
                if isinstance(message_date, datetime):
                    sort_key = float(message_date.timestamp())
                else:
                    sort_key = float("-inf")
                ordered_messages.append(
                    (
                        sort_key,
                        insertion_index,
                        IncomingMessage(
                            chat_id=int(getattr(message, "chat_id", normalized_chat_id)),
                            sender_id=int(sender_id),
                            text=str(getattr(message, "raw_text", "") or ""),
                            has_video=bool(getattr(message, "video", None)),
                        ),
                    )
                )
                insertion_index += 1
        ordered_messages.sort(key=lambda item: (item[0], -item[1]), reverse=True)
        return [message for _sort_key, _index, message in ordered_messages]

    async def _find_latest_valid_recent_raid(self) -> RaidDetectionResult | None:
        lookup_service = self._build_recent_raid_lookup_service()
        for message in await self._list_recent_allowed_messages():
            detection = lookup_service.handle_message(message)
            if detection.kind == "job_detected":
                return detection
        return None

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

    def _reason_from_exception(self, exc: Exception, fallback: str) -> str:
        message = str(exc).strip()
        return message or fallback

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
