from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime
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
from raidbot.desktop.automation.autorun import AutoRunProcessor, PendingRaidWorkItem
from raidbot.desktop.automation.models import AutomationStep
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
    MessageOutcome,
    RaidActionRequirements,
    RaidDetectionResult,
    RaidExecutionResult,
)

_PAGE_READY_POST_MATCH_DELAY_SECONDS = 0.5
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


@dataclass
class _LatestReplayableRaid:
    url: str
    succeeded_profiles: set[str]
    failed_profiles: set[str]


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
        self.chrome_environment_factory = chrome_environment_factory
        self.manual_run_active = manual_run_active or (lambda: False)
        self.auto_run_wait = auto_run_wait or time.sleep
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
        self._latest_replayable_raid: _LatestReplayableRaid | None = None
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
        enabled_slots = tuple(
            slot
            for slot in self.config.bot_action_slots
            if slot.enabled
            and (profile is None or raid_profile_allows_slot(profile, slot.key))
        )
        if not enabled_slots:
            self._bot_action_sequence_error = "bot_action_not_configured"
            return None
        if any(slot.template_path is None or not slot.template_path.exists() for slot in enabled_slots):
            self._bot_action_sequence_error = "captured_image_missing"
            return None
        self._bot_action_sequence_error = None
        if choose_preset is None:
            return build_bot_action_sequence(
                enabled_slots,
                slot_1_finish_delay_seconds=self.config.slot_1_finish_delay_seconds,
            )
        return build_bot_action_sequence(
            enabled_slots,
            slot_1_finish_delay_seconds=self.config.slot_1_finish_delay_seconds,
            choose_preset=choose_preset,
        )

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

    def _execute_automation_sequence(
        self,
        item: PendingRaidWorkItem,
        _context,
        sequence_id: str,
    ) -> tuple[bool, str | None]:
        runtime = self._automation_runtime
        if runtime is None:
            return False, "automation_runtime_unavailable"
        preset_chooser = build_slot_1_preset_chooser()
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
        all_enabled_profiles = tuple(
            profile
            for profile in self.config.raid_profiles
            if profile.enabled and raid_profile_has_any_actions_enabled(profile)
        )
        self._begin_latest_replayable_raid(item.normalized_url, all_enabled_profiles)
        eligible_profiles = self._eligible_raid_profiles()
        if not eligible_profiles:
            return False, "all_profiles_blocked"

        raid_opened = False
        raid_succeeded = False
        failure_recorded = False
        last_failure_reason: str | None = None
        for profile in eligible_profiles:
            profile_sequence = self._build_active_bot_action_sequence_result(
                choose_preset=preset_chooser,
                profile=profile,
            )
            sequence = profile_sequence.sequence if profile_sequence is not None else None
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
            succeeded, opened, failure_reason = self._execute_raid_for_profile(
                item,
                profile,
                sequence=sequence,
                runtime=runtime,
                sequence_id=sequence_id,
            )
            if opened and not raid_opened:
                self._record_whole_raid_opened()
                raid_opened = True
            if not succeeded:
                last_failure_reason = failure_reason
                failure_recorded = True
                continue
            raid_succeeded = True

        if raid_succeeded:
            self._record_whole_raid_completed()
            return True, None

        self._record_whole_raid_failed()
        self._automation_failure_already_recorded = failure_recorded
        return False, last_failure_reason or "automation_execution_failed"

    def _begin_latest_replayable_raid(
        self,
        url: str,
        profiles: tuple[RaidProfileConfig, ...],
    ) -> None:
        self._latest_replayable_raid = _LatestReplayableRaid(
            url=url,
            succeeded_profiles=set(),
            failed_profiles={profile.profile_directory for profile in profiles},
        )

    def _mark_latest_replayable_raid_profile_succeeded(
        self,
        profile_directory: str,
    ) -> None:
        replayable_raid = self._latest_replayable_raid
        if replayable_raid is None:
            return
        replayable_raid.succeeded_profiles.add(profile_directory)
        replayable_raid.failed_profiles.discard(profile_directory)

    def _mark_latest_replayable_raid_profile_failed(
        self,
        profile_directory: str,
    ) -> None:
        replayable_raid = self._latest_replayable_raid
        if replayable_raid is None:
            return
        replayable_raid.succeeded_profiles.discard(profile_directory)
        replayable_raid.failed_profiles.add(profile_directory)

    def _execute_raid_for_profile(
        self,
        item: PendingRaidWorkItem,
        profile: RaidProfileConfig,
        *,
        sequence,
        runtime: Any,
        sequence_id: str,
    ) -> tuple[bool, bool, str | None]:
        previous_windows = tuple(runtime.list_target_windows())
        profile_context, opened_window, open_failure_reason = self._open_raid_for_profile(
            item,
            profile,
            previous_windows,
        )
        if open_failure_reason is not None or profile_context is None or opened_window is None:
            failure_reason = open_failure_reason or "target_window_not_found"
            self._record_raid_profile_failure(
                item,
                profile,
                failure_reason,
                sequence_id=sequence_id,
            )
            return False, False, failure_reason

        page_ready_failure_reason, scroll_anchor = self._wait_for_page_ready(
            runtime,
            opened_window,
        )
        if page_ready_failure_reason is not None:
            self._record_raid_profile_failure(
                item,
                profile,
                page_ready_failure_reason,
                sequence_id=sequence_id,
            )
            return False, True, page_ready_failure_reason
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
            return False, True, anchor_failure_reason

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
        try:
            result = runtime.run_sequence(
                sequence,
                selected_window_handle=opened_window.handle,
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
            return False, True, failure_reason
        status = getattr(result, "status", None)
        failure_reason = getattr(result, "failure_reason", None)
        if status != "completed":
            failure_reason = failure_reason or "automation_execution_failed"
            self._record_raid_profile_failure(
                item,
                profile,
                failure_reason,
                sequence_id=sequence_id,
            )
            return False, True, failure_reason

        close_failure_reason = self._close_automation_window_for_profile(runtime)
        if close_failure_reason is not None:
            self._record_raid_profile_failure(
                item,
                profile,
                close_failure_reason,
                sequence_id=sequence_id,
            )
            return False, True, close_failure_reason

        self._record_raid_profile_success(
            item,
            profile,
            sequence_id=sequence_id,
        )
        return True, True, None

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

    def restart_raid_profile(self, profile_directory: str) -> None:
        profile_config = next(
            (
                profile
                for profile in self.config.raid_profiles
                if profile.profile_directory == profile_directory
            ),
            None,
        )
        updated_states: list[RaidProfileState] = []
        updated = False
        for profile_state in self.state.raid_profile_states:
            if profile_state.profile_directory != profile_directory:
                updated_states.append(profile_state)
                continue
            updated = True
            updated_states.append(
                replace(
                    profile_state,
                    status="green",
                    last_error=None,
                )
            )
        if not updated:
            return
        self.state.raid_profile_states = tuple(updated_states)
        self.storage.save_state(self.state)
        self._emit("stats_changed", state=self.state)
        processor = self._automation_processor
        if processor is not None and processor.state == "paused":
            processor.clear()
            self._sync_automation_status()
        if (
            profile_config is None
            or not profile_config.raid_on_restart
            or self._latest_replayable_raid is None
        ):
            return
        self._replay_latest_raid_for_restart()

    def reset_dashboard_metric(self, metric_key: str) -> None:
        self.state = apply_dashboard_metric_reset(
            self.state,
            metric_key,
            now=self.now(),
        )
        self._persist_state_snapshot()

    def _replay_latest_raid_for_restart(self) -> None:
        latest_replayable_raid = self._latest_replayable_raid
        if latest_replayable_raid is None or not latest_replayable_raid.failed_profiles:
            return
        if not self._auto_run_requested() or self._is_inactive():
            return
        runtime = self._automation_runtime
        if runtime is None:
            self._ensure_automation_processor()
            runtime = self._automation_runtime
        if runtime is None:
            return
        preset_chooser = build_slot_1_preset_chooser()
        build_result = self._build_active_bot_action_sequence_result()
        if build_result is None:
            return
        replay_profiles = tuple(
            profile
            for profile in self.config.raid_profiles
            if profile.enabled
            and raid_profile_has_any_actions_enabled(profile)
            and any(
                slot.enabled and raid_profile_allows_slot(profile, slot.key)
                for slot in self.config.bot_action_slots
            )
            and profile.raid_on_restart
            and profile.profile_directory in latest_replayable_raid.failed_profiles
            and profile.profile_directory not in latest_replayable_raid.succeeded_profiles
            and any(
                profile_state.profile_directory == profile.profile_directory
                and profile_state.status == "green"
                for profile_state in self.state.raid_profile_states
            )
        )
        if not replay_profiles:
            return
        item = PendingRaidWorkItem(
            normalized_url=latest_replayable_raid.url,
            trace_id="raid-on-restart",
        )
        sequence_id = build_result.sequence.id
        for profile in replay_profiles:
            profile_sequence = self._build_active_bot_action_sequence_result(
                choose_preset=preset_chooser,
                profile=profile,
            )
            sequence = profile_sequence.sequence if profile_sequence is not None else None
            if sequence is None:
                self._record_raid_profile_failure(
                    item,
                    profile,
                    self._translate_automation_reason("default_sequence_missing")
                    or "bot_action_not_configured",
                    sequence_id=sequence_id,
                )
                continue
            self._execute_raid_for_profile(
                item,
                profile,
                sequence=sequence,
                runtime=runtime,
                sequence_id=sequence_id,
            )

    def _eligible_raid_profiles(self) -> tuple[RaidProfileConfig, ...]:
        profile_states_by_directory = {
            profile_state.profile_directory: profile_state
            for profile_state in self.state.raid_profile_states
        }
        return tuple(
            profile
            for profile in self.config.raid_profiles
            if profile.enabled
            and raid_profile_has_any_actions_enabled(profile)
            and any(
                slot.enabled and raid_profile_allows_slot(profile, slot.key)
                for slot in self.config.bot_action_slots
            )
            and profile_states_by_directory.get(profile.profile_directory) is not None
            and profile_states_by_directory[profile.profile_directory].status != "red"
        )

    def _open_raid_for_profile(
        self,
        item: PendingRaidWorkItem,
        profile: RaidProfileConfig,
        previous_windows,
    ) -> tuple[Any | None, Any | None, str | None]:
        runtime = self._automation_runtime
        if runtime is None:
            return None, None, "automation_runtime_unavailable"
        opener = self._build_chrome_opener_for_profile(profile.profile_directory)
        try:
            context = opener.open_raid_window(item.normalized_url)
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
                max_search_seconds=8.0,
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
        failure_reason = getattr(result, "failure_reason", None)
        if failure_reason in {None, "match_not_found"}:
            return "page_ready_not_found", None
        return failure_reason, None

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

    def _close_automation_window_for_profile(self, runtime: Any) -> str | None:
        runner = getattr(runtime, "_active_runner", None)
        input_driver = getattr(runner, "input_driver", None)
        if input_driver is None or not hasattr(input_driver, "close_active_window"):
            return None
        try:
            input_driver.close_active_window()
        except Exception as exc:
            return self._reason_from_exception(exc, "window_close_failed")
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
        self._mark_latest_replayable_raid_profile_succeeded(profile.profile_directory)
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
        self._mark_latest_replayable_raid_profile_failed(profile.profile_directory)
        translated_reason = self._translate_automation_reason(reason) or "automation_execution_failed"
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
        self.state.raids_completed += 1
        self._persist_state_snapshot()

    def _record_whole_raid_failed(self) -> None:
        self.state.raids_failed += 1
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
