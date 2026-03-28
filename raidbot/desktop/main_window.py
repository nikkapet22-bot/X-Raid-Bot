from __future__ import annotations

import asyncio
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
    QStyle,
)

from raidbot.desktop.chrome_profiles import detect_chrome_environment
from raidbot.desktop.automation.page import AutomationPage
from raidbot.desktop.models import DesktopAppState
from raidbot.desktop.settings_page import SettingsPage
from raidbot.desktop.telegram_setup import TelegramSetupService
from raidbot.desktop.theme import CARD_OBJECT_NAME, SECTION_OBJECT_NAME
from raidbot.desktop.tray import TrayController


class MainWindow(QMainWindow):
    def __init__(
        self,
        *,
        controller,
        storage,
        tray_controller_factory=TrayController,
        confirm_close=None,
        available_profiles_loader=None,
        session_status_loader=None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.controller = controller
        self.storage = storage
        self.confirm_close = confirm_close or self._confirm_close
        self.available_profiles_loader = (
            available_profiles_loader or self._load_available_profiles
        )
        self.session_status_loader = session_status_loader or self._load_session_status
        self.bot_state = "stopped"
        self.connection_state = "disconnected"

        self.setWindowTitle("Raid Bot")

        self.bot_state_label = QLabel("")
        self.connection_state_label = QLabel("")
        self.command_bot_state_label = QLabel("")
        self.command_connection_state_label = QLabel("")
        self.raids_opened_label = QLabel("0")
        self.duplicates_label = QLabel("0")
        self.non_matching_label = QLabel("0")
        self.open_failures_label = QLabel("0")
        self.sender_rejected_label = QLabel("0")
        self.browser_session_failed_label = QLabel("0")
        self.page_ready_label = QLabel("0")
        self.executor_not_configured_label = QLabel("0")
        self.executor_succeeded_label = QLabel("0")
        self.executor_failed_label = QLabel("0")
        self.session_closed_label = QLabel("0")
        self.last_successful_label = QLabel("")
        self.last_error_label = QLabel("")
        self.activity_list = QListWidget()

        self.start_button = QPushButton("Start")
        self.stop_button = QPushButton("Stop")
        self.start_button.setProperty("variant", "primary")
        self.stop_button.setProperty("variant", "danger")
        self.start_button.clicked.connect(self.controller.start_bot)
        self.stop_button.clicked.connect(self.controller.stop_bot)

        central_widget = QWidget()
        central_layout = QVBoxLayout(central_widget)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_dashboard_tab(), "Dashboard")
        self.settings_page = SettingsPage(
            config=self.controller.config,
            available_profiles=self.available_profiles_loader(),
            session_status=self.session_status_loader(),
            reauthorize_available=hasattr(self.controller, "reauthorize_session"),
        )
        self.settings_page.applyRequested.connect(self.controller.apply_config)
        if hasattr(self.controller, "reauthorize_session"):
            self.settings_page.reauthorizeRequested.connect(
                self.controller.reauthorize_session
            )
        self.tabs.addTab(self.settings_page, "Settings")
        self.automation_page = AutomationPage(
            sequences=self._load_automation_sequences(),
            windows=self._load_automation_windows(),
            auto_run_enabled=self.controller.config.auto_run_enabled,
            default_auto_sequence_id=self.controller.config.default_auto_sequence_id,
            auto_run_settle_ms=self.controller.config.auto_run_settle_ms,
        )
        self.automation_page.sequenceSaveRequested.connect(
            self.controller.save_automation_sequence
        )
        self.automation_page.sequenceDeleteRequested.connect(
            self.controller.delete_automation_sequence
        )
        self.automation_page.autoRunEnabledRequested.connect(
            self.controller.set_auto_run_enabled
        )
        self.automation_page.defaultAutoSequenceRequested.connect(
            self.controller.set_default_auto_sequence_id
        )
        self.automation_page.autoRunSettleMsRequested.connect(
            self.controller.set_auto_run_settle_ms
        )
        self.automation_page.resumeQueueRequested.connect(
            self.controller.resume_automation_queue
        )
        self.automation_page.clearQueueRequested.connect(
            self.controller.clear_automation_queue
        )
        self.automation_page.runRequested.connect(self.controller.start_automation_run)
        self.automation_page.dryRunRequested.connect(
            self.controller.dry_run_automation_step
        )
        self.automation_page.stopRequested.connect(self.controller.stop_automation_run)
        self.automation_page.windowsRefreshRequested.connect(
            self._refresh_automation_windows
        )
        self.tabs.addTab(self.automation_page, "Automation")
        central_layout.addWidget(self.tabs)

        self.setCentralWidget(central_widget)

        self._connect_controller_signals()
        state = self.storage.load_state()
        self._apply_state(state, include_activity=True)
        self._sync_automation_config(self.controller.config)
        self._sync_automation_queue_state(state)
        self._ensure_window_icon()
        self.tray_controller = tray_controller_factory(
            window=self,
            controller=self.controller,
            icon=self.windowIcon(),
            initial_bot_state=self.bot_state,
        )

    def _build_dashboard_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(16)

        self.command_status_row = self._build_command_status_row()
        layout.addWidget(self.command_status_row)

        self.status_panel = self._build_status_panel()
        layout.addWidget(self.status_panel)

        self.metric_cards = [
            self._build_metric_card("Raids Opened", self.raids_opened_label),
            self._build_metric_card("Duplicates", self.duplicates_label),
            self._build_metric_card("Non-matching", self.non_matching_label),
            self._build_metric_card("Open Failures", self.open_failures_label),
            self._build_metric_card("Sender Rejected", self.sender_rejected_label),
            self._build_metric_card(
                "Browser Session Failed",
                self.browser_session_failed_label,
            ),
            self._build_metric_card("Page Ready", self.page_ready_label),
            self._build_metric_card(
                "Executor Not Configured",
                self.executor_not_configured_label,
            ),
            self._build_metric_card("Executor Succeeded", self.executor_succeeded_label),
            self._build_metric_card("Executor Failed", self.executor_failed_label),
            self._build_metric_card("Session Closed", self.session_closed_label),
        ]
        for card_group in (self.metric_cards[:6], self.metric_cards[6:]):
            metrics_row = QHBoxLayout()
            metrics_row.setSpacing(12)
            for card in card_group:
                metrics_row.addWidget(card)
            layout.addLayout(metrics_row)

        self.activity_panel = self._build_activity_panel()
        self.error_panel = self._build_error_panel()
        layout.addWidget(self.activity_panel)
        layout.addWidget(self.error_panel)
        layout.addStretch()
        return widget

    def _build_command_status_row(self) -> QWidget:
        row, surface = self._build_panel("commandStatusRow")
        layout = QHBoxLayout(surface)
        layout.setSpacing(12)
        layout.addWidget(self.start_button)
        layout.addWidget(self.stop_button)
        layout.addStretch()
        layout.addWidget(
            self._build_compact_status_block(
                "Bot", self.command_bot_state_label, "commandBotStateLabel"
            )
        )
        layout.addWidget(
            self._build_compact_status_block(
                "Telegram",
                self.command_connection_state_label,
                "commandConnectionStateLabel",
            )
        )
        return row

    def _build_status_panel(self) -> QWidget:
        panel, surface = self._build_panel("statusPanel")
        layout = QVBoxLayout(surface)
        layout.setSpacing(10)
        layout.addWidget(self._build_section_title("System Status"))
        layout.addWidget(
            self._build_helper_label("Monitor bot runtime and Telegram connectivity.")
        )

        status_layout = QFormLayout()
        status_layout.addRow("Bot state", self.bot_state_label)
        status_layout.addRow("Telegram", self.connection_state_label)
        status_layout.addRow("Last successful raid", self.last_successful_label)
        layout.addLayout(status_layout)
        return panel

    def _build_metric_card(self, title: str, value_label: QLabel) -> QFrame:
        card = QFrame()
        card.setObjectName(CARD_OBJECT_NAME)
        layout = QVBoxLayout(card)
        layout.setSpacing(6)
        title_label = QLabel(title)
        title_label.setProperty("muted", "true")
        layout.addWidget(title_label)
        layout.addWidget(value_label)
        layout.addStretch()
        return card

    def _build_activity_panel(self) -> QWidget:
        panel, surface = self._build_panel("activityPanel")
        layout = QVBoxLayout(surface)
        layout.setSpacing(10)
        layout.addWidget(self._build_section_title("Recent Activity"))
        layout.addWidget(
            self._build_helper_label(
                "New raid actions appear here as the bot processes messages."
            )
        )
        layout.addWidget(self.activity_list)
        return panel

    def _build_error_panel(self) -> QWidget:
        panel, surface = self._build_panel("errorPanel")
        layout = QVBoxLayout(surface)
        layout.setSpacing(10)
        layout.addWidget(self._build_section_title("Last Error"))
        layout.addWidget(
            self._build_helper_label("If something breaks, the latest issue is pinned here.")
        )
        layout.addWidget(self.last_error_label)
        return panel

    def _build_compact_status_block(
        self, title: str, value_label: QLabel, object_name: str
    ) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(2)
        layout.setContentsMargins(0, 0, 0, 0)
        title_label = QLabel(title)
        title_label.setProperty("muted", "true")
        value_label.setObjectName(object_name)
        layout.addWidget(title_label)
        layout.addWidget(value_label)
        return container

    def _build_panel(self, object_name: str) -> tuple[QWidget, QWidget]:
        panel = QWidget()
        panel.setObjectName(object_name)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)

        surface = QWidget()
        surface.setObjectName(SECTION_OBJECT_NAME)
        panel_layout.addWidget(surface)
        return panel, surface

    def _build_section_title(self, text: str) -> QLabel:
        label = QLabel(text)
        return label

    def _build_helper_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setWordWrap(True)
        label.setProperty("muted", "true")
        return label

    def _connect_controller_signals(self) -> None:
        self.controller.botStateChanged.connect(self._update_bot_state)
        self.controller.connectionStateChanged.connect(self._update_connection_state)
        self.controller.statsChanged.connect(self._apply_stats_state)
        self.controller.activityAdded.connect(self._append_activity_entry)
        self.controller.errorRaised.connect(self.last_error_label.setText)
        self.controller.errorRaised.connect(self.automation_page.show_error)
        self.controller.configChanged.connect(self._sync_automation_config)
        self.controller.automationSequencesChanged.connect(
            self.automation_page.set_sequences
        )
        self.controller.automationRunEvent.connect(self.automation_page.handle_run_event)
        self.controller.automationRunStateChanged.connect(
            self.automation_page.set_run_state
        )
        self.controller.automationQueueStateChanged.connect(
            self.automation_page.set_queue_state
        )
        self.controller.automationQueueLengthChanged.connect(
            self.automation_page.set_queue_length
        )
        self.controller.automationCurrentUrlChanged.connect(
            self.automation_page.set_current_url
        )

    def _update_bot_state(self, state: str) -> None:
        self.bot_state = state
        self.bot_state_label.setText(state)
        self.command_bot_state_label.setText(state)

    def _update_connection_state(self, state: str) -> None:
        self.connection_state = state
        self.connection_state_label.setText(state)
        self.command_connection_state_label.setText(state)

    def _apply_state(
        self, state: DesktopAppState, *, include_activity: bool = False
    ) -> None:
        self._update_bot_state(state.bot_state.value)
        self._update_connection_state(state.connection_state.value)
        self.raids_opened_label.setText(str(state.raids_opened))
        self.duplicates_label.setText(str(state.duplicates_skipped))
        self.non_matching_label.setText(str(state.non_matching_skipped))
        self.open_failures_label.setText(str(state.open_failures))
        self.sender_rejected_label.setText(str(state.sender_rejected))
        self.browser_session_failed_label.setText(str(state.browser_session_failed))
        self.page_ready_label.setText(str(state.page_ready))
        self.executor_not_configured_label.setText(str(state.executor_not_configured))
        self.executor_succeeded_label.setText(str(state.executor_succeeded))
        self.executor_failed_label.setText(str(state.executor_failed))
        self.session_closed_label.setText(str(state.session_closed))
        self.last_successful_label.setText(state.last_successful_raid_open_at or "")
        self.last_error_label.setText(state.last_error or "")
        if include_activity:
            self.activity_list.clear()
            for entry in state.activity:
                self.activity_list.addItem(self._format_activity(entry))

    def _apply_stats_state(self, state: DesktopAppState) -> None:
        self._apply_state(state, include_activity=False)

    def _append_activity_entry(self, entry) -> None:
        self.activity_list.addItem(self._format_activity(entry))

    def _format_activity(self, entry) -> str:
        timestamp = entry.timestamp
        if isinstance(timestamp, datetime):
            timestamp_text = timestamp.isoformat()
        else:
            timestamp_text = str(timestamp)
        parts = [timestamp_text, self._format_activity_action(entry.action)]
        if entry.url:
            parts.append(entry.url)
        if entry.reason:
            parts.append(entry.reason)
        return " | ".join(parts)

    def _format_activity_action(self, action: str) -> str:
        action_labels = {
            "sender_rejected": "Sender Rejected",
            "browser_session_failed": "Browser Session Failed",
            "page_ready": "Page Ready",
            "executor_not_configured": "Executor Not Configured",
            "executor_succeeded": "Executor Succeeded",
            "executor_failed": "Executor Failed",
            "session_closed": "Session Closed",
        }
        if action in action_labels:
            return action_labels[action]
        return action.replace("_", " ").title()

    def _ensure_window_icon(self) -> None:
        if not self.windowIcon().isNull():
            return
        icon = self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        if not icon.isNull():
            self.setWindowIcon(icon)

    def handle_minimize_requested(self) -> None:
        self.hide()

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if self.isMinimized():
            self.handle_minimize_requested()
            self.setWindowState(Qt.WindowState.WindowNoState)

    def closeEvent(self, event) -> None:
        if not self._should_wait_for_shutdown():
            event.accept()
            return

        if not self.confirm_close():
            event.ignore()
            return

        if self.controller.stop_bot_and_wait():
            event.accept()
            return
        event.ignore()

    def _should_wait_for_shutdown(self) -> bool:
        if hasattr(self.controller, "is_bot_active"):
            return bool(self.controller.is_bot_active())
        return self.bot_state in {"starting", "running", "stopping"}

    def _confirm_close(self) -> bool:
        return (
            QMessageBox.question(
                self,
                "Stop bot and exit",
                "The bot is still running. Stop it and close the app?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            == QMessageBox.StandardButton.Yes
        )

    def _load_available_profiles(self) -> list[str]:
        try:
            environment = detect_chrome_environment()
        except Exception:
            return [self.controller.config.chrome_profile_directory]
        profiles = [profile.directory_name for profile in environment.profiles]
        if self.controller.config.chrome_profile_directory not in profiles:
            profiles.append(self.controller.config.chrome_profile_directory)
        return profiles

    def _load_session_status(self) -> str:
        try:
            service = TelegramSetupService(
                api_id=self.controller.config.telegram_api_id,
                api_hash=self.controller.config.telegram_api_hash,
                session_path=self.controller.config.telegram_session_path,
            )
            status = asyncio.run(
                asyncio.wait_for(service.get_session_status(), timeout=1.0)
            )
        except Exception:
            return "unknown"
        return getattr(status, "value", str(status))

    def _load_automation_sequences(self) -> list[object]:
        if hasattr(self.controller, "list_automation_sequences"):
            return self.controller.list_automation_sequences()
        return []

    def _load_automation_windows(self) -> list[object]:
        if hasattr(self.controller, "list_target_windows"):
            return self.controller.list_target_windows()
        return []

    def _refresh_automation_windows(self) -> None:
        self.automation_page.refresh_windows(self._load_automation_windows())

    def _sync_automation_config(self, config) -> None:
        self.automation_page.set_auto_run_config(
            config.auto_run_enabled,
            config.default_auto_sequence_id,
            config.auto_run_settle_ms,
        )

    def _sync_automation_queue_state(self, state: DesktopAppState) -> None:
        self.automation_page.set_queue_state(state.automation_queue_state)
        self.automation_page.set_queue_length(state.automation_queue_length)
        self.automation_page.set_current_url(state.automation_current_url)
