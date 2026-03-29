from __future__ import annotations

import os
from dataclasses import replace
from datetime import datetime
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QCloseEvent, QIcon
from PySide6.QtWidgets import QApplication, QScrollArea, QSystemTrayIcon

from raidbot.desktop.automation.models import AutomationSequence, AutomationStep
from raidbot.desktop.automation.windowing import WindowInfo
from raidbot.desktop.models import (
    ActivityEntry,
    BotActionPreset,
    BotActionSlotConfig,
    BotRuntimeState,
    DesktopAppConfig,
    DesktopAppState,
    RaidProfileConfig,
    RaidProfileState,
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
        self.bot_action_slot_template_updates = []
        self.bot_action_slot_1_presets_updates = []
        self.bot_action_slot_test_calls = []
        self.bot_action_slot_enabled_updates = []
        self.auto_run_settle_ms_updates = []
        self.raid_profile_add_calls = []
        self.raid_profile_remove_calls = []
        self.raid_profile_move_calls = []
        self.restart_raid_profile_calls = []
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


def build_window(controller: FakeController, storage: FakeStorage, **overrides):
    from raidbot.desktop.main_window import MainWindow

    values = {
        "controller": controller,
        "storage": storage,
        "tray_controller_factory": lambda *args, **kwargs: None,
        "available_profiles_loader": lambda: ["Default", "Profile 3", "Profile 9"],
        "session_status_loader": lambda: "authorized",
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
        self.visible = False

    def setContextMenu(self, menu) -> None:
        self.context_menu = menu

    def show(self) -> None:
        self.visible = True

    def hide(self) -> None:
        self.visible = False


def test_main_window_initializes_from_persisted_state_and_updates_from_signals(qtbot) -> None:
    storage = FakeStorage(
        state=DesktopAppState(
            bot_state=BotRuntimeState.stopped,
            connection_state=TelegramConnectionState.disconnected,
            raids_opened=4,
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
                    timestamp=datetime(2026, 3, 26, 9, 55, 0),
                    action="sender_rejected",
                    url="https://x.com/i/status/100",
                    reason="sender 42 not allowed",
                ),
                ActivityEntry(
                    timestamp=datetime(2026, 3, 26, 9, 57, 0),
                    action="page_ready",
                    url="https://x.com/i/status/101",
                    reason="page ready",
                )
            ],
            last_error="boom",
        )
    )
    controller = FakeController()
    window = build_window(controller, storage)
    qtbot.addWidget(window)

    assert window.bot_state_label.text() == "stopped"
    assert window.connection_state_label.text() == "disconnected"
    assert window.raids_opened_label.text() == "4"
    assert window.sender_rejected_label.text() == "5"
    assert window.browser_session_failed_label.text() == "6"
    assert window.page_ready_label.text() == "7"
    assert window.executor_not_configured_label.text() == "8"
    assert window.executor_succeeded_label.text() == "9"
    assert window.executor_failed_label.text() == "10"
    assert window.session_closed_label.text() == "11"
    assert window.last_error_label.text() == "boom"
    assert window.activity_list.count() == 2
    assert "Page Ready" in window.activity_list.item(0).text()
    assert "Sender Rejected" in window.activity_list.item(1).text()

    updated_state = DesktopAppState(
        bot_state=BotRuntimeState.running,
        connection_state=TelegramConnectionState.connected,
        raids_opened=5,
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
        activity=[],
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
        controller.errorRaised.emit("new-error")

        assert window.bot_state_label.text() == "running"
        assert window.connection_state_label.text() == "connected"
        assert window.raids_opened_label.text() == "5"
        assert window.sender_rejected_label.text() == "12"
        assert window.browser_session_failed_label.text() == "13"
        assert window.page_ready_label.text() == "14"
        assert window.executor_not_configured_label.text() == "15"
        assert window.executor_succeeded_label.text() == "16"
        assert window.executor_failed_label.text() == "17"
        assert window.session_closed_label.text() == "18"
        assert window.last_successful_label.text() == "2026-03-26T10:10:00"
        assert window.last_error_label.text() == "new-error"
        assert window.activity_list.count() == 3
        assert "Executor Failed" in window.activity_list.item(0).text()
        assert "Page Ready" in window.activity_list.item(1).text()
    finally:
        controller.botStateChanged.emit("stopped")


def test_main_window_dashboard_exposes_metric_cards_and_panels(qtbot) -> None:
    from raidbot.desktop.main_window import MainWindow
    from raidbot.desktop.theme import SECTION_OBJECT_NAME

    window = MainWindow(controller=FakeController(), storage=FakeStorage())
    qtbot.addWidget(window)

    assert window.command_status_row.objectName() == "commandStatusRow"
    assert window.command_bot_state_label.objectName() == "commandBotStateLabel"
    assert window.command_connection_state_label.objectName() == "commandConnectionStateLabel"
    assert window.status_panel.objectName() == "statusPanel"
    assert len(window.metric_cards) == 11
    assert window.activity_panel.objectName() == "activityPanel"
    assert window.error_panel.objectName() == "errorPanel"
    assert window.command_status_row.findChild(type(window.status_panel), SECTION_OBJECT_NAME) is not None
    assert window.status_panel.findChild(type(window.status_panel), SECTION_OBJECT_NAME) is not None
    assert window.activity_panel.findChild(type(window.status_panel), SECTION_OBJECT_NAME) is not None
    assert window.error_panel.findChild(type(window.status_panel), SECTION_OBJECT_NAME) is not None


def test_main_window_removed_generic_automation_controls_are_not_visible(qtbot) -> None:
    window = build_window(FakeController(), FakeStorage())
    qtbot.addWidget(window)

    assert window.tabs.tabText(2) == "Bot Actions"
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


def test_main_window_settle_delay_changes_persist_through_controller(qtbot) -> None:
    controller = FakeController()
    window = build_window(controller, FakeStorage())
    qtbot.addWidget(window)

    window.bot_actions_page.settle_delay_input.setValue(2750)

    assert controller.auto_run_settle_ms_updates == [2750]
    assert controller.config.auto_run_settle_ms == 2750


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


def test_main_window_routes_settings_apply_errors_back_to_settings_status(qtbot) -> None:
    window = build_window(FailingApplyController(), FakeStorage())
    qtbot.addWidget(window)

    qtbot.mouseClick(window.settings_page.save_button, Qt.MouseButton.LeftButton)

    assert window.settings_page.status_label.text() == "Could not resolve sender '@missing'."


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


def test_main_window_start_button_uses_primary_variant(qtbot) -> None:
    from raidbot.desktop.main_window import MainWindow

    window = MainWindow(controller=FakeController(), storage=FakeStorage())
    qtbot.addWidget(window)

    assert window.start_button.property("variant") == "primary"


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
    controller.botStateChanged.emit("running")

    event = QCloseEvent()
    window.closeEvent(event)

    assert asked == ["asked"]
    assert event.isAccepted() is False
    assert controller.stop_calls == 0


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


def test_main_window_feeds_settings_page_real_profiles_and_session_status(qtbot) -> None:
    from raidbot.desktop.main_window import MainWindow

    controller = FakeController()
    window = MainWindow(
        controller=controller,
        storage=FakeStorage(),
        tray_controller_factory=lambda *args, **kwargs: None,
        available_profiles_loader=lambda: ["Default", "Profile 3", "Profile 9"],
        session_status_loader=lambda: "authorized",
    )
    qtbot.addWidget(window)

    assert window.settings_page.session_status_label.text() == "authorized"
    assert window.settings_page.profile_combo.count() == 3
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
