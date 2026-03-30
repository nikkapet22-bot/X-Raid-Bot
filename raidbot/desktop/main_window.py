from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import (
    QFrame,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
    QStyle,
)

from raidbot.desktop.bot_actions import BotActionsPage
from raidbot.desktop.bot_actions.capture import SlotCaptureService
from raidbot.desktop.bot_actions.presets_dialog import Slot1PresetsDialog
from raidbot.desktop.chrome_profiles import ChromeProfile, detect_chrome_environment
from raidbot.desktop.models import DesktopAppState, RaidProfileState
from raidbot.desktop.settings_page import SettingsPage
from raidbot.desktop.telegram_setup import TelegramSetupService
from raidbot.desktop.theme import (
    CARD_OBJECT_NAME,
    SECTION_OBJECT_NAME,
    NAV_SIDEBAR_WIDTH,
    ACCENT,
    SUCCESS,
    WARNING,
    ERROR,
    MUTED,
    TEXT,
)
from raidbot.desktop.tray import TrayController


# ── Helpers ───────────────────────────────────────────────────────────────────

def _bot_state_variant(state: str) -> str:
    if state == "running":
        return "running"
    if state in {"starting", "stopping"}:
        return "active"
    if state == "error":
        return "error"
    return "neutral"


def _connection_state_variant(state: str) -> str:
    if state == "connected":
        return "running"
    if state in {"connecting", "reconnecting"}:
        return "active"
    if state == "auth_required":
        return "error"
    return "neutral"


def _apply_variant(label: QLabel, variant: str) -> None:
    label.setProperty("stateVariant", variant)
    label.style().unpolish(label)
    label.style().polish(label)


# ── Profile card ──────────────────────────────────────────────────────────────

class RaidProfileCard(QFrame):
    restartRequested = Signal(str)

    def __init__(self, profile_directory: str, *, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.profile_directory = profile_directory
        self._details_visible = False
        self.setObjectName(CARD_OBJECT_NAME)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumWidth(140)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(14, 14, 14, 14)

        header_row = QHBoxLayout()
        header_row.setSpacing(8)
        header_row.setContentsMargins(0, 0, 0, 0)
        self.dot_label = QLabel()
        self.dot_label.setObjectName("statusDot")
        self.dot_label.setFixedSize(10, 10)
        self.title_label = QLabel(profile_directory)
        self.title_label.setObjectName("sectionTitle")
        header_row.addWidget(self.dot_label, 0, Qt.AlignmentFlag.AlignVCenter)
        header_row.addWidget(self.title_label, 1)
        layout.addLayout(header_row)

        self.status_label = QLabel("")
        self.status_label.setProperty("muted", "true")
        self.reason_label = QLabel("")
        self.reason_label.setWordWrap(True)
        self.reason_label.setProperty("muted", "true")
        self.reason_label.hide()

        self.restart_button = QPushButton("Restart")
        self.restart_button.setProperty("variant", "secondary")
        self.restart_button.clicked.connect(
            lambda: self.restartRequested.emit(self.profile_directory)
        )

        layout.addWidget(self.status_label)
        layout.addWidget(self.reason_label)
        layout.addWidget(self.restart_button)
        layout.addStretch()

    def apply_state(self, state: RaidProfileState) -> None:
        self.profile_directory = state.profile_directory
        self.title_label.setText(state.label)
        is_error = state.status == "red"
        profile_status = "red" if is_error else "green"

        self.setProperty("profileStatus", profile_status)
        self.style().unpolish(self)
        self.style().polish(self)

        dot_variant = "error" if is_error else "running"
        _apply_variant(self.dot_label, dot_variant)

        self.status_label.setText("Needs attention" if is_error else "Healthy")
        self.reason_label.setText(state.last_error or "No details available")
        if not is_error:
            self._details_visible = False
        self.reason_label.setVisible(is_error and self._details_visible)
        self.restart_button.setVisible(is_error)

    def mousePressEvent(self, event) -> None:
        if self.property("profileStatus") == "red":
            self._details_visible = not self._details_visible
            self.reason_label.setVisible(self._details_visible)
        super().mousePressEvent(event)


# ── Sidebar ───────────────────────────────────────────────────────────────────

class ActivityBadge(QWidget):
    _HEIGHT = 24
    _H_PADDING = 10
    _TONE_STYLES = {
        "accent": ("#1d4aa6", "#3167d7", "#b7d4ff"),
        "success": ("#0f5a4d", "#1f8d79", "#7ff0de"),
        "warning": ("#7b3b08", "#c86518", "#ffc68f"),
        "error": ("#7a1f25", "#ca4c55", "#ffb4b9"),
    }

    def __init__(self, text: str, tone: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._text = text
        self._tone = tone
        self.setObjectName("activityBadge")
        font = QFont(self.font())
        font.setBold(True)
        self.setFont(font)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(self._HEIGHT)

    def sizeHint(self) -> QSize:
        metrics = QFontMetrics(self.font())
        return QSize(
            metrics.horizontalAdvance(self._text) + (self._H_PADDING * 2),
            self._HEIGHT,
        )

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        fill, border, text = self._TONE_STYLES.get(
            self._tone,
            self._TONE_STYLES["accent"],
        )
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pill_rect = self.rect().adjusted(0, 0, -1, -1)
        radius = pill_rect.height() / 2
        painter.setPen(QPen(QColor(border), 1))
        painter.setBrush(QColor(fill))
        painter.drawRoundedRect(pill_rect, radius, radius)
        painter.setPen(QColor(text))
        painter.setFont(self.font())
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._text)
        painter.end()


class ActivityFeedRow(QFrame):
    def __init__(
        self,
        *,
        title: str,
        tone: str,
        timestamp_text: str,
        url: str | None,
        reason: str | None,
    ) -> None:
        super().__init__()
        self.setObjectName("activityCard")
        self.setProperty("activityTone", tone)
        self.setMinimumHeight(34)

        layout = QHBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 5, 10, 5)

        time_label = QLabel(timestamp_text)
        time_label.setObjectName("activityTime")
        time_label.setFixedWidth(54)
        layout.addWidget(time_label, 0, Qt.AlignmentFlag.AlignVCenter)

        badge_label = ActivityBadge(title, tone)
        layout.addWidget(badge_label, 0, Qt.AlignmentFlag.AlignVCenter)

        url_label = QLabel(self._truncate_middle(url or "—", 34))
        url_label.setObjectName("activityUrl")
        url_label.setToolTip(url or "")
        layout.addWidget(url_label, 1, Qt.AlignmentFlag.AlignVCenter)

        reason_label = QLabel(self._truncate_middle(reason or "—", 20))
        reason_label.setObjectName("activityReason")
        reason_label.setToolTip(reason or "")
        reason_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        reason_label.setFixedWidth(116)
        layout.addWidget(reason_label, 0, Qt.AlignmentFlag.AlignVCenter)

    def _truncate_middle(self, text: str, max_length: int) -> str:
        if len(text) <= max_length:
            return text
        keep = max(4, (max_length - 1) // 2)
        return f"{text[:keep]}…{text[-keep:]}"


class SidebarNav(QWidget):
    pageRequested = Signal(int)

    _NAV_ITEMS = [
        ("  Dashboard",   0),
        ("  Settings",    1),
        ("  Bot Actions", 2),
    ]

    def __init__(self, *, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(NAV_SIDEBAR_WIDTH)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 20, 12, 20)
        layout.setSpacing(4)

        # App identity block
        brand = QWidget()
        brand_layout = QVBoxLayout(brand)
        brand_layout.setContentsMargins(8, 0, 0, 0)
        brand_layout.setSpacing(2)
        name_label = QLabel("RAID BOT")
        name_label.setObjectName("appName")
        tag_label = QLabel("Automation Console")
        tag_label.setProperty("muted", "true")
        brand_layout.addWidget(name_label)
        brand_layout.addWidget(tag_label)
        layout.addWidget(brand)

        # Divider
        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setStyleSheet("background: #1e3252; max-height: 1px; border: none; margin: 10px 0;")
        layout.addWidget(div)

        self._buttons: list[QPushButton] = []
        for label, index in self._NAV_ITEMS:
            btn = QPushButton(label)
            btn.setObjectName("navButton")
            btn.clicked.connect(lambda _, i=index: self._activate(i))
            layout.addWidget(btn)
            self._buttons.append(btn)

        layout.addStretch()

        # Version tag at bottom
        ver = QLabel("v1.0")
        ver.setProperty("muted", "true")
        ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(ver)

        self._activate(0)

    def _activate(self, index: int) -> None:
        for i, btn in enumerate(self._buttons):
            btn.setProperty("active", "true" if i == index else "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        self.pageRequested.emit(index)

    def set_active_page(self, index: int) -> None:
        self._activate(index)


# ── Main window ───────────────────────────────────────────────────────────────

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
        slot_capture_service=None,
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
        self.slot_capture_service = slot_capture_service or SlotCaptureService(
            base_dir=getattr(self.storage, "base_dir", Path(".")),
        )
        self.bot_state = "stopped"
        self.connection_state = "disconnected"
        self._bot_actions_status_text = "Idle"
        self._bot_actions_current_slot_text: str | None = None
        self._bot_actions_last_error_text: str | None = None
        self._bot_actions_run_slots_snapshot: tuple[tuple[int, str], ...] = ()
        self._slot_1_presets_dialog: Slot1PresetsDialog | None = None
        self._latest_state = DesktopAppState()
        self.raid_profile_cards: dict[str, RaidProfileCard] = {}
        self._restore_geometry: QRect | None = None
        self._restore_was_maximized = False

        self.setWindowTitle("Raid Bot")
        self.setMinimumSize(960, 640)

        # ── Labels ────────────────────────────────────────────────────────────
        self.bot_state_label = QLabel("")
        self.connection_state_label = QLabel("")
        self.command_bot_state_label = QLabel("")
        self.command_connection_state_label = QLabel("")
        self.raids_detected_label = QLabel("0")
        self.raids_opened_label = QLabel("0")
        self.raids_completed_label = QLabel("0")
        self.raids_failed_label = QLabel("0")
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
        self.activity_list.setObjectName("activityList")
        self.activity_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.activity_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        # ── Dot indicators for command row ────────────────────────────────────
        self._bot_dot = QLabel()
        self._bot_dot.setObjectName("statusDot")
        self._bot_dot.setFixedSize(9, 9)
        self._conn_dot = QLabel()
        self._conn_dot.setObjectName("statusDot")
        self._conn_dot.setFixedSize(9, 9)

        # ── Buttons ────────────────────────────────────────────────────────────
        self.start_button = QPushButton("  Start")
        self.stop_button = QPushButton("  Stop")
        self.start_button.setProperty("variant", "primary")
        self.stop_button.setProperty("variant", "danger")
        self.start_button.setMinimumWidth(100)
        self.stop_button.setMinimumWidth(100)
        self.start_button.clicked.connect(self.controller.start_bot)
        self.stop_button.clicked.connect(self.controller.stop_bot)

        # ── Layout ─────────────────────────────────────────────────────────────
        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.sidebar = SidebarNav()
        root.addWidget(self.sidebar)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._wrap_page(self._build_dashboard_tab()))
        self.settings_page = SettingsPage(
            config=self.controller.config,
            available_profiles=self.available_profiles_loader(),
            session_status=self.session_status_loader(),
            reauthorize_available=hasattr(self.controller, "reauthorize_session"),
        )
        self.settings_page.applyRequested.connect(self._apply_settings_config)
        self.settings_page.raidProfileAddRequested.connect(self.controller.add_raid_profile)
        self.settings_page.raidProfileRemoveRequested.connect(
            self.controller.remove_raid_profile
        )
        self.settings_page.raidProfileMoveRequested.connect(self.controller.move_raid_profile)
        if hasattr(self.controller, "reauthorize_session"):
            self.settings_page.reauthorizeRequested.connect(
                self.controller.reauthorize_session
            )
        self.stack.addWidget(self._wrap_page(self.settings_page))

        self.bot_actions_page = BotActionsPage(config=self.controller.config)
        self.bot_actions_page.pageReadyCaptureRequested.connect(
            self._capture_page_ready_template
        )
        self.bot_actions_page.slotCaptureRequested.connect(self._capture_bot_action_slot)
        self.bot_actions_page.slotTestRequested.connect(self.controller.test_bot_action_slot)
        self.bot_actions_page.slotPresetsRequested.connect(self._open_bot_action_slot_presets)
        self.bot_actions_page.slotEnabledChanged.connect(
            self.controller.set_bot_action_slot_enabled
        )
        self.bot_actions_page.settleDelayChanged.connect(
            self.controller.set_auto_run_settle_ms
        )
        self.stack.addWidget(self._wrap_page(self.bot_actions_page))

        self.sidebar.pageRequested.connect(self.stack.setCurrentIndex)
        root.addWidget(self.stack, 1)

        # Keep self.tabs alias for any external code that references it
        self.tabs = self.stack

        self.setCentralWidget(central)
        self._connect_controller_signals()
        state = self.storage.load_state()
        self._apply_state(state, include_activity=True)
        self._sync_config(self.controller.config)
        self._render_bot_actions_status()
        self._ensure_window_icon()
        self.tray_controller = tray_controller_factory(
            window=self,
            controller=self.controller,
            icon=self.windowIcon(),
            initial_bot_state=self.bot_state,
        )

    # ── Page builders ─────────────────────────────────────────────────────────

    def _build_dashboard_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(14)
        layout.setContentsMargins(24, 24, 24, 24)

        page_title = QLabel("Dashboard")
        page_title.setObjectName("pageTitle")
        layout.addWidget(page_title)

        self.command_status_row = self._build_command_status_row()
        layout.addWidget(self.command_status_row)

        self.status_panel = self._build_status_panel()
        layout.addWidget(self.status_panel)

        self.profiles_panel = self._build_profiles_panel()
        layout.addWidget(self.profiles_panel)

        self.metric_cards = [
            self._build_metric_card("Raids Detected",         self.raids_detected_label),
            self._build_metric_card("Raids Opened",           self.raids_opened_label),
            self._build_metric_card("Raids Completed",        self.raids_completed_label),
            self._build_metric_card("Raids Failed",           self.raids_failed_label),
        ]
        metrics_row = QHBoxLayout()
        metrics_row.setSpacing(10)
        for card in self.metric_cards:
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
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)
        layout.addWidget(self.start_button)
        layout.addWidget(self.stop_button)
        layout.addStretch()
        layout.addWidget(
            self._build_compact_status_block(
                "Bot", self.command_bot_state_label, "commandBotStateLabel",
                dot=self._bot_dot,
            )
        )
        self._add_vertical_separator(layout)
        layout.addWidget(
            self._build_compact_status_block(
                "Telegram", self.command_connection_state_label,
                "commandConnectionStateLabel",
                dot=self._conn_dot,
            )
        )
        return row

    def _add_vertical_separator(self, layout: QHBoxLayout) -> None:
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet("background: #1e3252; max-width: 1px; border: none; margin: 6px 4px;")
        layout.addWidget(sep)

    def _build_status_panel(self) -> QWidget:
        panel, surface = self._build_panel("statusPanel")
        layout = QVBoxLayout(surface)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.addWidget(self._build_section_title("System Status"))
        layout.addWidget(self._build_divider())
        layout.addWidget(
            self._build_helper_label("Monitor bot runtime and Telegram connectivity.")
        )
        status_layout = QFormLayout()
        status_layout.setVerticalSpacing(10)
        status_layout.setHorizontalSpacing(24)
        status_layout.addRow("Bot state", self.bot_state_label)
        status_layout.addRow("Telegram", self.connection_state_label)
        status_layout.addRow("Last successful raid", self.last_successful_label)
        layout.addLayout(status_layout)
        return panel

    def _build_profiles_panel(self) -> QWidget:
        panel, surface = self._build_panel("profilesPanel")
        layout = QVBoxLayout(surface)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.addWidget(self._build_section_title("Profiles"))
        layout.addWidget(self._build_divider())
        layout.addWidget(
            self._build_helper_label(
                "Healthy profiles stay green. Failed profiles turn red until restarted."
            )
        )
        self.profile_cards_layout = QHBoxLayout()
        self.profile_cards_layout.setSpacing(12)
        layout.addLayout(self.profile_cards_layout)
        return panel

    def _build_metric_card(self, title: str, value_label: QLabel) -> QFrame:
        card = QFrame()
        card.setObjectName(CARD_OBJECT_NAME)
        layout = QVBoxLayout(card)
        layout.setSpacing(4)
        layout.setContentsMargins(14, 14, 14, 14)
        title_label = QLabel(title)
        title_label.setObjectName("metricTitle")
        value_label.setObjectName("metricValue")
        layout.addWidget(title_label)
        layout.addWidget(value_label)
        layout.addStretch()
        return card

    def _build_activity_panel(self) -> QWidget:
        panel, surface = self._build_panel("activityPanel")
        layout = QVBoxLayout(surface)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.addWidget(self._build_section_title("Recent Activity"))
        layout.addWidget(self._build_divider())
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
        layout.setSpacing(12)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.addWidget(self._build_section_title("Last Error"))
        layout.addWidget(self._build_divider())
        layout.addWidget(
            self._build_helper_label("If something breaks, the latest issue is pinned here.")
        )
        layout.addWidget(self.last_error_label)
        return panel

    def _build_compact_status_block(
        self,
        title: str,
        value_label: QLabel,
        object_name: str,
        *,
        dot: QLabel | None = None,
    ) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(3)
        layout.setContentsMargins(8, 0, 8, 0)
        title_label = QLabel(title)
        title_label.setProperty("muted", "true")
        value_label.setObjectName(object_name)
        val_row = QHBoxLayout()
        val_row.setSpacing(6)
        val_row.setContentsMargins(0, 0, 0, 0)
        if dot is not None:
            _apply_variant(dot, "neutral")
            val_row.addWidget(dot, 0, Qt.AlignmentFlag.AlignVCenter)
        val_row.addWidget(value_label)
        layout.addWidget(title_label)
        layout.addLayout(val_row)
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

    def _wrap_page(self, widget: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(widget)
        return scroll

    # keep old name used elsewhere
    def _wrap_tab_content(self, widget: QWidget) -> QScrollArea:
        return self._wrap_page(widget)

    def _build_section_title(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("sectionTitle")
        return label

    def _build_helper_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setWordWrap(True)
        label.setProperty("muted", "true")
        return label

    def _build_divider(self) -> QFrame:
        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setStyleSheet("background: #1e3252; max-height: 1px; border: none;")
        return div

    # ── Controller signals ────────────────────────────────────────────────────

    def _connect_controller_signals(self) -> None:
        self.controller.botStateChanged.connect(self._update_bot_state)
        self.controller.connectionStateChanged.connect(self._update_connection_state)
        self.controller.statsChanged.connect(self._apply_stats_state)
        self.controller.activityAdded.connect(self._append_activity_entry)
        self.controller.errorRaised.connect(self.last_error_label.setText)
        self.controller.errorRaised.connect(self._show_bot_actions_error)
        self.controller.configChanged.connect(self._sync_config)
        self.controller.automationQueueStateChanged.connect(
            self._update_bot_actions_queue_state
        )
        self.controller.botActionRunEvent.connect(self._handle_bot_actions_run_event)

    def _update_bot_state(self, state: str) -> None:
        self.bot_state = state
        variant = _bot_state_variant(state)
        for label in (self.bot_state_label, self.command_bot_state_label):
            label.setText(state)
            _apply_variant(label, variant)
        _apply_variant(self._bot_dot, variant)

    def _update_connection_state(self, state: str) -> None:
        self.connection_state = state
        variant = _connection_state_variant(state)
        for label in (self.connection_state_label, self.command_connection_state_label):
            label.setText(state)
            _apply_variant(label, variant)
        _apply_variant(self._conn_dot, variant)

    def _apply_state(
        self, state: DesktopAppState, *, include_activity: bool = False
    ) -> None:
        self._latest_state = state
        self._update_bot_state(state.bot_state.value)
        self._update_connection_state(state.connection_state.value)
        self.raids_detected_label.setText(str(state.raids_detected))
        self.raids_opened_label.setText(str(state.raids_opened))
        self.raids_completed_label.setText(str(state.raids_completed))
        self.raids_failed_label.setText(str(state.raids_failed))
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
        self._sync_raid_profile_cards(self.controller.config, state)
        if include_activity:
            self._populate_activity_list(state.activity)

    def _apply_stats_state(self, state: DesktopAppState) -> None:
        self._apply_state(state, include_activity=False)

    def _append_activity_entry(self, entry) -> None:
        if not self._should_display_activity(entry.action):
            return
        self._insert_activity_entry(entry, at_top=True)

    def _format_activity(self, entry) -> str:
        timestamp = entry.timestamp
        timestamp_text = (
            timestamp.isoformat() if isinstance(timestamp, datetime) else str(timestamp)
        )
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
        return action_labels.get(action, action.replace("_", " ").title())

    def _activity_tone(self, action: str) -> str:
        if action in {"automation_failed", "browser_session_failed", "executor_failed"}:
            return "error"
        if action in {"sender_rejected", "duplicate", "auto_queued"}:
            return "warning"
        if action in {"automation_succeeded", "executor_succeeded", "session_closed"}:
            return "success"
        return "accent"

    def _activity_badge(self, action: str) -> str:
        labels = {
            "raid_detected": "DETECTED",
            "auto_queued": "QUEUED",
            "automation_started": "RUNNING",
            "automation_succeeded": "DONE",
            "automation_failed": "FAILED",
            "browser_session_failed": "FAILED",
            "page_ready": "READY",
            "session_closed": "CLOSED",
            "sender_rejected": "REJECTED",
            "executor_failed": "ERROR",
            "executor_succeeded": "DONE",
        }
        return labels.get(action, action.replace("_", " ").upper())

    def _populate_activity_list(self, entries) -> None:
        self.activity_list.clear()
        for entry in reversed(entries):
            if not self._should_display_activity(entry.action):
                continue
            self._insert_activity_entry(entry, at_top=False)

    def _should_display_activity(self, action: str) -> bool:
        return action not in {"duplicate", "sender_rejected"}

    def _insert_activity_entry(self, entry, *, at_top: bool) -> None:
        tone = self._activity_tone(entry.action)
        list_item = QListWidgetItem(self._format_activity(entry))
        row_widget = ActivityFeedRow(
            title=self._format_activity_action(entry.action),
            tone=tone,
            timestamp_text=self._format_activity_timestamp(entry.timestamp),
            url=getattr(entry, "url", None),
            reason=getattr(entry, "reason", None),
        )
        list_item.setSizeHint(row_widget.sizeHint())
        if at_top:
            self.activity_list.insertItem(0, list_item)
        else:
            self.activity_list.addItem(list_item)
        self.activity_list.setItemWidget(list_item, row_widget)

    def _format_activity_timestamp(self, timestamp: object) -> str:
        if isinstance(timestamp, datetime):
            return timestamp.strftime("%H:%M:%S")
        return str(timestamp)

    def _ensure_window_icon(self) -> None:
        if not self.windowIcon().isNull():
            return
        icon = self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        if not icon.isNull():
            self.setWindowIcon(icon)

    def handle_minimize_requested(self) -> None:
        self.hide()

    def restore_from_tray(self) -> None:
        restore_was_maximized = self._restore_was_maximized
        restore_geometry = (
            QRect(self._restore_geometry)
            if self._restore_geometry is not None and not self._restore_geometry.isNull()
            else None
        )
        if restore_was_maximized:
            self.show()
            self.showMaximized()
        else:
            self.show()
            self.showNormal()
            if restore_geometry is not None:
                self.setGeometry(restore_geometry)
        self.raise_()
        self.activateWindow()

    def _remember_restore_geometry(self) -> None:
        normal_geometry = self.normalGeometry()
        self._restore_geometry = (
            QRect(normal_geometry)
            if not normal_geometry.isNull()
            else (QRect(self.geometry()) if not self.geometry().isNull() else None)
        )
        self._restore_was_maximized = self.isMaximized()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._remember_restore_geometry()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if not self.isMinimized():
            self._remember_restore_geometry()

    def moveEvent(self, event) -> None:
        super().moveEvent(event)
        if not self.isMinimized():
            self._remember_restore_geometry()

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if self.isMinimized():
            self._remember_restore_geometry()
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

    def _load_available_profiles(self) -> list[ChromeProfile]:
        try:
            environment = detect_chrome_environment()
        except Exception:
            return [
                ChromeProfile(
                    directory_name=profile.profile_directory,
                    label=profile.label,
                )
                for profile in self.controller.config.raid_profiles
            ]
        profiles = list(environment.profiles)
        known_directories = {profile.directory_name for profile in profiles}
        for configured_profile in self.controller.config.raid_profiles:
            if configured_profile.profile_directory in known_directories:
                continue
            profiles.append(
                ChromeProfile(
                    directory_name=configured_profile.profile_directory,
                    label=configured_profile.label,
                )
            )
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

    def _apply_settings_config(self, config) -> None:
        try:
            self.controller.apply_config(config)
        except Exception as exc:
            self.settings_page.show_error(str(exc))
            return
        self.settings_page.show_success("Settings saved.")

    def _capture_bot_action_slot(self, slot_index: int) -> None:
        slot = self.controller.config.bot_action_slots[slot_index]
        try:
            template_path = self.slot_capture_service.capture_slot(
                slot, existing_path=slot.template_path,
            )
            self.controller.set_bot_action_slot_template_path(slot_index, template_path)
            if template_path is not None:
                self._bot_actions_status_text = (
                    f"{self._format_bot_action_slot(slot_index, slot.label)}: image saved"
                )
                self._bot_actions_last_error_text = None
                self._bot_actions_current_slot_text = None
                self._render_bot_actions_status()
        except Exception as exc:
            self._show_bot_actions_error(str(exc))

    def _capture_page_ready_template(self) -> None:
        try:
            template_path = self.slot_capture_service.capture_to_path(
                Path("bot_actions/page_ready.png"),
                existing_path=self.controller.config.page_ready_template_path,
            )
            self.controller.set_page_ready_template_path(template_path)
            if template_path is not None:
                self._bot_actions_status_text = "Page Ready: image saved"
                self._bot_actions_last_error_text = None
                self._bot_actions_current_slot_text = None
                self._render_bot_actions_status()
        except Exception as exc:
            self._show_bot_actions_error(str(exc))

    def _open_bot_action_slot_presets(self, slot_index: int) -> None:
        if slot_index != 0:
            return
        slot = self.controller.config.bot_action_slots[0]
        dialog = Slot1PresetsDialog(slot=slot, parent=self)
        dialog.capture_finish_button.clicked.connect(self._capture_slot_1_finish_template)
        try:
            dialog.button_box.accepted.disconnect(dialog.accept)
        except (RuntimeError, TypeError):
            pass
        dialog.button_box.accepted.connect(self._save_slot_1_presets_dialog)
        dialog.finished.connect(self._clear_slot_1_presets_dialog)
        self._slot_1_presets_dialog = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _capture_slot_1_finish_template(self) -> None:
        dialog = self._slot_1_presets_dialog
        if dialog is None:
            return
        try:
            finish_template_path = self.slot_capture_service.capture_to_path(
                Path("bot_actions/slot_1_r_finish.png"),
                existing_path=dialog.finish_template_path,
            )
            dialog.finish_template_path = finish_template_path
            dialog.finish_image_status_label.setText(
                str(finish_template_path)
                if finish_template_path is not None
                else "No finish image"
            )
            updated_slot = dialog.build_updated_slot()
            self.controller.set_bot_action_slot_1_presets(
                presets=updated_slot.presets,
                finish_template_path=updated_slot.finish_template_path,
            )
            if finish_template_path is not None:
                self._bot_actions_status_text = "Slot 1 (R): finish image saved"
                self._bot_actions_last_error_text = None
                self._bot_actions_current_slot_text = None
                self._render_bot_actions_status()
        except Exception as exc:
            self._show_bot_actions_error(str(exc))

    def _save_slot_1_presets_dialog(self) -> None:
        dialog = self._slot_1_presets_dialog
        if dialog is None:
            return
        try:
            updated_slot = dialog.build_updated_slot()
            self.controller.set_bot_action_slot_1_presets(
                presets=updated_slot.presets,
                finish_template_path=updated_slot.finish_template_path,
            )
            self._bot_actions_status_text = "Slot 1 (R): presets saved"
            self._bot_actions_last_error_text = None
            self._bot_actions_current_slot_text = None
            self._render_bot_actions_status()
            dialog.accept()
        except Exception as exc:
            self._show_bot_actions_error(str(exc))

    def _clear_slot_1_presets_dialog(self, _result: int) -> None:
        self._slot_1_presets_dialog = None

    def _sync_config(self, config) -> None:
        self.settings_page.set_config(config)
        self.bot_actions_page.set_page_ready_template_path(config.page_ready_template_path)
        self.bot_actions_page.set_slots(config.bot_action_slots)
        self.bot_actions_page.set_settle_delay(config.auto_run_settle_ms)
        self._sync_raid_profile_cards(config, self._latest_state)

    def _sync_raid_profile_cards(self, config, state: DesktopAppState) -> None:
        while self.profile_cards_layout.count():
            item = self.profile_cards_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        states_by_directory = {
            ps.profile_directory: ps
            for ps in getattr(state, "raid_profile_states", ())
        }
        self.raid_profile_cards = {}
        for profile in config.raid_profiles:
            card = RaidProfileCard(profile.profile_directory, parent=self)
            card.restartRequested.connect(self.controller.restart_raid_profile)
            card.apply_state(
                states_by_directory.get(
                    profile.profile_directory,
                    RaidProfileState(
                        profile_directory=profile.profile_directory,
                        label=profile.label,
                        status="green",
                        last_error=None,
                    ),
                )
            )
            self.profile_cards_layout.addWidget(card)
            self.raid_profile_cards[profile.profile_directory] = card
        self.profile_cards_layout.addStretch()

    def _show_bot_actions_error(self, message: str) -> None:
        self._bot_actions_last_error_text = str(message)
        self._render_bot_actions_status()

    def _update_bot_actions_queue_state(self, state: str) -> None:
        queue_status_map = {
            "queued": "Queued", "running": "Running",
            "paused": "Paused", "idle": "Idle",
        }
        self._bot_actions_status_text = queue_status_map.get(str(state), "Idle")
        if state == "idle":
            self._clear_bot_actions_run_snapshot()
        self._render_bot_actions_status()

    def _handle_bot_actions_run_event(self, event: dict[str, object]) -> None:
        event_type = str(event.get("type", ""))
        if event_type in {"slot_test_started", "slot_test_succeeded", "slot_test_failed"}:
            self._bot_actions_status_text = str(event.get("message", "Idle"))
            self._bot_actions_current_slot_text = None
            self._bot_actions_last_error_text = None
            self._clear_bot_actions_run_snapshot()
        elif event_type == "automation_run_started":
            self._bot_actions_status_text = "Running"
            self._bot_actions_current_slot_text = None
            self._snapshot_bot_actions_run_slots()
            self._bot_actions_last_error_text = None
        elif event_type == "automation_run_succeeded":
            self._bot_actions_status_text = "Idle"
            self._clear_bot_actions_run_snapshot()
            self._bot_actions_last_error_text = None
        elif event_type in {"automation_run_failed", "step_failed", "target_window_lost"}:
            self._bot_actions_status_text = "Idle"
            slot_text = self._bot_actions_slot_text(event.get("step_index"))
            if slot_text is not None:
                self._bot_actions_current_slot_text = slot_text
            self._clear_bot_actions_run_snapshot(clear_current_slot=False)
            reason = event.get("reason")
            if reason:
                self._bot_actions_last_error_text = str(reason)
        elif "step_index" in event:
            self._bot_actions_current_slot_text = self._bot_actions_slot_text(
                event.get("step_index")
            )
        self._render_bot_actions_status()

    def _snapshot_bot_actions_run_slots(self) -> None:
        slots = getattr(self.controller.config, "bot_action_slots", ())
        self._bot_actions_run_slots_snapshot = tuple(
            (slot_index + 1, str(slot.label))
            for slot_index, slot in enumerate(slots)
            if getattr(slot, "enabled", False)
        )

    def _clear_bot_actions_run_snapshot(self, *, clear_current_slot: bool = True) -> None:
        self._bot_actions_run_slots_snapshot = ()
        if clear_current_slot:
            self._bot_actions_current_slot_text = None

    def _bot_actions_slot_text(self, step_index: object) -> str | None:
        if not isinstance(step_index, int) or step_index < 0:
            return None
        if step_index >= len(self._bot_actions_run_slots_snapshot):
            return None
        slot_number, slot_label = self._bot_actions_run_slots_snapshot[step_index]
        return f"Slot {slot_number} ({slot_label})"

    def _format_bot_action_slot(self, slot_index: int, slot_label: str) -> str:
        return f"Slot {slot_index + 1} ({slot_label})"

    def _render_bot_actions_status(self) -> None:
        lines = [f"Status: {self._bot_actions_status_text}"]
        if self._bot_actions_current_slot_text:
            lines.append(f"Current slot: {self._bot_actions_current_slot_text}")
        if self._bot_actions_last_error_text:
            lines.append(f"Last error: {self._bot_actions_last_error_text}")
        self.bot_actions_page.status_label.setText("\n".join(lines))
        self.bot_actions_page.set_status_fields(
            latest_status=self._bot_actions_status_text,
            current_slot=self._bot_actions_current_slot_text,
            last_error=self._bot_actions_last_error_text,
        )

    def _bot_state_is_active(self, state: str) -> bool:
        return state in {"starting", "running", "stopping"}
