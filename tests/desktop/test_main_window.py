from __future__ import annotations

import os
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QObject, QRect, Qt, Signal
from PySide6.QtGui import QCloseEvent, QColor, QIcon, QImage
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QPushButton,
    QScrollArea,
    QSystemTrayIcon,
    QWidget,
)

from raidbot.desktop.automation.models import AutomationSequence, AutomationStep
from raidbot.desktop.automation.windowing import WindowInfo
from raidbot.desktop.main_window import (
    ActivityBadge,
    ActivityFeedRow,
    MainWindow,
    RaidActivityChart,
)
from raidbot.desktop.models import (
    ActivityEntry,
    BotActionPreset,
    BotActionSlotConfig,
    BotRuntimeState,
    DashboardMetricResetState,
    DesktopAppConfig,
    DesktopAppState,
    RaidProfileConfig,
    RaidProfileState,
    SuccessfulProfileRun,
    TelegramConnectionState,
)
from raidbot.desktop.telegram_setup import AccessibleChat, RaidarCandidate, SessionStatus


def build_config(**overrides) -> DesktopAppConfig:
    values = {
        "telegram_api_id": 123456,
        "telegram_api_hash": "hash-value",
        "telegram_session_path": Path("raidbot.session"),
        "telegram_phone_number": "+40123456789",
        "whitelisted_chat_ids": [-1001],
        "allowed_sender_ids": [42],
        "allowed_sender_entries": ("42",),
        "chrome_profile_directory": "Profile 3",
        "browser_mode": "launch-only",
        "executor_name": "noop",
        "preset_replies": ("gm",),
        "default_action_like": True,
        "default_action_repost": True,
        "default_action_bookmark": False,
        "default_action_reply": True,
    }
    values.update(overrides)
    return DesktopAppConfig(**values)


def build_sequence(sequence_id: str = "seq-1") -> AutomationSequence:
    return AutomationSequence(
        id=sequence_id,
        name="Chrome Flow",
        target_window_rule="RaidBot",
        steps=[
            AutomationStep(
                name="Open menu",
                template_path=Path("templates/menu.png"),
                match_threshold=0.9,
                max_search_seconds=1.0,
                max_scroll_attempts=1,
                scroll_amount=-120,
                max_click_attempts=1,
                post_click_settle_ms=100,
            )
        ],
    )


def build_window_info(handle: int = 7, title: str = "RaidBot - Chrome") -> WindowInfo:
    return WindowInfo(
        handle=handle,
        title=title,
        bounds=(0, 0, 100, 100),
        last_focused_at=1.0,
    )


class FakeStorage:
    def __init__(
        self,
        *,
        state: DesktopAppState | None = None,
        config: DesktopAppConfig | None = None,
        base_dir: Path | None = None,
    ) -> None:
        self._state = state or DesktopAppState()
        self._config = config or build_config()
        self.base_dir = base_dir or Path(".")

    def load_state(self) -> DesktopAppState:
        return self._state

    def load_config(self) -> DesktopAppConfig:
        return self._config


class FakeTelegramSetupService:
    async def authorize(self, **_kwargs) -> SessionStatus:
        return SessionStatus.authorized

    async def list_accessible_chats(self) -> list[AccessibleChat]:
        return [AccessibleChat(chat_id=-1001, title="Raid Group")]

    async def infer_recent_sender_candidates(self, _chat_ids) -> list[RaidarCandidate]:
        return [RaidarCandidate(entity_id=42, label="@raidar")]


class FakeController(QObject):
    botStateChanged = Signal(str)
    connectionStateChanged = Signal(str)
    statsChanged = Signal(object)
    activityAdded = Signal(object)
    errorRaised = Signal(str)
    automationSequencesChanged = Signal(object)
    automationRunEvent = Signal(object)
    botActionRunEvent = Signal(object)
    automationRunStateChanged = Signal(str)
    automationQueueStateChanged = Signal(str)
    automationQueueLengthChanged = Signal(int)
    automationCurrentUrlChanged = Signal(object)
    configChanged = Signal(object)

    def __init__(self, config: DesktopAppConfig | None = None) -> None:
        super().__init__()
        self.config = config or build_config()
        self.start_calls = 0
        self.stop_calls = 0
        self.automation_stop_calls = 0
        self.apply_calls = []
        self.saved_sequences = [build_sequence()]
        self.deleted_sequence_ids = []
        self.automation_run_calls = []
        self.automation_dry_run_calls = []
        self.page_ready_template_updates = []
        self.bot_action_slot_template_updates = []
        self.bot_action_slot_1_presets_updates = []
        self.bot_action_slot_test_calls = []
        self.bot_action_slot_enabled_updates = []
        self.auto_run_settle_ms_updates = []
        self.slot_1_finish_delay_seconds_updates = []
        self.raid_profile_add_calls = []
        self.raid_profile_remove_calls = []
        self.raid_profile_move_calls = []
        self.raid_profile_raid_on_restart_updates = []
        self.raid_profile_action_override_updates = []
        self.restart_raid_profile_calls = []
        self.dashboard_metric_reset_requests = []
        self.sender_candidate_scan_calls = []
        self.sender_candidate_results = [RaidarCandidate(entity_id=42, label="@raidar")]
        self.available_windows = [build_window_info()]
        self.active = False
        self.botStateChanged.connect(self._sync_active_state)

    def start_bot(self) -> None:
        self.start_calls += 1
        self.active = True

    def stop_bot(self) -> None:
        self.stop_calls += 1
        self.active = False

    def stop_bot_and_wait(self) -> bool:
        self.stop_calls += 1
        self.active = False
        return True

    def apply_config(self, config: DesktopAppConfig) -> None:
        self.config = config
        self.apply_calls.append(config)
        self.configChanged.emit(config)

    def is_bot_active(self) -> bool:
        return self.active

    def list_automation_sequences(self):
        return list(self.saved_sequences)

    def save_automation_sequence(self, sequence: AutomationSequence) -> None:
        self.saved_sequences = [
            item for item in self.saved_sequences if item.id != sequence.id
        ] + [sequence]
        self.automationSequencesChanged.emit(self.list_automation_sequences())

    def delete_automation_sequence(self, sequence_id: str) -> None:
        self.deleted_sequence_ids.append(sequence_id)
        self.saved_sequences = [
            item for item in self.saved_sequences if item.id != sequence_id
        ]
        if self.config.default_auto_sequence_id == sequence_id:
            self.apply_config(
                build_config(
                    **{
                        **self.config.__dict__,
                        "default_auto_sequence_id": None,
                    }
                )
            )
        self.automationSequencesChanged.emit(self.list_automation_sequences())

    def list_target_windows(self):
        return list(self.available_windows)

    def start_automation_run(
        self, sequence_id: str, selected_window_handle: int | None
    ) -> None:
        self.automation_run_calls.append((sequence_id, selected_window_handle))

    def dry_run_automation_step(
        self,
        sequence_id: str,
        step_index: int,
        selected_window_handle: int | None,
    ) -> None:
        self.automation_dry_run_calls.append(
            (sequence_id, step_index, selected_window_handle)
        )

    def stop_automation_run(self) -> None:
        self.automation_stop_calls += 1

    def resume_automation_queue(self) -> None:
        self.automation_resume_calls = getattr(self, "automation_resume_calls", 0) + 1

    def clear_automation_queue(self) -> None:
        self.automation_clear_calls = getattr(self, "automation_clear_calls", 0) + 1

    def set_auto_run_enabled(self, enabled: bool) -> None:
        self.apply_config(
            build_config(
                **{
                    **self.config.__dict__,
                    "auto_run_enabled": enabled,
                }
            )
        )

    def set_default_auto_sequence_id(self, sequence_id: str | None) -> None:
        self.apply_config(
            build_config(
                **{
                    **self.config.__dict__,
                    "default_auto_sequence_id": sequence_id,
                }
            )
        )

    def set_auto_run_settle_ms(self, settle_ms: int) -> None:
        self.auto_run_settle_ms_updates.append(settle_ms)
        self.apply_config(
            build_config(
                **{
                    **self.config.__dict__,
                    "auto_run_settle_ms": settle_ms,
                }
            )
        )

    def set_slot_1_finish_delay_seconds(self, finish_delay_seconds: int) -> None:
        self.slot_1_finish_delay_seconds_updates.append(finish_delay_seconds)
        self.apply_config(
            build_config(
                **{
                    **self.config.__dict__,
                    "slot_1_finish_delay_seconds": finish_delay_seconds,
                }
            )
        )

    def set_page_ready_template_path(self, template_path: Path | None) -> None:
        self.page_ready_template_updates.append(template_path)
        if self.config.page_ready_template_path == template_path:
            return
        self.apply_config(replace(self.config, page_ready_template_path=template_path))

    def set_bot_action_slot_template_path(
        self, slot_index: int, template_path: Path | None
    ) -> None:
        self.bot_action_slot_template_updates.append((slot_index, template_path))
        if self.config.bot_action_slots[slot_index].template_path == template_path:
            return
        updated_slots = list(self.config.bot_action_slots)
        updated_slots[slot_index] = replace(
            updated_slots[slot_index],
            template_path=template_path,
        )
        self.apply_config(replace(self.config, bot_action_slots=tuple(updated_slots)))

    def set_bot_action_slot_enabled(self, slot_index: int, enabled: bool) -> None:
        self.bot_action_slot_enabled_updates.append((slot_index, enabled))
        if self.config.bot_action_slots[slot_index].enabled == enabled:
            return
        updated_slots = list(self.config.bot_action_slots)
        updated_slots[slot_index] = replace(
            updated_slots[slot_index],
            enabled=enabled,
        )
        self.apply_config(replace(self.config, bot_action_slots=tuple(updated_slots)))

    def set_bot_action_slot_1_presets(
        self,
        *,
        presets: tuple[BotActionPreset, ...],
        finish_template_path: Path | None,
    ) -> None:
        self.bot_action_slot_1_presets_updates.append(
            (presets, finish_template_path)
        )
        updated_slots = list(self.config.bot_action_slots)
        updated_slots[0] = replace(
            updated_slots[0],
            presets=presets,
            finish_template_path=finish_template_path,
        )
        self.apply_config(replace(self.config, bot_action_slots=tuple(updated_slots)))

    def test_bot_action_slot(self, slot_index: int) -> None:
        self.bot_action_slot_test_calls.append(slot_index)

    def add_raid_profile(self, profile_directory: str, label: str) -> None:
        self.raid_profile_add_calls.append((profile_directory, label))
        if any(
            profile.profile_directory == profile_directory
            for profile in self.config.raid_profiles
        ):
            return
        self.apply_config(
            replace(
                self.config,
                chrome_profile_directory=self.config.raid_profiles[0].profile_directory,
                raid_profiles=(
                    *self.config.raid_profiles,
                    RaidProfileConfig(
                        profile_directory=profile_directory,
                        label=label,
                        enabled=True,
                    ),
                ),
            )
        )

    def remove_raid_profile(self, profile_directory: str) -> None:
        self.raid_profile_remove_calls.append(profile_directory)

    def move_raid_profile(self, profile_directory: str, direction: str) -> None:
        self.raid_profile_move_calls.append((profile_directory, direction))
        profiles = list(self.config.raid_profiles)
        current_index = next(
            (
                index
                for index, profile in enumerate(profiles)
                if profile.profile_directory == profile_directory
            ),
            None,
        )
        if current_index is None:
            return
        target_index = current_index - 1 if direction == "up" else current_index + 1
        if target_index < 0 or target_index >= len(profiles):
            return
        profiles[current_index], profiles[target_index] = (
            profiles[target_index],
            profiles[current_index],
        )
        self.apply_config(
            replace(
                self.config,
                chrome_profile_directory=profiles[0].profile_directory,
                raid_profiles=tuple(profiles),
            )
        )

    def restart_raid_profile(self, profile_directory: str) -> None:
        self.restart_raid_profile_calls.append(profile_directory)

    def set_raid_profile_raid_on_restart(
        self,
        profile_directory: str,
        enabled: bool,
    ) -> None:
        self.raid_profile_raid_on_restart_updates.append((profile_directory, enabled))
        updated_profiles = tuple(
            replace(profile, raid_on_restart=enabled)
            if profile.profile_directory == profile_directory
            else profile
            for profile in self.config.raid_profiles
        )
        self.apply_config(replace(self.config, raid_profiles=updated_profiles))

    def set_raid_profile_action_overrides(
        self,
        profile_directory: str,
        *,
        reply_enabled: bool,
        like_enabled: bool,
        repost_enabled: bool,
        bookmark_enabled: bool,
    ) -> None:
        update = {
            "profile_directory": profile_directory,
            "reply_enabled": reply_enabled,
            "like_enabled": like_enabled,
            "repost_enabled": repost_enabled,
            "bookmark_enabled": bookmark_enabled,
        }
        self.raid_profile_action_override_updates.append(update)
        updated_profiles = tuple(
            replace(
                profile,
                reply_enabled=reply_enabled,
                like_enabled=like_enabled,
                repost_enabled=repost_enabled,
                bookmark_enabled=bookmark_enabled,
            )
            if profile.profile_directory == profile_directory
            else profile
            for profile in self.config.raid_profiles
        )
        self.apply_config(replace(self.config, raid_profiles=updated_profiles))

    def reset_dashboard_metric(self, metric_key: str) -> None:
        self.dashboard_metric_reset_requests.append(metric_key)

    def infer_recent_sender_candidates(self, chat_ids: list[int]):
        self.sender_candidate_scan_calls.append(list(chat_ids))
        return list(self.sender_candidate_results)

    def _sync_active_state(self, state: str) -> None:
        self.active = state in {"starting", "running", "stopping"}


class FailingApplyController(FakeController):
    def apply_config(self, config: DesktopAppConfig) -> None:
        raise ValueError("Could not resolve sender '@missing'.")


class FakeSlotCaptureService:
    def __init__(self, returned_path: Path | None = None, error: Exception | None = None) -> None:
        self.returned_path = returned_path
        self.error = error
        self.calls = []
        self.capture_to_path_calls = []

    def capture_slot(self, slot, existing_path: Path | None = None):
        self.calls.append((slot, existing_path))
        if self.error is not None:
            raise self.error
        return self.returned_path

    def capture_to_path(self, relative_path: Path, *, existing_path: Path | None = None):
        self.capture_to_path_calls.append((relative_path, existing_path))
        if self.error is not None:
            raise self.error
        return self.returned_path


def _write_solid_image(path: Path, color: str) -> None:
    image = QImage(120, 72, QImage.Format.Format_ARGB32)
    image.fill(QColor(color))
    assert image.save(str(path))


def _label_center_hex(label: QLabel) -> str:
    pixmap = label.pixmap()
    assert pixmap is not None
    image = pixmap.toImage()
    return image.pixelColor(image.width() // 2, image.height() // 2).name()


class OverwritingSlotCaptureService(FakeSlotCaptureService):
    def __init__(self, target_path: Path, colors: list[str]) -> None:
        super().__init__(returned_path=target_path)
        self.target_path = target_path
        self.colors = list(colors)
        self._last_color = colors[-1] if colors else "#ffffff"

    def _write_next(self) -> Path:
        if self.colors:
            self._last_color = self.colors.pop(0)
        _write_solid_image(self.target_path, self._last_color)
        return self.target_path

    def capture_slot(self, slot, existing_path: Path | None = None):
        self.calls.append((slot, existing_path))
        return self._write_next()

    def capture_to_path(self, relative_path: Path, *, existing_path: Path | None = None):
        self.capture_to_path_calls.append((relative_path, existing_path))
        return self._write_next()


def build_window(controller: FakeController, storage: FakeStorage, **overrides):
    values = {
        "controller": controller,
        "storage": storage,
        "tray_controller_factory": lambda *args, **kwargs: None,
        "available_profiles_loader": lambda: ["Default", "Profile 3", "Profile 9"],
        "available_chats_loader": lambda: [AccessibleChat(chat_id=-1001, title="Raid Group")],
        "session_status_loader": lambda: "authorized",
        "sender_candidate_picker": lambda candidates: [candidate.label for candidate in candidates],
    }
    values.update(overrides)
    return MainWindow(**values)


class FakeAction:
    def __init__(self, text: str, callback=None) -> None:
        self._text = text
        self.callback = callback
        self._enabled = True

    def text(self) -> str:
        return self._text

    def setText(self, text: str) -> None:
        self._text = text

    def setEnabled(self, enabled: bool) -> None:
        self._enabled = enabled

    def isEnabled(self) -> bool:
        return self._enabled

    def trigger(self) -> None:
        if self.callback is not None and self._enabled:
            self.callback()


class FakeMenu:
    def __init__(self) -> None:
        self.actions = []

    def addAction(self, text: str, callback=None):
        action = FakeAction(text, callback)
        self.actions.append(action)
        return action


class FakeTrayIconSignal:
    def __init__(self) -> None:
        self._callbacks = []

    def connect(self, callback) -> None:
        self._callbacks.append(callback)

    def emit(self, value) -> None:
        for callback in self._callbacks:
            callback(value)


class FakeTrayIcon:
    def __init__(self, _icon=None, _parent=None) -> None:
        self.activated = FakeTrayIconSignal()
        self.context_menu = None
        self.tooltip = None
        self.visible = False

    def setContextMenu(self, menu) -> None:
        self.context_menu = menu

    def setToolTip(self, value: str) -> None:
        self.tooltip = value

    def show(self) -> None:
        self.visible = True

    def hide(self) -> None:
        self.visible = False


def test_main_window_initializes_from_persisted_state_and_updates_from_signals(qtbot) -> None:
    base_time = datetime.now().replace(second=0, microsecond=0)
    storage = FakeStorage(
        state=DesktopAppState(
            bot_state=BotRuntimeState.stopped,
            connection_state=TelegramConnectionState.disconnected,
            raids_detected=6,
            raids_opened=4,
            raids_completed=3,
            raids_failed=1,
            duplicates_skipped=2,
            non_matching_skipped=3,
            open_failures=1,
            sender_rejected=5,
            browser_session_failed=6,
            page_ready=7,
            executor_not_configured=8,
            executor_succeeded=9,
            executor_failed=10,
            session_closed=11,
            last_successful_raid_open_at="2026-03-26T10:00:00",
            activity=[
                ActivityEntry(
                    timestamp=base_time - timedelta(hours=4),
                    action="browser_session_opened",
                    url="https://x.com/i/status/100",
                    reason="opened",
                ),
                ActivityEntry(
                    timestamp=base_time - timedelta(hours=3, minutes=58),
                    action="executor_succeeded",
                    url="https://x.com/i/status/100",
                    reason="done",
                ),
                ActivityEntry(
                    timestamp=base_time - timedelta(hours=2),
                    action="browser_session_opened",
                    url="https://x.com/i/status/101",
                    reason="opened",
                ),
                ActivityEntry(
                    timestamp=base_time - timedelta(hours=1, minutes=55),
                    action="executor_succeeded",
                    url="https://x.com/i/status/101",
                    reason="done",
                ),
                ActivityEntry(
                    timestamp=base_time - timedelta(hours=1),
                    action="browser_session_opened",
                    url="https://x.com/i/status/102",
                    reason="opened",
                ),
                ActivityEntry(
                    timestamp=base_time - timedelta(minutes=59),
                    action="executor_failed",
                    url="https://x.com/i/status/102",
                    reason="timeout",
                ),
                ActivityEntry(
                    timestamp=base_time - timedelta(minutes=20),
                    action="sender_rejected",
                    url="https://x.com/i/status/200",
                    reason="sender 42 not allowed",
                ),
                ActivityEntry(
                    timestamp=base_time - timedelta(minutes=10),
                    action="chat_rejected",
                    url="https://x.com/i/status/201",
                    reason="chat not allowed",
                ),
                ActivityEntry(
                    timestamp=base_time - timedelta(minutes=7),
                    action="not_a_raid",
                    url="https://x.com/i/status/201b",
                    reason="not_a_raid",
                ),
                ActivityEntry(
                    timestamp=base_time - timedelta(minutes=5),
                    action="page_ready",
                    url="https://x.com/i/status/202",
                    reason="page ready",
                ),
            ],
            successful_profile_runs=[
                SuccessfulProfileRun(
                    timestamp=base_time - timedelta(hours=3, minutes=58),
                    duration_seconds=120.0,
                ),
                SuccessfulProfileRun(
                    timestamp=base_time - timedelta(hours=1, minutes=55),
                    duration_seconds=300.0,
                ),
            ],
            last_error="boom",
        )
    )
    controller = FakeController()
    window = build_window(controller, storage)
    qtbot.addWidget(window)

    assert window.bot_state_label.text() == "Stopped"
    assert window.connection_state_label.text() == "Disconnected"
    assert window.avg_raid_completion_time_label.text() == "210s"
    assert window.average_raids_per_hour_label.text() == "1.0/hr"
    assert window.raids_completed_label.text() == "3"
    assert window.raids_failed_label.text() == "1"
    assert window.sidebar_success_rate_label.text() == "75.0%"
    assert window.sidebar_uptime_label.text() == "—"
    assert window.last_error_label.text() == "boom"
    assert window.activity_list.count() == 7
    assert "Page Ready" in window.activity_list.item(0).text()
    assert not any(
        "chat_rejected" in window.activity_list.item(index).text()
        for index in range(window.activity_list.count())
    )
    assert not any(
        "not_a_raid" in window.activity_list.item(index).text()
        for index in range(window.activity_list.count())
    )
    first_activity_widget = window.activity_list.itemWidget(window.activity_list.item(0))
    assert first_activity_widget.property("activityTone") == "accent"
    first_badge = first_activity_widget.findChild(ActivityBadge, "activityBadge")
    assert first_badge is not None
    first_reason_label = first_activity_widget.findChild(QLabel, "activityReason")
    assert first_reason_label is not None
    assert first_reason_label.isHidden() is True

    updated_activity = []
    updated_successful_profile_runs = []
    for index in range(24):
        opened_at = base_time - timedelta(hours=23) + timedelta(minutes=index * 5)
        url = f"https://x.com/i/status/{300 + index}"
        updated_activity.extend(
            [
                ActivityEntry(
                    timestamp=opened_at,
                    action="browser_session_opened",
                    url=url,
                    reason="opened",
                ),
                ActivityEntry(
                    timestamp=opened_at + timedelta(minutes=1),
                    action="executor_succeeded",
                    url=url,
                    reason="done",
                ),
            ]
        )
        updated_successful_profile_runs.append(
            SuccessfulProfileRun(
                timestamp=opened_at + timedelta(minutes=1),
                duration_seconds=60.0,
            )
        )
    updated_activity.append(
        ActivityEntry(
            timestamp=base_time - timedelta(minutes=2),
            action="page_ready",
            url="https://x.com/i/status/999",
            reason="page ready",
        )
    )
    updated_state = DesktopAppState(
        bot_state=BotRuntimeState.running,
        connection_state=TelegramConnectionState.connected,
        raids_detected=7,
        raids_opened=5,
        raids_completed=24,
        raids_failed=0,
        duplicates_skipped=2,
        non_matching_skipped=3,
        open_failures=1,
        sender_rejected=12,
        browser_session_failed=13,
        page_ready=14,
        executor_not_configured=15,
        executor_succeeded=16,
        executor_failed=17,
        session_closed=18,
        last_successful_raid_open_at="2026-03-26T10:10:00",
        activity=updated_activity,
        successful_profile_runs=updated_successful_profile_runs,
        last_error="new-error",
    )
    try:
        controller.botStateChanged.emit("running")
        controller.connectionStateChanged.emit("connected")
        controller.statsChanged.emit(updated_state)
        controller.activityAdded.emit(
            ActivityEntry(
                timestamp=datetime(2026, 3, 26, 10, 10, 0),
                action="executor_failed",
                url="https://x.com/i/status/200",
                reason="executor crashed",
            )
        )
        controller.activityAdded.emit(
            ActivityEntry(
                timestamp=datetime(2026, 3, 26, 10, 11, 0),
                action="duplicate",
                url="https://x.com/i/status/201",
                reason="duplicate",
            )
        )
        controller.errorRaised.emit("new-error")

        assert window.bot_state_label.text() == "Running"
        assert window.connection_state_label.text() == "Connected"
        assert window.avg_raid_completion_time_label.text() == "60s"
        assert window.average_raids_per_hour_label.text() == "8.0/hr"
        assert window.raids_completed_label.text() == "24"
        assert window.raids_failed_label.text() == "0"
        assert window.sidebar_success_rate_label.text() == "100.0%"
        assert window.sidebar_uptime_label.text().endswith("m")
        assert window.last_successful_label.text() == "Mar 26, 10:10"
        assert window.last_error_label.text() == "new-error"
        assert "Executor Failed" in window.activity_list.item(0).text()
        assert "Page Ready" in window.activity_list.item(1).text()
    finally:
        controller.botStateChanged.emit("stopped")


def test_main_window_per_profile_counter_cards_render_completed_failed_and_success_rate(
    qtbot,
) -> None:
    state = DesktopAppState(
        raids_completed=3,
        raids_failed=1,
    )
    window = build_window(FakeController(), FakeStorage(state=state))
    qtbot.addWidget(window)

    assert window.raids_completed_label.text() == "3"
    assert window.raids_failed_label.text() == "1"
    assert window.sidebar_success_rate_label.text() == "75.0%"


def test_main_window_dashboard_exposes_metric_cards_and_panels(qtbot) -> None:
    from raidbot.desktop.theme import SECTION_OBJECT_NAME

    window = build_window(FakeController(), FakeStorage())
    qtbot.addWidget(window)

    tab_texts = [
        button.text()
        for button in window.findChildren(QPushButton, "shellTabButton")
    ]

    assert window.findChild(QWidget, "sidebar") is None
    assert tab_texts == ["Dashboard", "Settings", "Bot Actions"]
    assert window.findChild(QWidget, "commandStatusRow") is None
    assert window.status_panel.objectName() == "statusPanel"
    status_summary_column = window.status_panel.findChild(QWidget, "statusSummaryColumn")
    status_header_row = window.status_panel.findChild(QWidget, "statusHeaderRow")
    status_header_buttons = window.status_panel.findChild(QWidget, "statusHeaderButtons")
    assert status_summary_column is not None
    assert status_header_row is not None
    assert window.status_panel.findChild(QWidget, "statusHeaderInline") is None
    assert status_header_buttons is not None
    assert status_header_buttons.parentWidget() is status_header_row
    assert window.start_button.parentWidget() is status_header_buttons
    assert window.stop_button.parentWidget() is status_header_buttons
    status_summary_card = window.status_panel.findChild(QWidget, "statusSummaryCard")
    assert status_summary_card is not None
    assert len(status_summary_card.findChildren(QLabel, "statusDot")) == 2
    first_status_row = status_summary_card.findChildren(QWidget, "statusSummaryRow")[0]
    first_status_row_layout = first_status_row.layout()
    assert first_status_row_layout is not None
    assert first_status_row_layout.itemAt(2).widget() is window.bot_state_label
    assert first_status_row_layout.itemAt(3).widget() is window._bot_dot
    assert len(window.metric_cards) == 6
    assert [label.text() for label in window.metric_title_labels] == [
        "AVG RAID COMPLETION TIME",
        "AVG RAIDS PER HOUR",
        "Raids Completed",
        "Raids Failed",
        "Success Rate",
        "Uptime",
    ]
    assert window.activity_panel.objectName() == "activityPanel"
    assert window.error_panel.objectName() == "errorPanel"
    assert window.status_panel.findChild(type(window.status_panel), SECTION_OBJECT_NAME) is not None
    assert window.activity_panel.findChild(type(window.status_panel), SECTION_OBJECT_NAME) is not None
    assert window.error_panel.findChild(type(window.status_panel), SECTION_OBJECT_NAME) is not None
    assert window.status_panel.findChild(QLabel, "raidActivitySubtitle").text() == (
        "Last 24 Hours | Smoothed Rate"
    )


def test_main_window_metric_cards_expose_reset_buttons(qtbot) -> None:
    window = build_window(FakeController(), FakeStorage())
    qtbot.addWidget(window)

    reset_buttons = window.findChildren(QPushButton, "metricResetButton")

    assert len(reset_buttons) == 6
    assert all(button.text() == "R" for button in reset_buttons)
    assert all(button.height() == 12 for button in reset_buttons)
    assert all(button.width() == 12 for button in reset_buttons)
    assert set(window.metric_reset_buttons) == {
        "avg_raid_completion_time",
        "avg_raids_per_hour",
        "raids_completed",
        "raids_failed",
        "success_rate",
        "uptime",
    }


def test_main_window_metric_reset_button_resets_only_its_own_metric(qtbot) -> None:
    controller = FakeController()
    window = build_window(controller, FakeStorage())
    qtbot.addWidget(window)

    qtbot.mouseClick(
        window.metric_reset_buttons["raids_completed"],
        Qt.MouseButton.LeftButton,
    )

    assert controller.dashboard_metric_reset_requests == ["raids_completed"]


def test_main_window_status_panel_header_contains_action_buttons(qtbot) -> None:
    window = build_window(FakeController(), FakeStorage())
    qtbot.addWidget(window)

    status_summary_column = window.status_panel.findChild(QWidget, "statusSummaryColumn")
    status_header_row = window.status_panel.findChild(QWidget, "statusHeaderRow")
    status_header_buttons = window.status_panel.findChild(QWidget, "statusHeaderButtons")

    assert status_summary_column is not None
    assert status_header_row is not None
    assert window.status_panel.findChild(QWidget, "statusHeaderInline") is None
    assert status_header_buttons is not None
    assert status_header_buttons.parentWidget() is status_header_row
    assert window.start_button.parentWidget() is status_header_buttons
    assert window.stop_button.parentWidget() is status_header_buttons
    header_layout = status_header_row.layout()
    assert header_layout is not None
    assert header_layout.itemAt(2).widget() is status_header_buttons


def test_main_window_formats_zero_dashboard_metrics_without_em_dash(qtbot) -> None:
    window = build_window(FakeController(), FakeStorage())
    qtbot.addWidget(window)

    assert window._format_average_completion_time([]) == "0s"
    assert window._format_raids_per_hour(0) == "0.0/hr"
    assert window._format_success_rate(0, 0) == "0%"


def test_main_window_formats_last_successful_raid_human_readable(qtbot) -> None:
    window = build_window(FakeController(), FakeStorage())
    qtbot.addWidget(window)
    now = datetime(2026, 3, 31, 18, 42, 0)

    assert (
        window._format_last_successful_raid("2026-03-31T18:42:00", now=now)
        == "Today, 18:42"
    )
    assert (
        window._format_last_successful_raid("2026-03-30T18:42:00", now=now)
        == "Yesterday, 18:42"
    )
    assert (
        window._format_last_successful_raid("2026-03-29T18:42:00", now=now)
        == "Mar 29, 18:42"
    )
    assert (
        window._format_last_successful_raid("2025-03-29T18:42:00", now=now)
        == "Mar 29, 2025, 18:42"
    )
    assert window._format_last_successful_raid("", now=now) == "No successful raid yet"
    assert (
        window._format_last_successful_raid("not-a-timestamp", now=now)
        == "not-a-timestamp"
    )


def test_main_window_builds_hourly_completed_raid_buckets_from_recent_activity(
    qtbot, monkeypatch
) -> None:
    monkeypatch.setenv("RAIDBOT_CHART_MODE", "cumulative")
    window = build_window(FakeController(), FakeStorage())
    qtbot.addWidget(window)
    base_time = datetime.now().replace(minute=0, second=0, microsecond=0)

    series = window._build_recent_raid_activity_series(
        [
            ActivityEntry(
                timestamp=base_time - timedelta(hours=4),
                action="automation_succeeded",
                url="https://x.com/i/status/100",
                reason="automation_succeeded",
                profile_directory="Default",
            ),
            ActivityEntry(
                timestamp=base_time - timedelta(hours=1),
                action="automation_succeeded",
                url="https://x.com/i/status/100",
                reason="automation_succeeded",
                profile_directory="Profile 3",
            ),
            ActivityEntry(
                timestamp=base_time - timedelta(hours=1, minutes=10),
                action="automation_succeeded",
                url="https://x.com/i/status/100",
                reason="automation_succeeded",
                profile_directory="Profile 9",
            ),
        ]
    )

    assert len(series) == 24
    assert series[-1] == 3
    assert max(series) == 3
    assert any(value == 0 for value in series[:18])
    assert any(value == 1 for value in series[18:21])
    assert any(value == 3 for value in series[21:])


def test_main_window_builds_monotonic_cumulative_raid_series(
    qtbot, monkeypatch
) -> None:
    monkeypatch.setenv("RAIDBOT_CHART_MODE", "cumulative")
    window = build_window(FakeController(), FakeStorage())
    qtbot.addWidget(window)
    base_time = datetime.now().replace(minute=0, second=0, microsecond=0)

    series = window._build_recent_raid_activity_series(
        [
            ActivityEntry(
                timestamp=base_time - timedelta(hours=2),
                action="automation_succeeded",
                url="https://x.com/i/status/100",
                reason="automation_succeeded",
                profile_directory="Default",
            ),
            ActivityEntry(
                timestamp=base_time - timedelta(hours=1),
                action="automation_succeeded",
                url="https://x.com/i/status/101",
                reason="automation_succeeded",
                profile_directory="Profile 3",
            ),
            ActivityEntry(
                timestamp=base_time - timedelta(minutes=15),
                action="automation_succeeded",
                url="https://x.com/i/status/102",
                reason="automation_succeeded",
                profile_directory="Profile 9",
            ),
        ]
    )

    assert series == sorted(series)
    assert series[-1] == 3


def test_main_window_supports_rolling_60m_raid_activity_preview_mode(
    qtbot, monkeypatch
) -> None:
    monkeypatch.setenv("RAIDBOT_CHART_MODE", "smoothed_rate")
    window = build_window(FakeController(), FakeStorage())
    qtbot.addWidget(window)
    base_time = datetime.now().replace(minute=0, second=0, microsecond=0)

    series = window._build_recent_raid_activity_series(
        [
            ActivityEntry(
                timestamp=base_time - timedelta(hours=2),
                action="automation_succeeded",
                url="https://x.com/i/status/200",
                reason="automation_succeeded",
                profile_directory="Default",
            ),
            ActivityEntry(
                timestamp=base_time - timedelta(hours=1),
                action="automation_succeeded",
                url="https://x.com/i/status/201",
                reason="automation_succeeded",
                profile_directory="Profile 3",
            ),
            ActivityEntry(
                timestamp=base_time - timedelta(hours=1, minutes=10),
                action="automation_succeeded",
                url="https://x.com/i/status/202",
                reason="automation_succeeded",
                profile_directory="Profile 9",
            ),
        ]
    )

    assert window.status_panel.findChild(QLabel, "raidActivitySubtitle").text() == (
        "Last 24 Hours | Smoothed Rate"
    )
    assert len(series) == 24
    assert sum(series) > 0
    assert max(series) > 0
    assert any(value > 0 for value in series[-4:])


def test_raid_activity_chart_accepts_dense_preview_series(qtbot) -> None:
    chart = RaidActivityChart()
    qtbot.addWidget(chart)

    chart.set_series(list(range(289)))

    assert len(chart._series) == 289
    assert chart._series[-1] == 288


def test_raid_activity_chart_builds_qtcharts_series(qtbot) -> None:
    from PySide6.QtCharts import QAreaSeries, QChart, QSplineSeries

    chart = RaidActivityChart()
    qtbot.addWidget(chart)

    chart.set_series([0, 3, 5, 2])

    assert isinstance(chart.chart(), QChart)
    assert isinstance(chart._upper_series, QSplineSeries)
    assert chart._upper_series.count() == 4
    assert any(isinstance(series, QAreaSeries) for series in chart.chart().series())


def test_raid_activity_chart_uses_plain_line_series_for_cumulative_mode(qtbot) -> None:
    from PySide6.QtCharts import QLineSeries, QSplineSeries

    chart = RaidActivityChart()
    qtbot.addWidget(chart)

    chart.set_mode("cumulative")
    chart.set_series([0, 3, 5, 20])

    assert isinstance(chart._upper_series, QLineSeries)
    assert not isinstance(chart._upper_series, QSplineSeries)
    assert chart._upper_series.count() == 4


def test_build_chart_area_path_uses_winding_fill() -> None:
    from PySide6.QtCore import QPointF
    from PySide6.QtCore import Qt as QtCoreQt

    from raidbot.desktop.main_window import _build_chart_area_path

    path = _build_chart_area_path(
        [QPointF(0.0, 10.0), QPointF(20.0, 5.0), QPointF(40.0, 15.0)],
        baseline_y=20.0,
    )

    assert path.fillRule() == QtCoreQt.FillRule.WindingFill


def test_build_chart_fill_band_path_stays_within_area() -> None:
    from PySide6.QtCore import QPointF

    from raidbot.desktop.main_window import (
        _build_chart_area_path,
        _build_chart_fill_band_path,
        _build_eased_cumulative_path,
    )

    points = [QPointF(0.0, 10.0), QPointF(20.0, 5.0), QPointF(40.0, 15.0)]
    line_path = _build_eased_cumulative_path(points)
    area_path = _build_chart_area_path(points, baseline_y=20.0)
    fill_band = _build_chart_fill_band_path(line_path, area_path, band_width=12.0)

    assert not fill_band.isEmpty()
    assert area_path.boundingRect().contains(fill_band.boundingRect())


def test_render_line_relative_fill_image_uses_line_relative_depth() -> None:
    from PySide6.QtCore import QPointF, QSize
    from PySide6.QtGui import QColor

    from raidbot.desktop.main_window import _render_line_relative_fill_image

    sampled_points = [
        QPointF(0.0, 18.0),
        QPointF(5.0, 18.0),
        QPointF(10.0, 10.0),
    ]

    image = _render_line_relative_fill_image(
        QSize(12, 22),
        sampled_points,
        baseline_y=20.0,
        color=QColor(45, 212, 191),
    )

    shallow_fill = image.pixelColor(2, 19)
    deeper_fill = image.pixelColor(9, 16)

    assert shallow_fill.alpha() > 0
    assert deeper_fill.alpha() > 0
    assert abs(shallow_fill.alpha() - deeper_fill.alpha()) <= 12
    assert image.pixelColor(9, 10).alpha() == 0


def test_render_line_relative_fill_image_can_limit_fill_mass_to_fixed_depth() -> None:
    from PySide6.QtCore import QPointF, QSize
    from PySide6.QtGui import QColor

    from raidbot.desktop.main_window import _render_line_relative_fill_image

    sampled_points = [
        QPointF(0.0, 6.0),
        QPointF(10.0, 6.0),
        QPointF(20.0, 16.0),
    ]

    image = _render_line_relative_fill_image(
        QSize(24, 32),
        sampled_points,
        baseline_y=28.0,
        color=QColor(45, 212, 191),
        alpha=0,
        band_alpha=48,
        band_height=10.0,
    )

    deep_column_alpha = sum(image.pixelColor(4, y).alpha() for y in range(32))
    shallow_column_alpha = sum(image.pixelColor(18, y).alpha() for y in range(32))

    assert deep_column_alpha > 0
    assert shallow_column_alpha > 0
    assert abs(deep_column_alpha - shallow_column_alpha) <= 24


def test_render_line_band_fill_image_keeps_deep_area_transparent() -> None:
    from PySide6.QtCore import QPointF, QSize
    from PySide6.QtGui import QColor

    from raidbot.desktop.main_window import _render_line_band_fill_image

    sampled_points = [
        QPointF(0.0, 6.0),
        QPointF(10.0, 6.0),
        QPointF(20.0, 16.0),
    ]

    image = _render_line_band_fill_image(
        QSize(24, 32),
        sampled_points,
        baseline_y=28.0,
        color=QColor(45, 212, 191),
        band_width=12.0,
        alpha=28,
    )

    assert image.pixelColor(4, 8).alpha() > 0
    assert image.pixelColor(4, 24).alpha() == 0
    assert image.pixelColor(18, 18).alpha() > 0
    assert image.pixelColor(18, 26).alpha() == 0


def test_render_line_shadow_image_fades_with_depth() -> None:
    from PySide6.QtCore import QPointF, QSize
    from PySide6.QtGui import QColor

    from raidbot.desktop.main_window import _render_line_shadow_image

    sampled_points = [
        QPointF(0.0, 6.0),
        QPointF(10.0, 6.0),
        QPointF(20.0, 16.0),
    ]

    image = _render_line_shadow_image(
        QSize(24, 32),
        sampled_points,
        baseline_y=28.0,
        color=QColor(45, 212, 191),
    )

    near_shadow = image.pixelColor(4, 8).alpha()
    mid_shadow = image.pixelColor(4, 12).alpha()
    deep_shadow = image.pixelColor(4, 24).alpha()

    assert near_shadow > 0
    assert mid_shadow > 0
    assert near_shadow > mid_shadow
    assert deep_shadow == 0


def test_render_line_glow_image_keeps_deep_area_transparent() -> None:
    from PySide6.QtCore import QPointF, QSize
    from PySide6.QtGui import QColor

    from raidbot.desktop.main_window import _render_line_glow_image

    sampled_points = [
        QPointF(0.0, 6.0),
        QPointF(10.0, 6.0),
        QPointF(20.0, 16.0),
    ]

    image = _render_line_glow_image(
        QSize(24, 32),
        sampled_points,
        color=QColor(45, 212, 191),
    )

    assert image.pixelColor(4, 6).alpha() > 0
    assert image.pixelColor(4, 14).alpha() == 0
    assert image.pixelColor(18, 16).alpha() > 0
    assert image.pixelColor(18, 24).alpha() == 0


def test_main_window_smoothed_rate_preview_mode_softens_bursts(
    qtbot, monkeypatch
) -> None:
    monkeypatch.setenv("RAIDBOT_CHART_MODE", "smoothed_rate")
    window = build_window(FakeController(), FakeStorage())
    qtbot.addWidget(window)
    now = datetime.now().replace(minute=0, second=0, microsecond=0)
    entries = [
        ActivityEntry(
            timestamp=now - timedelta(minutes=minute_offset),
            action="automation_succeeded",
            url=f"https://x.com/i/status/{1000 + index}",
            reason="automation_succeeded",
            profile_directory=f"Profile {index}",
        )
        for index, minute_offset in enumerate((10, 12, 14, 16, 18, 20, 22, 24))
    ]

    series = window._build_recent_raid_activity_series(entries)

    assert len(series) == 24
    peak_index = series.index(max(series))
    assert max(series) < 8
    assert series[peak_index] > 0
    assert peak_index > 0
    assert series[peak_index - 1] > 0


def test_raid_activity_chart_accepts_sparse_cumulative_series(qtbot) -> None:
    chart = RaidActivityChart()
    qtbot.addWidget(chart)

    chart.set_series([0] * 20 + [1, 5, 18, 19])

    assert chart._series[-4:] == [1, 5, 18, 19]


def test_build_eased_cumulative_path_handles_steep_growth_without_reversing() -> None:
    from PySide6.QtCore import QPointF

    from raidbot.desktop.main_window import _build_eased_cumulative_path

    points = [
        QPointF(float(index), float(value))
        for index, value in enumerate([0] * 20 + [1, 5, 18, 19])
    ]

    path = _build_eased_cumulative_path(points)

    assert path.elementCount() > len(points)
    previous_x = None
    previous_y = None
    for step in range(201):
        point = path.pointAtPercent(step / 200)
        if previous_x is not None:
            assert point.x() >= previous_x
            assert point.y() >= previous_y
        previous_x = point.x()
        previous_y = point.y()


def test_main_window_uses_current_automation_activity_for_dashboard_metrics(qtbot) -> None:
    base_time = datetime.now().replace(second=0, microsecond=0)
    state = DesktopAppState(
        raids_completed=14,
        raids_failed=1,
        activity=[
            ActivityEntry(
                timestamp=base_time - timedelta(minutes=20),
                action="automation_started",
                url="https://x.com/i/status/500",
                reason="automation_started",
                profile_directory="Default",
            ),
            ActivityEntry(
                timestamp=base_time - timedelta(minutes=19, seconds=57),
                action="automation_succeeded",
                url="https://x.com/i/status/500",
                reason="automation_succeeded",
                profile_directory="Default",
            ),
            ActivityEntry(
                timestamp=base_time - timedelta(minutes=19),
                action="automation_started",
                url="https://x.com/i/status/500",
                reason="automation_started",
                profile_directory="Profile 3",
            ),
            ActivityEntry(
                timestamp=base_time - timedelta(minutes=18, seconds=57),
                action="automation_succeeded",
                url="https://x.com/i/status/500",
                reason="automation_succeeded",
                profile_directory="Profile 3",
            ),
            ActivityEntry(
                timestamp=base_time - timedelta(minutes=18),
                action="automation_started",
                url="https://x.com/i/status/500",
                reason="automation_started",
                profile_directory="Profile 9",
            ),
            ActivityEntry(
                timestamp=base_time - timedelta(minutes=17, seconds=57),
                action="automation_succeeded",
                url="https://x.com/i/status/500",
                reason="automation_succeeded",
                profile_directory="Profile 9",
            ),
            ActivityEntry(
                timestamp=base_time - timedelta(minutes=17),
                action="automation_started",
                url="https://x.com/i/status/500",
                reason="automation_started",
                profile_directory="Profile 10",
            ),
            ActivityEntry(
                timestamp=base_time - timedelta(minutes=16, seconds=57),
                action="automation_succeeded",
                url="https://x.com/i/status/500",
                reason="automation_succeeded",
                profile_directory="Profile 10",
            ),
        ],
        successful_profile_runs=[
            SuccessfulProfileRun(
                timestamp=base_time - timedelta(minutes=19, seconds=57),
                duration_seconds=3.0,
            ),
            SuccessfulProfileRun(
                timestamp=base_time - timedelta(minutes=18, seconds=57),
                duration_seconds=3.0,
            ),
            SuccessfulProfileRun(
                timestamp=base_time - timedelta(minutes=17, seconds=57),
                duration_seconds=3.0,
            ),
            SuccessfulProfileRun(
                timestamp=base_time - timedelta(minutes=16, seconds=57),
                duration_seconds=3.0,
            ),
        ],
    )
    window = build_window(FakeController(), FakeStorage(state=state))
    qtbot.addWidget(window)

    assert window.sidebar_success_rate_label.text() == "93.3%"
    assert window.avg_raid_completion_time_label.text() == "3s"
    assert window.average_raids_per_hour_label.text() == "4.0/hr"


def test_main_window_dashboard_metrics_respect_reset_baselines(qtbot) -> None:
    current_time = datetime.now().replace(second=0, microsecond=0)
    state = DesktopAppState(
        raids_completed=14,
        raids_failed=3,
        activity=[
            ActivityEntry(
                timestamp=current_time - timedelta(minutes=20),
                action="automation_started",
                url="https://x.com/i/status/500",
                reason="automation_started",
                profile_directory="Default",
            ),
            ActivityEntry(
                timestamp=current_time - timedelta(minutes=19, seconds=51),
                action="automation_succeeded",
                url="https://x.com/i/status/500",
                reason="automation_succeeded",
                profile_directory="Default",
            ),
            ActivityEntry(
                timestamp=current_time - timedelta(minutes=9),
                action="automation_started",
                url="https://x.com/i/status/500",
                reason="automation_started",
                profile_directory="Profile 3",
            ),
            ActivityEntry(
                timestamp=current_time - timedelta(minutes=8, seconds=57),
                action="automation_succeeded",
                url="https://x.com/i/status/500",
                reason="automation_succeeded",
                profile_directory="Profile 3",
            ),
            ActivityEntry(
                timestamp=current_time - timedelta(minutes=7),
                action="automation_started",
                url="https://x.com/i/status/500",
                reason="automation_started",
                profile_directory="Profile 9",
            ),
            ActivityEntry(
                timestamp=current_time - timedelta(minutes=6, seconds=55),
                action="automation_succeeded",
                url="https://x.com/i/status/500",
                reason="automation_succeeded",
                profile_directory="Profile 9",
            ),
        ],
        successful_profile_runs=[
            SuccessfulProfileRun(
                timestamp=current_time - timedelta(minutes=19, seconds=51),
                duration_seconds=9.0,
            ),
            SuccessfulProfileRun(
                timestamp=current_time - timedelta(minutes=8, seconds=57),
                duration_seconds=3.0,
            ),
            SuccessfulProfileRun(
                timestamp=current_time - timedelta(minutes=6, seconds=55),
                duration_seconds=5.0,
            ),
        ],
        dashboard_metric_resets=DashboardMetricResetState(
            avg_completion_reset_at=current_time - timedelta(minutes=10),
            avg_raids_per_hour_reset_at=current_time - timedelta(minutes=10),
            raids_completed_offset=10,
            raids_failed_offset=1,
            success_rate_completed_offset=12,
            success_rate_failed_offset=1,
            uptime_reset_at=current_time - timedelta(minutes=5),
        ),
    )
    window = build_window(FakeController(), FakeStorage(state=state))
    qtbot.addWidget(window)

    assert window.raids_completed_label.text() == "4"
    assert window.raids_failed_label.text() == "2"
    assert window.sidebar_success_rate_label.text() == "50.0%"
    assert window.avg_raid_completion_time_label.text() == "4s"
    assert window.average_raids_per_hour_label.text() == "2.0/hr"
    assert window.sidebar_uptime_label.text() == "5m"


def test_main_window_average_raids_per_hour_uses_success_history_active_hours(
    qtbot,
) -> None:
    current_time = datetime.now().replace(minute=0, second=0, microsecond=0)
    state = DesktopAppState(
        successful_profile_runs=[
            SuccessfulProfileRun(
                timestamp=current_time - timedelta(minutes=50),
                duration_seconds=3.0,
            ),
            SuccessfulProfileRun(
                timestamp=current_time - timedelta(minutes=40),
                duration_seconds=4.0,
            ),
            SuccessfulProfileRun(
                timestamp=current_time - timedelta(hours=1, minutes=30),
                duration_seconds=3.0,
            ),
            SuccessfulProfileRun(
                timestamp=current_time - timedelta(hours=1, minutes=20),
                duration_seconds=5.0,
            ),
        ],
    )
    window = build_window(FakeController(), FakeStorage(state=state))
    qtbot.addWidget(window)

    assert window.average_raids_per_hour_label.text() == "2.0/hr"


def test_main_window_ignores_future_successful_runs_for_dashboard_metrics(qtbot) -> None:
    future_time = datetime.now() + timedelta(hours=2)
    state = DesktopAppState(
        activity=[
            ActivityEntry(
                timestamp=future_time - timedelta(seconds=3),
                action="automation_started",
                url="https://x.com/i/status/700",
                reason="automation_started",
                profile_directory="Default",
            ),
            ActivityEntry(
                timestamp=future_time,
                action="automation_succeeded",
                url="https://x.com/i/status/700",
                reason="automation_succeeded",
                profile_directory="Default",
            ),
        ]
    )
    window = build_window(FakeController(), FakeStorage(state=state))
    qtbot.addWidget(window)

    assert window.avg_raid_completion_time_label.text() == "0s"
    assert window.average_raids_per_hour_label.text() == "0.0/hr"
    assert max(window.raid_activity_chart._series) == 0


def test_main_window_uses_l8n_raid_bot_branding(qtbot) -> None:
    from raidbot.desktop.branding import APP_VERSION_BADGE

    window = build_window(FakeController(), FakeStorage())
    qtbot.addWidget(window)

    assert window.windowTitle() == "L8N Raid Bot"
    assert window.findChild(QLabel, "appName") is None
    assert window.top_tabs.findChild(QLabel, "shellSessionStamp").text() == APP_VERSION_BADGE


def test_main_window_top_tabs_switch_pages(qtbot) -> None:
    window = build_window(FakeController(), FakeStorage())
    qtbot.addWidget(window)

    top_tabs = window.findChildren(QPushButton, "shellTabButton")

    assert [button.text() for button in top_tabs] == [
        "Dashboard",
        "Settings",
        "Bot Actions",
    ]
    assert window.stack.currentIndex() == 0

    qtbot.mouseClick(top_tabs[1], Qt.MouseButton.LeftButton)
    assert window.stack.currentIndex() == 1

    qtbot.mouseClick(top_tabs[2], Qt.MouseButton.LeftButton)
    assert window.stack.currentIndex() == 2


def test_main_window_dashboard_uses_tighter_left_gutter(qtbot) -> None:
    window = build_window(FakeController(), FakeStorage())
    qtbot.addWidget(window)

    dashboard_scroll = window.stack.widget(0)
    assert isinstance(dashboard_scroll, QScrollArea)
    dashboard_page = dashboard_scroll.widget()
    assert dashboard_page is not None
    dashboard_layout = dashboard_page.layout()
    assert dashboard_layout is not None

    assert dashboard_layout.contentsMargins().left() == 12


def test_activity_feed_row_does_not_flash_reason_label_as_top_level_window(qtbot) -> None:
    app = QApplication.instance()
    assert app is not None

    flashed_labels: list[str] = []

    class ReasonProbe(QObject):
        def eventFilter(self, obj, event) -> bool:
            if (
                isinstance(obj, QLabel)
                and obj.objectName() == "activityReason"
                and obj.isWindow()
                and event.type() == QEvent.Type.Show
            ):
                flashed_labels.append(obj.text())
            return False

    probe = ReasonProbe()
    app.installEventFilter(probe)
    try:
        row = ActivityFeedRow(
            title="Automation Succeeded",
            tone="success",
            timestamp_text="11:32:39",
            url="https://x.com/i/status/1",
            reason_text="automation_succeeded",
        )
        qtbot.addWidget(row)
    finally:
        app.removeEventFilter(probe)

    assert flashed_labels == []


def test_activity_feed_row_reason_label_is_not_hard_limited(qtbot) -> None:
    row = ActivityFeedRow(
        title="Automation Failed",
        tone="error",
        timestamp_text="23:06:03",
        url="https://x.com/i/status/1",
        reason_text="window_not_focusable",
    )
    qtbot.addWidget(row)

    reason_label = row.findChild(QLabel, "activityReason")

    assert reason_label is not None
    assert reason_label.maximumWidth() >= 16777215
    assert reason_label.text() == "window_not_focusable"


def test_main_window_removed_generic_automation_controls_are_not_visible(qtbot) -> None:
    window = build_window(FakeController(), FakeStorage())
    qtbot.addWidget(window)

    assert window.findChild(QWidget, "sidebar") is None
    assert window.stack.count() == 3
    assert hasattr(window, "bot_actions_page")
    assert not hasattr(window, "automation_page")
    assert not hasattr(window.bot_actions_page, "sequence_list")
    assert not hasattr(window.bot_actions_page, "window_combo")
    assert not hasattr(window.bot_actions_page, "start_button")
    assert not hasattr(window.bot_actions_page, "dry_run_button")
    assert not hasattr(window.bot_actions_page, "resume_queue_button")
    assert not hasattr(window.bot_actions_page, "clear_queue_button")


def test_main_window_bot_actions_runtime_failure_keeps_simple_status(qtbot) -> None:
    window = build_window(FakeController(), FakeStorage())
    qtbot.addWidget(window)

    window.controller.errorRaised.emit("runtime boom")

    assert window.bot_actions_page.status_label.text() == (
        "Status: Idle\nLast error: runtime boom"
    )


def test_main_window_bot_actions_step_event_shows_and_clears_current_slot(qtbot) -> None:
    config = build_config(
        bot_action_slots=(
            replace(build_config().bot_action_slots[0], enabled=True),
            replace(build_config().bot_action_slots[1], enabled=True),
            replace(build_config().bot_action_slots[2], enabled=False),
            replace(build_config().bot_action_slots[3], enabled=False),
        )
    )
    window = build_window(FakeController(config=config), FakeStorage(config=config))
    qtbot.addWidget(window)

    window.controller.botActionRunEvent.emit(
        {"type": "automation_run_started", "sequence_id": "seq-1"}
    )
    window.controller.botActionRunEvent.emit(
        {"type": "step_search_started", "step_index": 1}
    )

    assert window.bot_actions_page.status_label.text() == (
        "Status: Running\nCurrent slot: Slot 2 (L)"
    )

    window.controller.botActionRunEvent.emit({"type": "automation_run_succeeded"})

    assert window.bot_actions_page.status_label.text() == "Status: Idle"


def test_main_window_bot_actions_failure_keeps_current_slot_when_step_index_is_available(qtbot) -> None:
    config = build_config(
        bot_action_slots=(
            replace(build_config().bot_action_slots[0], enabled=True),
            replace(build_config().bot_action_slots[1], enabled=True),
            replace(build_config().bot_action_slots[2], enabled=False),
            replace(build_config().bot_action_slots[3], enabled=False),
        )
    )
    window = build_window(FakeController(config=config), FakeStorage(config=config))
    qtbot.addWidget(window)

    window.controller.botActionRunEvent.emit(
        {"type": "automation_run_started", "sequence_id": "seq-1"}
    )
    window.controller.botActionRunEvent.emit(
        {"type": "step_failed", "step_index": 1, "reason": "click_failed"}
    )

    assert window.bot_actions_page.status_label.text() == (
        "Status: Idle\nCurrent slot: Slot 2 (L)\nLast error: click_failed"
    )


def test_main_window_bot_actions_failure_keeps_current_slot_across_followup_run_failed_event(
    qtbot,
) -> None:
    config = build_config(
        bot_action_slots=(
            replace(build_config().bot_action_slots[0], enabled=True),
            replace(build_config().bot_action_slots[1], enabled=True),
            replace(build_config().bot_action_slots[2], enabled=False),
            replace(build_config().bot_action_slots[3], enabled=False),
        )
    )
    window = build_window(FakeController(config=config), FakeStorage(config=config))
    qtbot.addWidget(window)

    window.controller.botActionRunEvent.emit(
        {"type": "automation_run_started", "sequence_id": "seq-1"}
    )
    window.controller.botActionRunEvent.emit(
        {"type": "step_failed", "step_index": 1, "reason": "ui_did_not_change"}
    )
    window.controller.botActionRunEvent.emit(
        {"type": "automation_run_failed", "reason": "ui_did_not_change"}
    )

    assert window.bot_actions_page.status_label.text() == (
        "Status: Idle\nCurrent slot: Slot 2 (L)\nLast error: ui_did_not_change"
    )


def test_main_window_current_slot_uses_enabled_slot_order(qtbot) -> None:
    config = build_config(
        bot_action_slots=(
            replace(build_config().bot_action_slots[0], enabled=False),
            replace(build_config().bot_action_slots[1], enabled=True),
            replace(build_config().bot_action_slots[2], enabled=False),
            replace(build_config().bot_action_slots[3], enabled=False),
        )
    )
    window = build_window(FakeController(config=config), FakeStorage(config=config))
    qtbot.addWidget(window)

    window.controller.botActionRunEvent.emit(
        {"type": "automation_run_started", "sequence_id": "seq-1"}
    )
    window.controller.botActionRunEvent.emit(
        {"type": "step_search_started", "step_index": 0}
    )

    assert window.bot_actions_page.status_label.text() == (
        "Status: Running\nCurrent slot: Slot 2 (L)"
    )


def test_main_window_worker_bot_action_step_event_updates_current_slot(qtbot) -> None:
    from raidbot.desktop.controller import DesktopController

    class WorkerBackedRunner:
        def __init__(self) -> None:
            self.running = False

        def start(self, job) -> None:
            self.running = True

        def submit(self, job):
            return None

        def is_running(self) -> bool:
            return self.running

        def wait_until_stopped(self, timeout: float | None = None) -> bool:
            self.running = False
            return True

    class WorkerBackedWorker:
        def __init__(self, *, emit_event, config, **_kwargs) -> None:
            self.emit_event = emit_event
            self.config = config

        async def run(self) -> None:
            return None

        async def stop(self) -> None:
            return None

        async def apply_config(self, config) -> None:
            self.config = config

        def resume_automation_queue(self) -> None:
            return None

        def clear_automation_queue(self) -> None:
            return None

        def notify_manual_automation_finished(self) -> None:
            return None

    config = build_config(
        bot_action_slots=(
            replace(build_config().bot_action_slots[0], enabled=False),
            replace(build_config().bot_action_slots[1], enabled=True),
            replace(build_config().bot_action_slots[2], enabled=False),
            replace(build_config().bot_action_slots[3], enabled=False),
        )
    )
    storage = FakeStorage(config=config)
    created = {}

    def worker_factory(**kwargs):
        worker = WorkerBackedWorker(**kwargs)
        created["worker"] = worker
        return worker

    controller = DesktopController(
        storage=storage,
        config=config,
        worker_factory=worker_factory,
        runner_factory=WorkerBackedRunner,
    )
    window = build_window(controller, storage)
    qtbot.addWidget(window)

    controller.start_bot()
    created["worker"].emit_event(
        {"type": "automation_run_started", "sequence_id": "slot-2-sequence"}
    )
    created["worker"].emit_event(
        {
            "type": "automation_runtime_event",
            "event": {"type": "step_search_started", "step_index": 0},
        }
    )

    qtbot.waitUntil(
        lambda: window.bot_actions_page.status_label.text()
        == "Status: Running\nCurrent slot: Slot 2 (L)"
    )
    controller._runner.running = False


def test_main_window_capture_updates_bot_action_slot_via_controller(qtbot) -> None:
    captured_path = Path("bot_actions/slot_1_r.png")
    capture_service = FakeSlotCaptureService(captured_path)
    controller = FakeController()
    window = build_window(
        controller,
        FakeStorage(),
        slot_capture_service=capture_service,
    )
    qtbot.addWidget(window)

    qtbot.mouseClick(window.bot_actions_page.slot_boxes[0].capture_button, Qt.MouseButton.LeftButton)

    captured_slot, existing_path = capture_service.calls[-1]
    assert captured_slot.key == "slot_1_r"
    assert existing_path is None
    assert controller.bot_action_slot_template_updates == [(0, captured_path)]
    assert controller.config.bot_action_slots[0].template_path == captured_path
    assert (
        window.bot_actions_page.slot_boxes[0].template_status_label.text()
        == str(captured_path)
    )
    assert window.bot_actions_page.status_label.text() == "Status: Slot 1 (R): image saved"


def test_main_window_capture_updates_page_ready_template_via_controller(qtbot) -> None:
    captured_path = Path("bot_actions/page_ready.png")
    capture_service = FakeSlotCaptureService(captured_path)
    controller = FakeController()
    window = build_window(
        controller,
        FakeStorage(),
        slot_capture_service=capture_service,
    )
    qtbot.addWidget(window)

    qtbot.mouseClick(window.bot_actions_page.page_ready_capture_button, Qt.MouseButton.LeftButton)

    assert capture_service.capture_to_path_calls == [
        (Path("bot_actions/page_ready.png"), None)
    ]
    assert controller.page_ready_template_updates == [captured_path]
    assert controller.config.page_ready_template_path == captured_path
    assert window.bot_actions_page.page_ready_status_label.text() == str(captured_path)
    assert window.bot_actions_page.status_label.text() == "Status: Page Ready: image saved"


def test_main_window_capture_refreshes_slot_preview_when_same_path_is_overwritten(
    qtbot,
    tmp_path,
) -> None:
    image_path = tmp_path / "slot_1_r.png"
    _write_solid_image(image_path, "#ff0000")
    default_slots = build_config().bot_action_slots
    controller = FakeController(
        config=build_config(
            bot_action_slots=(
                replace(default_slots[0], template_path=image_path),
                *default_slots[1:],
            )
        )
    )
    capture_service = OverwritingSlotCaptureService(image_path, ["#00ff00"])
    window = build_window(
        controller,
        FakeStorage(),
        slot_capture_service=capture_service,
    )
    qtbot.addWidget(window)

    assert _label_center_hex(window.bot_actions_page.slot_boxes[0].template_preview_label) == "#ff0000"

    qtbot.mouseClick(window.bot_actions_page.slot_boxes[0].capture_button, Qt.MouseButton.LeftButton)

    assert controller.bot_action_slot_template_updates == [(0, image_path)]
    assert _label_center_hex(window.bot_actions_page.slot_boxes[0].template_preview_label) == "#00ff00"


def test_main_window_capture_refreshes_page_ready_preview_when_same_path_is_overwritten(
    qtbot,
    tmp_path,
) -> None:
    image_path = tmp_path / "page_ready.png"
    _write_solid_image(image_path, "#ff0000")
    controller = FakeController(config=build_config(page_ready_template_path=image_path))
    capture_service = OverwritingSlotCaptureService(image_path, ["#00ff00"])
    window = build_window(
        controller,
        FakeStorage(),
        slot_capture_service=capture_service,
    )
    qtbot.addWidget(window)

    assert _label_center_hex(window.bot_actions_page.page_ready_preview_label) == "#ff0000"

    qtbot.mouseClick(window.bot_actions_page.page_ready_capture_button, Qt.MouseButton.LeftButton)

    assert controller.page_ready_template_updates == [image_path]
    assert _label_center_hex(window.bot_actions_page.page_ready_preview_label) == "#00ff00"


def test_main_window_slot_1_presets_dialog_capture_updates_finish_preview(qtbot) -> None:
    finish_path = Path("bot_actions/slot_1_r_finish.png")
    capture_service = FakeSlotCaptureService(finish_path)
    controller = FakeController()
    window = build_window(
        controller,
        FakeStorage(),
        slot_capture_service=capture_service,
    )
    qtbot.addWidget(window)

    qtbot.mouseClick(window.bot_actions_page.slot_boxes[0].presets_button, Qt.MouseButton.LeftButton)

    dialog = window._slot_1_presets_dialog
    assert dialog is not None

    qtbot.mouseClick(dialog.capture_finish_button, Qt.MouseButton.LeftButton)

    assert capture_service.capture_to_path_calls == [
        (Path("bot_actions/slot_1_r_finish.png"), None)
    ]
    assert controller.bot_action_slot_1_presets_updates[-1] == ((), finish_path)
    assert dialog.finish_template_path == finish_path
    assert dialog.finish_image_status_label.text() == str(finish_path)


def test_main_window_slot_1_finish_capture_refreshes_card_preview_when_same_path_is_overwritten(
    qtbot,
    tmp_path,
) -> None:
    finish_path = tmp_path / "slot_1_r_finish.png"
    _write_solid_image(finish_path, "#ff0000")
    default_slots = build_config().bot_action_slots
    controller = FakeController(
        config=build_config(
            bot_action_slots=(
                replace(default_slots[0], finish_template_path=finish_path),
                *default_slots[1:],
            )
        )
    )
    capture_service = OverwritingSlotCaptureService(finish_path, ["#00ff00"])
    window = build_window(
        controller,
        FakeStorage(),
        slot_capture_service=capture_service,
    )
    qtbot.addWidget(window)

    finish_preview_label = window.bot_actions_page.slot_boxes[0].finish_preview_label
    assert finish_preview_label is not None
    assert _label_center_hex(finish_preview_label) == "#ff0000"

    qtbot.mouseClick(window.bot_actions_page.slot_boxes[0].presets_button, Qt.MouseButton.LeftButton)
    dialog = window._slot_1_presets_dialog
    assert dialog is not None

    qtbot.mouseClick(dialog.capture_finish_button, Qt.MouseButton.LeftButton)

    assert controller.bot_action_slot_1_presets_updates[-1] == ((), finish_path)
    assert _label_center_hex(finish_preview_label) == "#00ff00"


def test_main_window_slot_1_presets_dialog_capture_updates_finish_preview(
    qtbot,
) -> None:
    finish_path = Path("bot_actions/slot_1_r_finish.png")
    capture_service = FakeSlotCaptureService(finish_path)
    controller = FakeController()
    window = build_window(
        controller,
        FakeStorage(),
        slot_capture_service=capture_service,
    )
    qtbot.addWidget(window)

    qtbot.mouseClick(window.bot_actions_page.slot_boxes[0].presets_button, Qt.MouseButton.LeftButton)

    dialog = window._slot_1_presets_dialog
    assert dialog is not None

    qtbot.mouseClick(dialog.capture_finish_button, Qt.MouseButton.LeftButton)

    assert capture_service.capture_to_path_calls == [
        (Path("bot_actions/slot_1_r_finish.png"), None)
    ]
    assert controller.bot_action_slot_1_presets_updates[-1] == ((), finish_path)
    assert dialog.finish_template_path == finish_path
    assert dialog.finish_image_status_label.text() == str(finish_path)


def test_main_window_slot_1_presets_dialog_save_persists_multiple_presets_and_image(
    qtbot,
    monkeypatch,
    tmp_path: Path,
) -> None:
    preset_image_path = tmp_path / "preset.png"
    preset_image_path.write_bytes(b"fake image")
    controller = FakeController(
        build_config(
            bot_action_slots=(
                BotActionSlotConfig(
                    key="slot_1_r",
                    label="R",
                    enabled=True,
                    presets=(
                        BotActionPreset(id="preset-1", text="gm"),
                    ),
                ),
                *build_config().bot_action_slots[1:],
            )
        )
    )
    window = build_window(controller, FakeStorage(config=controller.config))
    qtbot.addWidget(window)
    monkeypatch.setattr(
        "raidbot.desktop.bot_actions.presets_dialog.QFileDialog.getOpenFileName",
        lambda *_args, **_kwargs: (str(preset_image_path), "Images (*.png)"),
    )

    qtbot.mouseClick(window.bot_actions_page.slot_boxes[0].presets_button, Qt.MouseButton.LeftButton)

    dialog = window._slot_1_presets_dialog
    assert dialog is not None
    dialog.preset_list.setCurrentRow(0)
    dialog.preset_text_input.setPlainText("gm first")
    qtbot.mouseClick(dialog.add_preset_button, Qt.MouseButton.LeftButton)
    dialog.preset_text_input.setPlainText("gm second")
    qtbot.mouseClick(dialog.upload_image_button, Qt.MouseButton.LeftButton)
    qtbot.mouseClick(
        dialog.button_box.button(dialog.button_box.StandardButton.Save),
        Qt.MouseButton.LeftButton,
    )

    assert controller.config.bot_action_slots[0].presets == (
        BotActionPreset(id="preset-1", text="gm first"),
        BotActionPreset(
            id=controller.config.bot_action_slots[0].presets[1].id,
            text="gm second",
            image_path=preset_image_path,
        ),
    )
    assert window.bot_actions_page.status_label.text() == "Status: Slot 1 (R): presets saved"


def test_main_window_test_button_calls_controller_slot_test(qtbot) -> None:
    controller = FakeController()
    window = build_window(controller, FakeStorage())
    qtbot.addWidget(window)

    qtbot.mouseClick(window.bot_actions_page.slot_boxes[0].test_button, Qt.MouseButton.LeftButton)

    assert controller.bot_action_slot_test_calls == [0]


def test_main_window_slot_test_events_show_simple_status(qtbot) -> None:
    window = build_window(FakeController(), FakeStorage())
    qtbot.addWidget(window)

    window.controller.botActionRunEvent.emit(
        {
            "type": "slot_test_started",
            "slot_index": 0,
            "message": "Slot 1 (R): testing",
        }
    )
    assert window.bot_actions_page.status_label.text() == "Status: Slot 1 (R): testing"

    window.controller.botActionRunEvent.emit(
        {
            "type": "slot_test_failed",
            "slot_index": 0,
            "reason": "match_not_found",
            "message": "Slot 1 (R): image not found",
        }
    )
    assert window.bot_actions_page.status_label.text() == (
        "Status: Slot 1 (R): image not found"
    )

    window.controller.botActionRunEvent.emit(
        {
            "type": "slot_test_succeeded",
            "slot_index": 0,
            "message": "Slot 1 (R): success",
        }
    )
    assert window.bot_actions_page.status_label.text() == "Status: Slot 1 (R): success"


def test_main_window_capture_cancel_with_existing_path_does_not_persist_noop(qtbot) -> None:
    existing_path = Path("bot_actions/slot_1_r.png")
    config = build_config(
        bot_action_slots=(
            replace(build_config().bot_action_slots[0], template_path=existing_path),
            *build_config().bot_action_slots[1:],
        )
    )
    capture_service = FakeSlotCaptureService(existing_path)
    controller = FakeController(config=config)
    window = build_window(
        controller,
        FakeStorage(config=config),
        slot_capture_service=capture_service,
    )
    qtbot.addWidget(window)

    qtbot.mouseClick(window.bot_actions_page.slot_boxes[0].capture_button, Qt.MouseButton.LeftButton)

    assert capture_service.calls[-1][1] == existing_path
    assert controller.bot_action_slot_template_updates == [(0, existing_path)]
    assert controller.apply_calls == []


def test_main_window_capture_save_failure_surfaces_error_without_persisting(qtbot) -> None:
    capture_service = FakeSlotCaptureService(error=OSError("Could not save bot_actions/slot_1_r.png"))
    controller = FakeController()
    window = build_window(
        controller,
        FakeStorage(),
        slot_capture_service=capture_service,
    )
    qtbot.addWidget(window)

    qtbot.mouseClick(window.bot_actions_page.slot_boxes[0].capture_button, Qt.MouseButton.LeftButton)

    assert controller.bot_action_slot_template_updates == []
    assert window.bot_actions_page.status_label.text() == (
        "Status: Idle\nLast error: Could not save bot_actions/slot_1_r.png"
    )


def test_main_window_wraps_long_tabs_in_scroll_areas(qtbot) -> None:
    window = build_window(FakeController(), FakeStorage())
    qtbot.addWidget(window)

    dashboard_tab = window.tabs.widget(0)
    settings_tab = window.tabs.widget(1)
    bot_actions_tab = window.tabs.widget(2)

    assert isinstance(dashboard_tab, QScrollArea)
    assert dashboard_tab.widgetResizable() is True
    assert settings_tab.widget() is window.settings_page
    assert bot_actions_tab.widget() is window.bot_actions_page


def test_main_window_slot_enabled_changes_persist_through_controller(qtbot) -> None:
    controller = FakeController()
    window = build_window(controller, FakeStorage())
    qtbot.addWidget(window)

    window.bot_actions_page.slot_boxes[1].enabled_checkbox.setChecked(True)

    assert controller.bot_action_slot_enabled_updates == [(1, True)]
    assert controller.config.bot_action_slots[1].enabled is True


def test_main_window_slot_enabled_change_does_not_reload_available_chats(qtbot) -> None:
    controller = FakeController()
    chat_load_calls: list[str] = []

    def load_available_chats():
        chat_load_calls.append("load")
        return [AccessibleChat(chat_id=-1001, title="Raid Group")]

    window = build_window(
        controller,
        FakeStorage(),
        available_chats_loader=load_available_chats,
    )
    qtbot.addWidget(window)

    assert chat_load_calls == ["load"]

    window.bot_actions_page.slot_boxes[1].enabled_checkbox.setChecked(True)

    assert chat_load_calls == ["load"]


def test_main_window_refreshes_available_chats_when_session_source_changes(qtbot) -> None:
    controller = FakeController()
    chat_load_calls: list[str] = []

    def load_available_chats():
        chat_load_calls.append("load")
        return [AccessibleChat(chat_id=-1001, title="Raid Group")]

    window = build_window(
        controller,
        FakeStorage(),
        available_chats_loader=load_available_chats,
    )
    qtbot.addWidget(window)

    controller.apply_config(
        replace(
            controller.config,
            telegram_session_path=Path("other.session"),
        )
    )

    assert chat_load_calls == ["load", "load"]


def test_main_window_slot_1_finish_delay_changes_persist_through_controller(
    qtbot,
) -> None:
    controller = FakeController()
    window = build_window(controller, FakeStorage())
    qtbot.addWidget(window)

    window.bot_actions_page.slot_1_finish_delay_input.setValue(4)

    assert controller.slot_1_finish_delay_seconds_updates == [4]
    assert controller.config.slot_1_finish_delay_seconds == 4


def test_main_window_running_queue_state_renders_running_status(qtbot) -> None:
    window = build_window(FakeController(), FakeStorage())
    qtbot.addWidget(window)

    window.controller.automationQueueStateChanged.emit("running")

    assert window.bot_actions_page.status_label.text() == "Status: Running"


def test_automation_page_emits_start_and_save_requests(qtbot) -> None:
    from raidbot.desktop.automation.page import AutomationPage

    page = AutomationPage(
        sequences=[build_sequence()],
        windows=[build_window_info()],
    )
    qtbot.addWidget(page)
    saved = []
    started = []
    page.sequenceSaveRequested.connect(saved.append)
    page.runRequested.connect(lambda sequence_id, handle: started.append((sequence_id, handle)))

    page.sequence_name_input.setText("Updated Chrome Flow")
    qtbot.mouseClick(page.save_button, Qt.MouseButton.LeftButton)
    qtbot.mouseClick(page.start_button, Qt.MouseButton.LeftButton)

    assert saved[-1].name == "Updated Chrome Flow"
    assert started == [("seq-1", None)]


def test_automation_page_emits_dry_run_request(qtbot) -> None:
    from raidbot.desktop.automation.page import AutomationPage

    page = AutomationPage(
        sequences=[build_sequence()],
        windows=[build_window_info()],
    )
    qtbot.addWidget(page)
    captured = []
    page.dryRunRequested.connect(
        lambda sequence_id, step_index, handle: captured.append(
            (sequence_id, step_index, handle)
        )
    )

    page.window_combo.setCurrentIndex(1)
    qtbot.mouseClick(page.dry_run_button, Qt.MouseButton.LeftButton)

    assert captured == [("seq-1", 0, 7)]


def test_automation_page_displays_dry_run_match_without_clicking(qtbot) -> None:
    from raidbot.desktop.automation.page import AutomationPage

    page = AutomationPage(
        sequences=[build_sequence()],
        windows=[build_window_info()],
    )
    qtbot.addWidget(page)

    page.handle_run_event(
        {
            "type": "dry_run_match_found",
            "step_index": 0,
            "window_handle": 7,
            "score": 0.97,
        }
    )

    assert "0.97" in page.status_label.text()


def test_automation_page_shows_immediate_feedback_for_common_buttons(qtbot) -> None:
    from raidbot.desktop.automation.page import AutomationPage

    page = AutomationPage(
        sequences=[build_sequence()],
        windows=[build_window_info()],
        auto_run_enabled=True,
    )
    qtbot.addWidget(page)

    saved = []
    deleted = []
    refreshed = []
    started = []
    dry_runs = []
    resumed = []
    cleared = []
    stopped = []
    page.sequenceSaveRequested.connect(saved.append)
    page.sequenceDeleteRequested.connect(deleted.append)
    page.windowsRefreshRequested.connect(lambda: refreshed.append(True))
    page.runRequested.connect(lambda sequence_id, handle: started.append((sequence_id, handle)))
    page.dryRunRequested.connect(lambda sequence_id, step_index, handle: dry_runs.append((sequence_id, step_index, handle)))
    page.resumeQueueRequested.connect(lambda: resumed.append(True))
    page.clearQueueRequested.connect(lambda: cleared.append(True))
    page.stopRequested.connect(lambda: stopped.append(True))

    qtbot.mouseClick(page.save_button, Qt.MouseButton.LeftButton)
    assert page.status_label.text() == "Sequence saved."
    assert len(saved) == 1

    qtbot.mouseClick(page.add_step_button, Qt.MouseButton.LeftButton)
    assert page.status_label.text() == "Step added."

    qtbot.mouseClick(page.remove_step_button, Qt.MouseButton.LeftButton)
    assert page.status_label.text() == "Step removed."

    qtbot.mouseClick(page.refresh_windows_button, Qt.MouseButton.LeftButton)
    assert page.status_label.text() == "Refreshing target windows..."
    assert refreshed == [True]

    qtbot.mouseClick(page.start_button, Qt.MouseButton.LeftButton)
    assert page.status_label.text() == "Starting manual run..."
    assert started == [("seq-1", None)]

    qtbot.mouseClick(page.dry_run_button, Qt.MouseButton.LeftButton)
    assert page.status_label.text() == "Running dry run..."
    assert dry_runs == [("seq-1", 0, None)]

    page.set_queue_state("paused")
    page.set_queue_length(0)
    qtbot.mouseClick(page.resume_queue_button, Qt.MouseButton.LeftButton)
    assert page.status_label.text() == "Resuming queue..."
    assert resumed == [True]

    qtbot.mouseClick(page.clear_queue_button, Qt.MouseButton.LeftButton)
    assert page.status_label.text() == "Clearing queue..."
    assert cleared == [True]

    page.set_run_state("running")
    qtbot.mouseClick(page.stop_button, Qt.MouseButton.LeftButton)
    assert page.status_label.text() == "Stopping run..."
    assert stopped == [True]

    qtbot.mouseClick(page.delete_button, Qt.MouseButton.LeftButton)
    assert page.status_label.text() == "Sequence deleted."
    assert deleted == ["seq-1"]


def test_main_window_settings_page_hides_legacy_automation_controls(qtbot) -> None:
    from raidbot.desktop.main_window import MainWindow

    window = MainWindow(controller=FakeController(), storage=FakeStorage())
    qtbot.addWidget(window)

    assert not hasattr(window.settings_page, "automation_section")
    assert not hasattr(window.settings_page, "browser_mode_combo")


def test_main_window_routes_detected_raid_profile_add_and_reorder_actions(qtbot) -> None:
    from raidbot.desktop.chrome_profiles import ChromeProfile

    controller = FakeController(
        config=build_config(
            chrome_profile_directory="Default",
            raid_profiles=(
                RaidProfileConfig(
                    profile_directory="Default",
                    label="George",
                    enabled=True,
                ),
            ),
        )
    )
    window = build_window(
        controller,
        FakeStorage(config=controller.config),
        available_profiles_loader=lambda: [
            ChromeProfile(directory_name="Default", label="George"),
            ChromeProfile(directory_name="Profile 3", label="Maria"),
            ChromeProfile(directory_name="Profile 9", label="Pasok"),
        ],
    )
    qtbot.addWidget(window)

    window.settings_page.available_profile_combo.setCurrentText("Maria [Profile 3]")
    qtbot.mouseClick(window.settings_page.add_profile_button, Qt.MouseButton.LeftButton)
    window.settings_page.available_profile_combo.setCurrentText("Pasok [Profile 9]")
    qtbot.mouseClick(window.settings_page.add_profile_button, Qt.MouseButton.LeftButton)
    window.settings_page.raid_profiles_list.setCurrentRow(2)
    qtbot.mouseClick(window.settings_page.move_profile_up_button, Qt.MouseButton.LeftButton)

    assert controller.raid_profile_add_calls == [
        ("Profile 3", "Maria"),
        ("Profile 9", "Pasok"),
    ]
    assert controller.raid_profile_move_calls == [("Profile 9", "up")]
    assert [window.settings_page.raid_profiles_list.item(index).text() for index in range(window.settings_page.raid_profiles_list.count())] == [
        "George [Default]",
        "Pasok [Profile 9]",
        "Maria [Profile 3]",
    ]


def test_main_window_refreshes_available_profiles_when_profile_picker_opens(qtbot) -> None:
    from raidbot.desktop.chrome_profiles import ChromeProfile

    controller = FakeController(
        config=build_config(
            chrome_profile_directory="Default",
            raid_profiles=(
                RaidProfileConfig(
                    profile_directory="Default",
                    label="George",
                    enabled=True,
                ),
            ),
        )
    )
    available_profiles = [
        [ChromeProfile(directory_name="Default", label="George")],
        [
            ChromeProfile(directory_name="Default", label="George"),
            ChromeProfile(directory_name="Profile 12", label="Elena"),
        ],
    ]
    loader_calls = []

    def load_profiles():
        loader_calls.append(True)
        index = min(len(loader_calls) - 1, len(available_profiles) - 1)
        return available_profiles[index]

    window = build_window(
        controller,
        FakeStorage(config=controller.config),
        available_profiles_loader=load_profiles,
    )
    qtbot.addWidget(window)

    assert [window.settings_page.profile_combo.itemText(index) for index in range(window.settings_page.profile_combo.count())] == [
        "George [Default]",
    ]

    window.settings_page.available_profile_combo.showPopup()
    window.settings_page.available_profile_combo.hidePopup()
    window.settings_page.available_profile_combo.setCurrentText("Elena [Profile 12]")
    qtbot.mouseClick(window.settings_page.add_profile_button, Qt.MouseButton.LeftButton)

    assert len(loader_calls) == 2
    assert controller.raid_profile_add_calls == [("Profile 12", "Elena")]
    assert [window.settings_page.profile_combo.itemText(index) for index in range(window.settings_page.profile_combo.count())] == [
        "George [Default]",
        "Elena [Profile 12]",
    ]


def test_main_window_renders_raid_profile_cards_from_state(qtbot) -> None:
    controller = FakeController(
        config=build_config(
            chrome_profile_directory="Default",
            raid_profiles=(
                RaidProfileConfig("Default", "George", True),
                RaidProfileConfig("Profile 3", "Maria", True),
            ),
        )
    )
    storage = FakeStorage(
        config=controller.config,
        state=DesktopAppState(
            raid_profile_states=(
                RaidProfileState("Default", "George", "green", None),
                RaidProfileState("Profile 3", "Maria", "red", "login required"),
            )
        ),
    )
    window = build_window(controller, storage)
    qtbot.addWidget(window)

    assert list(window.raid_profile_cards) == ["Default", "Profile 3"]
    assert window.raid_profile_cards["Default"].title_label.text() == "George"
    assert window.raid_profile_cards["Default"].property("profileStatus") == "green"
    assert window.raid_profile_cards["Default"].restart_button.isHidden() is True
    assert window.raid_profile_cards["Profile 3"].title_label.text() == "Maria"
    assert window.raid_profile_cards["Profile 3"].property("profileStatus") == "red"
    assert window.raid_profile_cards["Profile 3"].restart_button.isHidden() is False
    assert (
        window.raid_profile_cards["Profile 3"].reason_label.text() == "login required"
    )


def test_main_window_wraps_raid_profile_cards_across_rows(qtbot) -> None:
    profiles = tuple(
        RaidProfileConfig(f"Profile {index}", f"Profile {index}", True)
        for index in range(1, 9)
    )
    controller = FakeController(
        config=build_config(
            chrome_profile_directory="Profile 1",
            raid_profiles=profiles,
        )
    )
    storage = FakeStorage(
        config=controller.config,
        state=DesktopAppState(
            raid_profile_states=tuple(
                RaidProfileState(profile.profile_directory, profile.label, "green", None)
                for profile in profiles
            )
        ),
    )
    window = build_window(controller, storage)
    qtbot.addWidget(window)

    with qtbot.waitExposed(window):
        window.resize(920, 860)
        window.show()

    row_positions = {card.y() for card in window.raid_profile_cards.values()}

    assert len(row_positions) > 1


def test_main_window_profile_card_click_toggles_failure_reason(qtbot) -> None:
    controller = FakeController(
        config=build_config(
            chrome_profile_directory="Profile 3",
            raid_profiles=(RaidProfileConfig("Profile 3", "Maria", True),),
        )
    )
    storage = FakeStorage(
        config=controller.config,
        state=DesktopAppState(
            raid_profile_states=(
                RaidProfileState("Profile 3", "Maria", "red", "login required"),
            )
        ),
    )
    window = build_window(controller, storage)
    qtbot.addWidget(window)
    card = window.raid_profile_cards["Profile 3"]

    assert card.reason_label.isHidden() is True

    qtbot.mouseClick(card, Qt.MouseButton.LeftButton)
    assert card.reason_label.isHidden() is False

    qtbot.mouseClick(card, Qt.MouseButton.LeftButton)
    assert card.reason_label.isHidden() is True


def test_main_window_profile_card_restart_routes_to_controller(qtbot) -> None:
    controller = FakeController(
        config=build_config(
            chrome_profile_directory="Profile 3",
            raid_profiles=(RaidProfileConfig("Profile 3", "Maria", True),),
        )
    )
    storage = FakeStorage(
        config=controller.config,
        state=DesktopAppState(
            raid_profile_states=(
                RaidProfileState("Profile 3", "Maria", "red", "login required"),
            )
        ),
    )
    window = build_window(controller, storage)
    qtbot.addWidget(window)

    qtbot.mouseClick(
        window.raid_profile_cards["Profile 3"].restart_button,
        Qt.MouseButton.LeftButton,
    )

    assert controller.restart_raid_profile_calls == ["Profile 3"]


def test_main_window_profile_card_renders_raid_on_restart_toggle(qtbot) -> None:
    controller = FakeController(
        config=build_config(
            chrome_profile_directory="Profile 3",
            raid_profiles=(
                RaidProfileConfig("Default", "George", True, False),
                RaidProfileConfig("Profile 3", "Maria", True, True),
            ),
        )
    )
    storage = FakeStorage(
        config=controller.config,
        state=DesktopAppState(
            raid_profile_states=(
                RaidProfileState("Default", "George", "green", None),
                RaidProfileState("Profile 3", "Maria", "red", "login required"),
            )
        ),
    )
    window = build_window(controller, storage)
    qtbot.addWidget(window)

    default_card = window.raid_profile_cards["Default"]
    maria_card = window.raid_profile_cards["Profile 3"]

    assert default_card.raid_on_restart_label.text() == "Raid on Restart"
    assert default_card.raid_on_restart_toggle.isChecked() is False
    assert maria_card.raid_on_restart_toggle.isChecked() is True


def test_main_window_profile_card_raid_on_restart_toggle_routes_to_controller(
    qtbot,
) -> None:
    controller = FakeController(
        config=build_config(
            chrome_profile_directory="Profile 3",
            raid_profiles=(RaidProfileConfig("Profile 3", "Maria", True, False),),
        )
    )
    storage = FakeStorage(
        config=controller.config,
        state=DesktopAppState(
            raid_profile_states=(
                RaidProfileState("Profile 3", "Maria", "red", "login required"),
            )
        ),
    )
    window = build_window(controller, storage)
    qtbot.addWidget(window)

    qtbot.mouseClick(
        window.raid_profile_cards["Profile 3"].raid_on_restart_toggle,
        Qt.MouseButton.LeftButton,
    )

    assert controller.raid_profile_raid_on_restart_updates == [("Profile 3", True)]


def test_main_window_profile_card_renders_paused_when_all_actions_disabled(qtbot) -> None:
    controller = FakeController(
        config=build_config(
            chrome_profile_directory="Profile 3",
            raid_profiles=(
                RaidProfileConfig(
                    "Profile 3",
                    "Maria",
                    True,
                    False,
                    False,
                    False,
                    False,
                    False,
                ),
            ),
        )
    )
    storage = FakeStorage(
        config=controller.config,
        state=DesktopAppState(
            raid_profile_states=(
                RaidProfileState("Profile 3", "Maria", "green", None),
            )
        ),
    )
    window = build_window(controller, storage)
    qtbot.addWidget(window)

    card = window.raid_profile_cards["Profile 3"]

    assert card.property("profileStatus") == "paused"
    assert card.status_label.text() == "Paused"
    assert card.restart_button.isHidden() is True


def test_main_window_profile_action_cog_routes_overrides_to_controller(qtbot) -> None:
    controller = FakeController(
        config=build_config(
            chrome_profile_directory="Profile 3",
            bot_action_slots=(
                BotActionSlotConfig(key="slot_1_r", label="R", enabled=True),
                BotActionSlotConfig(key="slot_2_l", label="L", enabled=True),
                BotActionSlotConfig(key="slot_3_r", label="R", enabled=True),
                BotActionSlotConfig(key="slot_4_b", label="B", enabled=True),
            ),
            raid_profiles=(RaidProfileConfig("Profile 3", "Maria", True),),
        )
    )
    storage = FakeStorage(
        config=controller.config,
        state=DesktopAppState(
            raid_profile_states=(RaidProfileState("Profile 3", "Maria", "green", None),)
        ),
    )
    window = build_window(
        controller,
        storage,
        profile_action_picker=lambda *_args, **_kwargs: {
            "reply_enabled": False,
            "like_enabled": True,
            "repost_enabled": True,
            "bookmark_enabled": False,
        },
    )
    qtbot.addWidget(window)

    button = window.raid_profile_cards["Profile 3"].action_config_button

    assert button.text() == ""
    assert button.icon().isNull() is False
    assert button.height() == 14
    assert button.width() == 14

    qtbot.mouseClick(
        button,
        Qt.MouseButton.LeftButton,
    )

    assert controller.raid_profile_action_override_updates == [
        {
            "profile_directory": "Profile 3",
            "reply_enabled": False,
            "like_enabled": True,
            "repost_enabled": True,
            "bookmark_enabled": False,
        }
    ]


def test_main_window_routes_settings_apply_errors_back_to_settings_status(qtbot) -> None:
    window = build_window(FailingApplyController(), FakeStorage())
    qtbot.addWidget(window)

    qtbot.mouseClick(window.settings_page.save_button, Qt.MouseButton.LeftButton)

    assert "Could not resolve sender '@missing'." in window.settings_page.status_label.text()


def test_main_window_scan_sender_appends_selected_candidates(qtbot) -> None:
    controller = FakeController(
        config=build_config(
            allowed_sender_ids=[42],
            allowed_sender_entries=("@raidar",),
            whitelisted_chat_ids=[-1001],
        )
    )
    controller.sender_candidate_results = [
        RaidarCandidate(entity_id=42, label="@raidar"),
        RaidarCandidate(entity_id=5349287105, label="@RallyGuard_Raid_Bot"),
    ]
    window = build_window(
        controller,
        FakeStorage(config=controller.config),
        sender_candidate_picker=lambda candidates: [candidates[1].label],
    )
    qtbot.addWidget(window)

    qtbot.mouseClick(
        window.settings_page.sender_scan_buttons[0],
        Qt.MouseButton.LeftButton,
    )

    assert controller.sender_candidate_scan_calls == [[-1001]]
    assert [entry.text() for entry in window.settings_page.sender_entry_inputs] == [
        "@raidar",
        "@RallyGuard_Raid_Bot",
    ]


def test_main_window_scan_sender_button_shows_busy_feedback_then_resets(qtbot) -> None:
    controller = FakeController(
        config=build_config(
            allowed_sender_ids=[42],
            allowed_sender_entries=("@raidar",),
            whitelisted_chat_ids=[-1001],
        )
    )

    def picker(candidates):
        button = window.settings_page.sender_scan_buttons[0]
        assert button.text() == "Scanning..."
        assert button.isEnabled() is False
        return []

    window = build_window(
        controller,
        FakeStorage(config=controller.config),
        sender_candidate_picker=picker,
    )
    qtbot.addWidget(window)

    qtbot.mouseClick(
        window.settings_page.sender_scan_buttons[0],
        Qt.MouseButton.LeftButton,
    )

    assert window.settings_page.sender_scan_buttons[0].text() == "Scan"
    assert window.settings_page.sender_scan_buttons[0].isEnabled() is True


def test_main_window_uses_visible_fallback_icon_for_tray(qtbot) -> None:
    from raidbot.desktop.main_window import MainWindow

    captured = {}

    def tray_factory(**kwargs):
        captured["icon_is_null"] = kwargs["icon"].isNull()
        return object()

    window = MainWindow(
        controller=FakeController(),
        storage=FakeStorage(),
        tray_controller_factory=tray_factory,
    )
    qtbot.addWidget(window)

    assert captured["icon_is_null"] is False
    assert window.windowIcon().isNull() is False


def test_main_window_buttons_reflect_stopped_state_variants(qtbot) -> None:
    window = build_window(FakeController(), FakeStorage())
    qtbot.addWidget(window)

    assert window.start_button.property("variant") == "secondary"
    assert window.stop_button.property("variant") == "danger"


def test_main_window_buttons_reflect_running_state_variants(qtbot) -> None:
    window = build_window(FakeController(), FakeStorage())
    qtbot.addWidget(window)

    window.controller.botStateChanged.emit("running")

    assert window.start_button.property("variant") == "primary"
    assert window.stop_button.property("variant") == "secondary"


def test_running_window_minimizes_to_tray_on_minimize(qtbot) -> None:
    controller = FakeController()
    window = build_window(controller, FakeStorage())
    qtbot.addWidget(window)
    window.show()

    window.handle_minimize_requested()

    assert window.isHidden() is True


def test_setup_window_minimize_behaves_like_normal_window_minimize(qtbot, tmp_path: Path) -> None:
    from raidbot.desktop.chrome_profiles import ChromeEnvironment, ChromeProfile
    from raidbot.desktop.wizard import SetupWizard

    wizard = SetupWizard(
        storage=FakeStorage(base_dir=tmp_path),
        telegram_service_factory=lambda *_args: FakeTelegramSetupService(),
        chrome_environment=ChromeEnvironment(
            chrome_path=Path(r"C:\Chrome\chrome.exe"),
            user_data_dir=Path(r"C:\Chrome\User Data"),
            profiles=[ChromeProfile(directory_name="Profile 3", label="Raid")],
        ),
    )
    qtbot.addWidget(wizard)
    wizard.show()
    wizard.showMinimized()
    qtbot.waitUntil(
        lambda: bool(wizard.windowState() & Qt.WindowState.WindowMinimized)
    )

    assert wizard.isHidden() is False


def test_close_during_setup_exits_normally(qtbot, tmp_path: Path) -> None:
    from raidbot.desktop.chrome_profiles import ChromeEnvironment, ChromeProfile
    from raidbot.desktop.wizard import SetupWizard

    wizard = SetupWizard(
        storage=FakeStorage(base_dir=tmp_path),
        telegram_service_factory=lambda *_args: FakeTelegramSetupService(),
        chrome_environment=ChromeEnvironment(
            chrome_path=Path(r"C:\Chrome\chrome.exe"),
            user_data_dir=Path(r"C:\Chrome\User Data"),
            profiles=[ChromeProfile(directory_name="Profile 3", label="Raid")],
        ),
    )
    qtbot.addWidget(wizard)

    event = QCloseEvent()
    QApplication.sendEvent(wizard, event)

    assert event.isAccepted() is True


def test_close_while_stopped_exits_normally(qtbot) -> None:
    controller = FakeController()
    window = build_window(controller, FakeStorage())
    qtbot.addWidget(window)

    event = QCloseEvent()
    window.closeEvent(event)

    assert event.isAccepted() is True
    assert controller.stop_calls == 0


def test_close_while_running_requests_confirmation_before_exit(qtbot) -> None:
    controller = FakeController()
    controller.active = True
    confirmations = []
    window = build_window(
        controller,
        FakeStorage(),
        confirm_close=lambda: confirmations.append("asked") or True,
    )
    qtbot.addWidget(window)
    controller.botStateChanged.emit("running")

    event = QCloseEvent()
    window.closeEvent(event)

    assert confirmations == ["asked"]
    assert event.isAccepted() is True
    assert controller.stop_calls == 1


def test_close_while_running_uses_synchronous_shutdown_on_controller(qtbot) -> None:
    class BlockingShutdownController(FakeController):
        def __init__(self) -> None:
            super().__init__()
            self.stop_and_wait_calls = 0

        def stop_bot(self) -> None:
            raise AssertionError("closeEvent should use stop_bot_and_wait")

        def stop_bot_and_wait(self) -> None:
            self.stop_and_wait_calls += 1
            return True

    controller = BlockingShutdownController()
    controller.active = True
    window = build_window(
        controller,
        FakeStorage(),
        confirm_close=lambda: True,
    )
    qtbot.addWidget(window)
    controller.botStateChanged.emit("running")

    event = QCloseEvent()
    window.closeEvent(event)

    assert controller.stop_and_wait_calls == 1
    assert event.isAccepted() is True


def test_close_while_stopping_still_waits_for_active_controller_shutdown(qtbot) -> None:
    controller = FakeController()
    controller.active = True
    window = build_window(
        controller,
        FakeStorage(),
        confirm_close=lambda: True,
    )
    qtbot.addWidget(window)
    controller.botStateChanged.emit("stopping")

    event = QCloseEvent()
    window.closeEvent(event)

    assert controller.stop_calls == 1
    assert event.isAccepted() is True


def test_close_while_running_uses_default_confirmation_dialog(qtbot, monkeypatch) -> None:
    from raidbot.desktop import main_window as main_window_module
    from PySide6.QtWidgets import QMessageBox

    controller = FakeController()
    controller.active = True
    asked = []

    def fake_question(*_args, **_kwargs):
        asked.append("asked")
        return QMessageBox.StandardButton.No

    monkeypatch.setattr(main_window_module.QMessageBox, "question", fake_question)

    window = build_window(controller, FakeStorage(), confirm_close=None)
    qtbot.addWidget(window)
    window.show()
    qtbot.waitUntil(window.isVisible)
    controller.botStateChanged.emit("running")

    event = QCloseEvent()
    window.closeEvent(event)

    assert asked == ["asked"]
    assert event.isAccepted() is False
    assert controller.stop_calls == 0


def test_hidden_window_close_confirmation_centers_dialog_on_screen(
    qtbot,
    monkeypatch,
) -> None:
    from raidbot.desktop import main_window as main_window_module

    controller = FakeController()
    controller.active = True
    dialog_calls: list[tuple[object | None, tuple[int, int] | None]] = []

    class FakeMessageBox:
        class StandardButton:
            Yes = 1
            No = 2

        def __init__(self, parent=None) -> None:
            self.parent = parent
            self._frame = QRect(0, 0, 240, 120)
            self._moved_to: tuple[int, int] | None = None

        def setWindowTitle(self, _title: str) -> None:
            return None

        def setText(self, _text: str) -> None:
            return None

        def setStandardButtons(self, _buttons) -> None:
            return None

        def setDefaultButton(self, _button) -> None:
            return None

        def adjustSize(self) -> None:
            return None

        def frameGeometry(self) -> QRect:
            return QRect(self._frame)

        def move(self, x: int, y: int) -> None:
            self._moved_to = (x, y)

        def exec(self):
            dialog_calls.append((self.parent, self._moved_to))
            return self.StandardButton.No

    monkeypatch.setattr(main_window_module, "QMessageBox", FakeMessageBox)

    window = build_window(controller, FakeStorage(), confirm_close=None)
    qtbot.addWidget(window)
    controller.botStateChanged.emit("running")
    window.hide()
    monkeypatch.setattr(
        window,
        "_primary_screen_geometry",
        lambda: QRect(100, 100, 800, 600),
    )

    event = QCloseEvent()
    window.closeEvent(event)

    assert dialog_calls == [(None, (380, 340))]
    assert event.isAccepted() is False


def test_tray_toggle_action_tracks_runtime_state_model(qtbot) -> None:
    from raidbot.desktop.tray import TrayController

    controller = FakeController()
    window = build_window(controller, FakeStorage())
    qtbot.addWidget(window)
    tray = TrayController(
        window=window,
        controller=controller,
        icon=QIcon(),
        tray_icon_factory=FakeTrayIcon,
        menu_factory=FakeMenu,
        initial_bot_state="stopped",
    )

    assert tray.toggle_action.text() == "Start bot"
    controller.botStateChanged.emit("running")
    assert tray.toggle_action.text() == "Stop bot"
    assert tray.toggle_action.isEnabled() is True
    controller.botStateChanged.emit("starting")
    assert tray.toggle_action.text() == "Starting..."
    assert tray.toggle_action.isEnabled() is False
    tray.toggle_action.trigger()
    assert controller.start_calls == 0
    controller.botStateChanged.emit("stopping")
    assert tray.toggle_action.text() == "Stopping..."
    assert tray.toggle_action.isEnabled() is False
    tray.toggle_action.trigger()
    assert controller.stop_calls == 0
    controller.botStateChanged.emit("setup_required")
    assert tray.toggle_action.text() == "Setup required"
    assert tray.toggle_action.isEnabled() is False
    tray.toggle_action.trigger()
    assert controller.start_calls == 0
    controller.botStateChanged.emit("error")
    assert tray.toggle_action.text() == "Retry start"
    assert tray.toggle_action.isEnabled() is True
    tray.toggle_action.trigger()
    assert controller.start_calls == 1
    controller.botStateChanged.emit("stopped")
    assert tray.toggle_action.text() == "Start bot"
    assert tray.tray.tooltip == "L8N Raid Bot"


def test_tray_click_restores_main_window(qtbot) -> None:
    from raidbot.desktop.tray import TrayController

    controller = FakeController()
    window = build_window(controller, FakeStorage())
    qtbot.addWidget(window)
    tray = TrayController(
        window=window,
        controller=controller,
        icon=QIcon(),
        tray_icon_factory=FakeTrayIcon,
        menu_factory=FakeMenu,
        initial_bot_state="stopped",
    )
    window.show()
    window.hide()

    tray._handle_activated(QSystemTrayIcon.ActivationReason.Trigger)

    assert window.isVisible() is True


def test_tray_restore_prefers_window_restore_from_tray(qtbot) -> None:
    from raidbot.desktop.tray import TrayController

    tray = TrayController(
        window=SimpleNamespace(
            restore_from_tray=lambda: restore_calls.append("restore_from_tray"),
            showNormal=lambda: restore_calls.append("showNormal"),
            raise_=lambda: restore_calls.append("raise"),
            activateWindow=lambda: restore_calls.append("activate"),
        ),
        controller=FakeController(),
        icon=QIcon(),
        tray_icon_factory=FakeTrayIcon,
        menu_factory=FakeMenu,
        initial_bot_state="stopped",
    )
    restore_calls: list[str] = []

    tray.restore_window()

    assert restore_calls == ["restore_from_tray"]


def test_main_window_restore_from_tray_uses_last_known_geometry(qtbot) -> None:
    window = build_window(FakeController(), FakeStorage())
    qtbot.addWidget(window)

    expected_geometry = QRect(120, 140, 960, 720)
    window.setGeometry(expected_geometry)
    window._remember_restore_geometry()
    window.setGeometry(0, 0, 320, 240)

    window.restore_from_tray()

    assert window.geometry() == expected_geometry


def test_main_window_restore_from_tray_clamps_offscreen_geometry_onto_available_screen(
    qtbot,
) -> None:
    window = build_window(FakeController(), FakeStorage())
    qtbot.addWidget(window)

    window._restore_geometry = QRect(3000, 400, 960, 640)
    window._restore_was_maximized = False
    window._available_screen_geometries = lambda: [QRect(0, 0, 1280, 720)]
    window._primary_screen_geometry = lambda: QRect(0, 0, 1280, 720)

    window.restore_from_tray()

    assert window.geometry() == QRect(160, 40, 960, 640)


def test_main_window_uses_top_tab_shell(qtbot) -> None:
    window = build_window(FakeController(), FakeStorage())
    qtbot.addWidget(window)

    assert window.findChild(QWidget, "sidebar") is None
    assert len(window.findChildren(QPushButton, "shellTabButton")) == 3
    assert getattr(window, "stack", None) is not None
    assert window.stack.widget(0).findChild(QLabel, "pageTitle") is None
    assert window.top_tabs.layout().contentsMargins().top() == 12
    session_stamp = window.top_tabs.findChild(QLabel, "shellSessionStamp")
    assert session_stamp is not None
    assert session_stamp.text().startswith("v")


def test_main_window_feeds_settings_page_real_profiles_and_session_status(qtbot) -> None:
    from raidbot.desktop.main_window import MainWindow

    controller = FakeController()
    window = MainWindow(
        controller=controller,
        storage=FakeStorage(),
        tray_controller_factory=lambda *args, **kwargs: None,
        available_profiles_loader=lambda: ["Default", "Profile 3", "Profile 9"],
        available_chats_loader=lambda: [
            AccessibleChat(chat_id=-1001, title="Raid Group"),
            AccessibleChat(chat_id=-2002, title="Launch Squad"),
        ],
        session_status_loader=lambda: "authorized",
    )
    qtbot.addWidget(window)

    assert window.settings_page.session_status_label.text() == "authorized"
    assert window.settings_page.profile_combo.count() == 3
    assert [window.settings_page.chat_row_combos[0].itemText(index) for index in range(window.settings_page.chat_row_combos[0].count())] == [
        "Launch Squad [-2002]",
        "Raid Group [-1001]",
    ]
    assert window.settings_page.profile_combo.currentText() == "Default"
    assert window.settings_page.reauthorize_button.isEnabled() is False
    assert "delete the saved desktop config file" in window.settings_page.reauthorize_hint_label.text().lower()
    assert "restart the app" in window.settings_page.reauthorize_hint_label.text().lower()


def test_main_window_default_loaders_feed_settings_page(qtbot, monkeypatch) -> None:
    from raidbot.desktop import main_window as main_window_module
    from raidbot.desktop.chrome_profiles import ChromeEnvironment, ChromeProfile
    from raidbot.desktop.main_window import MainWindow

    class FakeTelegramSetupService:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def get_session_status(self):
            return SessionStatus.authorized

        async def list_accessible_chats(self):
            return [
                AccessibleChat(chat_id=-1001, title="Raid Group"),
                AccessibleChat(chat_id=-2002, title="Launch Squad"),
            ]

    monkeypatch.setattr(
        main_window_module,
        "detect_chrome_environment",
        lambda: ChromeEnvironment(
            chrome_path=Path(r"C:\Chrome\chrome.exe"),
            user_data_dir=Path(r"C:\Chrome\User Data"),
            profiles=[
                ChromeProfile(directory_name="Default", label="Default"),
                ChromeProfile(directory_name="Profile 3", label="Raid"),
                ChromeProfile(directory_name="Profile 9", label="Alt"),
            ],
        ),
    )
    monkeypatch.setattr(
        main_window_module,
        "TelegramSetupService",
        FakeTelegramSetupService,
    )

    controller = FakeController()
    window = MainWindow(
        controller=controller,
        storage=FakeStorage(),
        tray_controller_factory=lambda *args, **kwargs: None,
    )
    qtbot.addWidget(window)

    assert window.settings_page.session_status_label.text() == "authorized"
    assert [window.settings_page.chat_row_combos[0].itemText(index) for index in range(window.settings_page.chat_row_combos[0].count())] == [
        "Launch Squad [-2002]",
        "Raid Group [-1001]",
    ]
    assert [window.settings_page.profile_combo.itemText(index) for index in range(window.settings_page.profile_combo.count())] == [
        "Default",
        "Raid [Profile 3]",
        "Alt [Profile 9]",
    ]
    assert window.settings_page.profile_combo.currentText() == "Default"
    assert window.settings_page.reauthorize_button.isEnabled() is False


def test_main_window_keeps_reauthorize_enabled_when_controller_supports_it(qtbot) -> None:
    from raidbot.desktop.main_window import MainWindow

    class ReauthorizeController(FakeController):
        def reauthorize_session(self) -> None:
            self.reauthorize_calls = getattr(self, "reauthorize_calls", 0) + 1

    controller = ReauthorizeController()
    window = MainWindow(
        controller=controller,
        storage=FakeStorage(),
        tray_controller_factory=lambda *args, **kwargs: None,
        available_profiles_loader=lambda: ["Default", "Profile 3"],
        session_status_loader=lambda: "authorized",
    )
    qtbot.addWidget(window)

    assert window.settings_page.reauthorize_button.isEnabled() is True
    assert window.settings_page.reauthorize_button.property("variant") == "secondary"


def test_main_window_reauthorize_button_calls_controller_when_supported(qtbot) -> None:
    from raidbot.desktop.main_window import MainWindow

    class ReauthorizeController(FakeController):
        def __init__(self) -> None:
            super().__init__()
            self.reauthorize_calls = 0

        def reauthorize_session(self) -> None:
            self.reauthorize_calls += 1

    controller = ReauthorizeController()
    window = MainWindow(
        controller=controller,
        storage=FakeStorage(),
        tray_controller_factory=lambda *args, **kwargs: None,
        available_profiles_loader=lambda: ["Default", "Profile 3"],
        session_status_loader=lambda: "authorized",
    )
    qtbot.addWidget(window)

    qtbot.mouseClick(window.settings_page.reauthorize_button, Qt.MouseButton.LeftButton)

    assert controller.reauthorize_calls == 1
