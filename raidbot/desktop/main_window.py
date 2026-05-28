from __future__ import annotations

import asyncio
import base64
import math
import mimetypes
import os
from collections import defaultdict, deque
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

from PySide6.QtCore import QDateTime, QMargins, QPointF, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtCharts import (
    QAreaSeries,
    QChart,
    QChartView,
    QDateTimeAxis,
    QLineSeries,
    QSplineSeries,
    QValueAxis,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QIcon,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPainterPathStroker,
    QPaintEvent,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from raidbot.desktop.bot_actions import BotActionsPage
from raidbot.desktop.bot_actions.capture import SlotCaptureService
from raidbot.desktop.bot_actions.presets_dialog import Slot1PresetsDialog
from raidbot.desktop.animated_button import AttentionPulseButton
from raidbot.desktop.assets import app_icon
from raidbot.desktop.branding import APP_NAME, APP_VERSION_BADGE
from raidbot.desktop.chrome_profiles import ChromeProfile, detect_chrome_environment
from raidbot.desktop.diagnostics import export_diagnostics
from raidbot.desktop.hotkeys import WindowsGlobalHotkeyRegistrar
from raidbot.desktop.models import (
    BotActionSlotConfig,
    DesktopAppState,
    RaidProfileConfig,
    RaidProfileState,
    SuccessfulProfileRun,
    raid_profile_action_specs,
    raid_profile_has_any_actions_enabled,
)
from raidbot.desktop.settings_page import SettingsPage
from raidbot.desktop.telegram_setup import AccessibleChat, TelegramSetupService
from raidbot.desktop.theme import (
    CARD_OBJECT_NAME,
    SECTION_OBJECT_NAME,
    ACCENT,
    ACCENT_HOVER,
    SUCCESS,
    WARNING,
    ERROR,
    MUTED,
    TEXT,
)
from raidbot.desktop.tray import TrayController
from raidbot.desktop.web_dashboard import DashboardWebView


RAID_ACTIVITY_MODE_CUMULATIVE = "cumulative"
RAID_ACTIVITY_MODE_PER_HOUR = "per_hour"
RAID_ACTIVITY_MODE_ROLLING_60M = "rolling_60m"
RAID_ACTIVITY_MODE_SMOOTHED_RATE = "smoothed_rate"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_profile_action_icon(size: int = 12, *, color: str = TEXT) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    font = QFont("Segoe UI Symbol")
    font.setPixelSize(max(8, int(size * 0.95)))
    painter.setFont(font)
    painter.setPen(QColor(color))
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "\u2699")
    painter.end()
    return QIcon(pixmap)


def _build_metric_reset_icon(size: int = 10, *, color: str = TEXT) -> QIcon:
    return _build_profile_reset_icon(size=size, color=color)


def _build_profile_reset_icon(size: int = 12, *, color: str = TEXT) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(QColor(color))
    pen.setWidthF(max(1.4, size * 0.12))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    arc_rect = QRectF(size * 0.18, size * 0.18, size * 0.54, size * 0.54)
    painter.drawArc(arc_rect, 35 * 16, 290 * 16)

    arrow_path = QPainterPath()
    arrow_tip = QPointF(size * 0.78, size * 0.24)
    arrow_path.moveTo(arrow_tip)
    arrow_path.lineTo(QPointF(size * 0.58, size * 0.24))
    arrow_path.lineTo(QPointF(size * 0.68, size * 0.40))
    arrow_path.closeSubpath()
    painter.fillPath(arrow_path, QColor(color))
    painter.end()
    return QIcon(pixmap)


def _build_shell_nav_icon(
    name: str,
    *,
    size: int = 22,
    color: str = MUTED,
) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(QColor(color))
    pen.setWidthF(max(1.4, size * 0.085))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    if name == "dashboard":
        gap = size * 0.13
        cell = size * 0.29
        left = size * 0.18
        top = size * 0.18
        for row in range(2):
            for column in range(2):
                painter.drawRect(
                    QRectF(
                        left + column * (cell + gap),
                        top + row * (cell + gap),
                        cell,
                        cell,
                    )
                )
    elif name == "settings":
        center = QPointF(size / 2, size / 2)
        outer = size * 0.34
        inner = size * 0.15
        painter.drawEllipse(center, inner, inner)
        for index in range(8):
            angle = (math.pi * 2 * index) / 8
            start = QPointF(
                center.x() + math.cos(angle) * (outer * 0.74),
                center.y() + math.sin(angle) * (outer * 0.74),
            )
            end = QPointF(
                center.x() + math.cos(angle) * outer,
                center.y() + math.sin(angle) * outer,
            )
            painter.drawLine(start, end)
    elif name == "bot_actions":
        center = QPointF(size / 2, size / 2)
        painter.drawEllipse(center, size * 0.19, size * 0.19)
        for index in range(8):
            angle = (math.pi * 2 * index) / 8
            start = QPointF(
                center.x() + math.cos(angle) * size * 0.30,
                center.y() + math.sin(angle) * size * 0.30,
            )
            end = QPointF(
                center.x() + math.cos(angle) * size * 0.42,
                center.y() + math.sin(angle) * size * 0.42,
            )
            painter.drawLine(start, end)
    elif name == "account":
        painter.drawEllipse(QPointF(size / 2, size * 0.34), size * 0.16, size * 0.16)
        painter.drawArc(
            QRectF(size * 0.23, size * 0.50, size * 0.54, size * 0.42),
            20 * 16,
            140 * 16,
        )
    else:
        path = QPainterPath()
        path.moveTo(size * 0.58, size * 0.08)
        path.lineTo(size * 0.23, size * 0.55)
        path.lineTo(size * 0.48, size * 0.55)
        path.lineTo(size * 0.38, size * 0.92)
        path.lineTo(size * 0.76, size * 0.42)
        path.lineTo(size * 0.51, size * 0.42)
        painter.drawPath(path)
    painter.end()
    return QIcon(pixmap)


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


def _format_status_caption(value: str) -> str:
    return value.replace("_", " ").title()


def _build_eased_cumulative_points(
    points: list[QPointF],
    *,
    samples_per_segment: int = 16,
) -> list[QPointF]:
    if not points:
        return []
    if len(points) == 1:
        return [QPointF(points[0])]
    sampled_points = [QPointF(points[0])]
    sample_count = max(2, samples_per_segment)
    for start, end in zip(points, points[1:]):
        dx = end.x() - start.x()
        for sample_index in range(1, sample_count + 1):
            t = sample_index / sample_count
            eased_t = t * t * (3.0 - (2.0 * t))
            sampled_points.append(
                QPointF(
                    start.x() + (dx * t),
                    start.y() + ((end.y() - start.y()) * eased_t),
                )
            )
    return sampled_points


def _build_eased_cumulative_path(points: list[QPointF]) -> QPainterPath:
    if not points:
        return QPainterPath()
    sampled_points = _build_eased_cumulative_points(points)
    path = QPainterPath(sampled_points[0])
    for point in sampled_points[1:]:
        path.lineTo(point)
    return path


def _smooth_hourly_activity_series(
    values: list[int],
    *,
    weights: tuple[int, ...] = (1, 2, 3, 4, 3, 2, 1),
) -> list[int]:
    if not values:
        return []
    radius = len(weights) // 2
    smoothed: list[int] = []
    for index in range(len(values)):
        total = 0.0
        total_weight = 0.0
        for offset, weight in enumerate(weights):
            source_index = index + offset - radius
            if 0 <= source_index < len(values):
                total += values[source_index] * weight
                total_weight += weight
        smoothed.append(int(round(total / total_weight)) if total_weight else 0)
    return smoothed


def _build_chart_area_path(
    sampled_points: list[QPointF],
    *,
    baseline_y: float,
) -> QPainterPath:
    if not sampled_points:
        return QPainterPath()
    area_path = QPainterPath(QPointF(sampled_points[0].x(), baseline_y))
    area_path.setFillRule(Qt.FillRule.WindingFill)
    for point in sampled_points:
        area_path.lineTo(point)
    area_path.lineTo(QPointF(sampled_points[-1].x(), baseline_y))
    area_path.closeSubpath()
    return area_path


def _build_chart_fill_band_path(
    line_path: QPainterPath,
    area_path: QPainterPath,
    *,
    band_width: float = 18.0,
) -> QPainterPath:
    stroker = QPainterPathStroker()
    stroker.setWidth(band_width)
    stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
    return stroker.createStroke(line_path).intersected(area_path)


def _render_line_relative_fill_image(
    size: QSize,
    sampled_points: list[QPointF],
    *,
    baseline_y: float,
    color: QColor,
    alpha: int = 28,
    band_alpha: int = 0,
    band_height: float = 0.0,
) -> QImage:
    image = QImage(size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    if not sampled_points or size.isEmpty():
        return image

    painter = QPainter(image)
    _paint_line_relative_fill(
        painter,
        sampled_points,
        baseline_y=baseline_y,
        color=color,
        alpha=alpha,
        band_alpha=band_alpha,
        band_height=band_height,
    )
    painter.end()
    return image


def _render_line_band_fill_image(
    size: QSize,
    sampled_points: list[QPointF],
    *,
    baseline_y: float,
    color: QColor,
    band_width: float = 12.0,
    alpha: int = 28,
) -> QImage:
    image = QImage(size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    if not sampled_points or size.isEmpty():
        return image

    line_path = QPainterPath(sampled_points[0])
    for point in sampled_points[1:]:
        line_path.lineTo(point)
    area_path = _build_chart_area_path(sampled_points, baseline_y=baseline_y)
    fill_band = _build_chart_fill_band_path(
        line_path,
        area_path,
        band_width=band_width,
    )

    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    fill_color = QColor(color)
    fill_color.setAlpha(alpha)
    painter.fillPath(fill_band, fill_color)
    painter.end()
    return image


def _render_line_shadow_image(
    size: QSize,
    sampled_points: list[QPointF],
    *,
    baseline_y: float,
    color: QColor,
    layers: tuple[tuple[float, int], ...] = (
        (24.0, 6),
        (18.0, 9),
        (12.0, 13),
        (8.0, 18),
        (5.0, 24),
    ),
) -> QImage:
    image = QImage(size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    if not sampled_points or size.isEmpty():
        return image

    line_path = QPainterPath(sampled_points[0])
    for point in sampled_points[1:]:
        line_path.lineTo(point)
    area_path = _build_chart_area_path(sampled_points, baseline_y=baseline_y)

    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    for band_width, alpha in layers:
        shadow_path = _build_chart_fill_band_path(
            line_path,
            area_path,
            band_width=band_width,
        )
        shadow_color = QColor(color)
        shadow_color.setAlpha(alpha)
        painter.fillPath(shadow_path, shadow_color)
    painter.end()
    return image


def _render_line_glow_image(
    size: QSize,
    sampled_points: list[QPointF],
    *,
    color: QColor,
    layers: tuple[tuple[float, int], ...] = (
        (8.0, 8),
        (5.0, 14),
        (3.0, 22),
    ),
) -> QImage:
    image = QImage(size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    if not sampled_points or size.isEmpty():
        return image

    line_path = QPainterPath(sampled_points[0])
    for point in sampled_points[1:]:
        line_path.lineTo(point)

    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    for width, alpha in layers:
        glow_color = QColor(color)
        glow_color.setAlpha(alpha)
        painter.setPen(
            QPen(
                glow_color,
                width,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
                Qt.PenJoinStyle.RoundJoin,
            )
        )
        painter.drawPath(line_path)
    painter.end()
    return image


def _paint_line_relative_fill(
    painter: QPainter,
    sampled_points: list[QPointF],
    *,
    baseline_y: float,
    color: QColor,
    alpha: int = 28,
    band_alpha: int = 0,
    band_height: float = 0.0,
) -> None:
    if not sampled_points:
        return

    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

    first_x = int(sampled_points[0].x())
    last_x = int(sampled_points[-1].x())
    segment_index = 0

    for x in range(first_x, last_x + 1):
        while (
            segment_index < len(sampled_points) - 2
            and sampled_points[segment_index + 1].x() < x
        ):
            segment_index += 1

        start = sampled_points[segment_index]
        end = sampled_points[min(segment_index + 1, len(sampled_points) - 1)]
        dx = end.x() - start.x()
        if dx <= 0:
            line_y = start.y()
        else:
            t = (x - start.x()) / dx
            line_y = start.y() + ((end.y() - start.y()) * t)

        if line_y >= baseline_y:
            continue

        fill_color = QColor(color)
        fill_color.setAlpha(alpha)
        column_height = int(baseline_y - line_y) + 1
        painter.fillRect(QRect(int(x), int(line_y), 1, column_height), fill_color)

        if band_alpha > 0 and band_height > 0:
            band_bottom = min(baseline_y, line_y + band_height)
            if band_bottom > line_y:
                band_gradient = QLinearGradient(float(x), line_y, float(x), band_bottom)
                band_top_color = QColor(color)
                band_top_color.setAlpha(band_alpha)
                band_bottom_color = QColor(color)
                band_bottom_color.setAlpha(0)
                band_gradient.setColorAt(0.0, band_top_color)
                band_gradient.setColorAt(1.0, band_bottom_color)
                painter.fillRect(
                    QRect(int(x), int(line_y), 1, int(band_bottom - line_y) + 1),
                    band_gradient,
                )

    painter.restore()


# ── Profile card ──────────────────────────────────────────────────────────────

class RaidProfileCard(QFrame):
    raidNowRequested = Signal(str)
    resetProfileRequested = Signal(str)
    actionOverridesRequested = Signal(str)

    def __init__(self, profile_directory: str, *, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.profile_directory = profile_directory
        self._details_visible = False
        self._raid_now_enabled = False
        self._profile_config = None
        self._profile_state = None
        self._execution_overlay_state = "none"
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
        self.reset_profile_button = QPushButton("")
        self.reset_profile_button.setObjectName("profileResetButton")
        self.reset_profile_button.setProperty("variant", "secondary")
        self.reset_profile_button.setFixedSize(21, 21)
        self.reset_profile_button.setIcon(_build_profile_reset_icon(size=15))
        self.reset_profile_button.setIconSize(QSize(15, 15))
        self.reset_profile_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.reset_profile_button.setToolTip("Reset profile status")
        self.reset_profile_button.clicked.connect(
            lambda: self.resetProfileRequested.emit(self.profile_directory)
        )
        self.action_config_button = QPushButton("")
        self.action_config_button.setObjectName("profileActionConfigButton")
        self.action_config_button.setProperty("variant", "secondary")
        self.action_config_button.setFixedSize(21, 21)
        self.action_config_button.setIcon(_build_profile_action_icon(size=15))
        self.action_config_button.setIconSize(QSize(15, 15))
        self.action_config_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.action_config_button.setToolTip("Configure profile actions")
        self.action_config_button.clicked.connect(
            lambda: self.actionOverridesRequested.emit(self.profile_directory)
        )
        header_row.addWidget(self.dot_label, 0, Qt.AlignmentFlag.AlignVCenter)
        header_row.addWidget(self.title_label, 1)
        header_row.addSpacing(6)
        header_row.addWidget(
            self.reset_profile_button,
            0,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        )
        header_row.addWidget(
            self.action_config_button,
            0,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        )
        layout.addLayout(header_row)

        self.status_label = QLabel("")
        self.status_label.setProperty("muted", "true")
        self.warmup_progress_bar = QProgressBar()
        self.warmup_progress_bar.setObjectName("warmupProgressBar")
        self.warmup_progress_bar.setRange(0, 100)
        self.warmup_progress_bar.setTextVisible(True)
        self.warmup_progress_bar.hide()
        self.reason_label = QLabel("")
        self.reason_label.setWordWrap(True)
        self.reason_label.setProperty("muted", "true")
        self.reason_label.hide()

        self.raid_now_button = AttentionPulseButton("Raid NOW!")
        self.raid_now_button.clicked.connect(
            lambda: self.raidNowRequested.emit(self.profile_directory)
        )
        self.raid_now_feedback_label = QLabel("")
        self.raid_now_feedback_label.setWordWrap(True)
        self.raid_now_feedback_label.setProperty("muted", "true")
        self.raid_now_feedback_label.hide()

        layout.addWidget(self.status_label)
        layout.addWidget(self.warmup_progress_bar)
        layout.addWidget(self.reason_label)
        layout.addWidget(self.raid_now_button)
        layout.addWidget(self.raid_now_feedback_label)
        layout.addStretch()

    def apply_state(self, profile, state: RaidProfileState) -> None:
        self._profile_config = profile
        self._profile_state = state
        self._refresh_visual_state()

    def set_execution_overlay_state(self, overlay_state: str) -> None:
        self._execution_overlay_state = str(overlay_state or "none")
        self._refresh_visual_state()

    def _refresh_visual_state(self) -> None:
        profile = self._profile_config
        state = self._profile_state
        if profile is None or state is None:
            return
        self.profile_directory = state.profile_directory
        self.title_label.setText(state.label)
        base_is_paused = not raid_profile_has_any_actions_enabled(profile)
        base_is_error = state.status == "red" and not base_is_paused
        base_is_warmup = bool(getattr(profile, "warmup_enabled", False)) and not base_is_error

        if self._execution_overlay_state == "stopped":
            profile_status = "stopped"
            dot_variant = "error"
            status_text = "Stopped"
            reason_visible = False
            reset_visible = False
        elif self._execution_overlay_state == "paused":
            profile_status = "paused"
            dot_variant = "active"
            status_text = "Paused"
            reason_visible = False
            reset_visible = False
        else:
            profile_status = (
                "warmup"
                if base_is_warmup
                else "paused" if base_is_paused else "red" if base_is_error else "green"
            )
            dot_variant = (
                "active"
                if base_is_warmup or base_is_paused
                else "error" if base_is_error else "running"
            )
            status_text = (
                "Warmup"
                if base_is_warmup
                else "Paused" if base_is_paused else "Needs attention" if base_is_error else "Healthy"
            )
            if not base_is_error:
                self._details_visible = False
            reason_visible = base_is_error and self._details_visible
            reset_visible = base_is_error

        self.setProperty("profileStatus", profile_status)
        self.style().unpolish(self)
        self.style().polish(self)

        _apply_variant(self.dot_label, dot_variant)
        self.status_label.setText(status_text)
        warmup_completed_cycles = max(
            0,
            min(int(getattr(profile, "warmup_completed_cycles", 0) or 0), 20),
        )
        warmup_cycle_index = max(
            0,
            min(int(getattr(profile, "warmup_cycle_index", 0) or 0), 2),
        )
        completed_warmup_raids = min(
            warmup_completed_cycles * 3 + warmup_cycle_index,
            60,
        )
        progress_value = int(round((completed_warmup_raids / 60) * 100))
        self.warmup_progress_bar.setValue(progress_value)
        self.warmup_progress_bar.setFormat(f"{progress_value}%")
        self.warmup_progress_bar.setVisible(bool(getattr(profile, "warmup_enabled", False)))
        self.reason_label.setText(state.last_error or "No details available")
        self.reason_label.setVisible(reason_visible)
        self.reset_profile_button.setVisible(reset_visible)
        self.raid_now_button.setVisible(True)

    def set_raid_now_enabled(self, enabled: bool) -> None:
        self._raid_now_enabled = bool(enabled)
        if self.raid_now_button.text() == "Raid NOW!":
            self.raid_now_button.setEnabled(self._raid_now_enabled)

    def set_raid_now_busy(self, text: str) -> None:
        self.raid_now_button.setText(str(text))
        self.raid_now_button.setEnabled(False)
        self.raid_now_button.set_busy(True)
        self.raid_now_feedback_label.hide()

    def reset_raid_now_button(self) -> None:
        self.raid_now_button.setText("Raid NOW!")
        self.raid_now_button.set_busy(False)
        self.raid_now_button.setEnabled(self._raid_now_enabled)

    def show_raid_now_feedback(self, message: str) -> None:
        self.raid_now_feedback_label.setText(str(message))
        self.raid_now_feedback_label.setVisible(bool(message))

    def clear_raid_now_feedback(self) -> None:
        self.raid_now_feedback_label.clear()
        self.raid_now_feedback_label.hide()

    def mousePressEvent(self, event) -> None:
        if self.property("profileStatus") == "red":
            self._details_visible = not self._details_visible
            self.reason_label.setVisible(self._details_visible)
        super().mousePressEvent(event)


# ── Sidebar ───────────────────────────────────────────────────────────────────

class ActivityBadge(QWidget):
    _HEIGHT = 20
    _H_PADDING = 8
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
        font.setPointSize(max(9, font.pointSize() - 1))
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
        reason_text: str | None,
    ) -> None:
        super().__init__()
        self.setObjectName("activityCard")
        self.setProperty("activityTone", tone)
        self.setMinimumHeight(30)

        layout = QHBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(10, 4, 10, 4)

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
        reason = reason_text or ""

        reason_label = QLabel(self._truncate_middle(reason or "—", 20))
        reason_label.setObjectName("activityReason")
        reason_label.setToolTip(reason_text or "")
        reason_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        reason_label.setSizePolicy(
            QSizePolicy.Policy.Maximum,
            QSizePolicy.Policy.Preferred,
        )
        reason_label.setParent(self)
        reason_label.setVisible(bool(reason_text))
        layout.addWidget(reason_label, 0, Qt.AlignmentFlag.AlignVCenter)

    def _truncate_middle(self, text: str, max_length: int) -> str:
        if len(text) <= max_length:
            return text
        keep = max(4, (max_length - 1) // 2)
        return f"{text[:keep]}…{text[-keep:]}"


class RaidActivityChart(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._series = [0] * 24
        self._mode = RAID_ACTIVITY_MODE_SMOOTHED_RATE
        self.setObjectName("raidActivityChart")
        self.setMinimumHeight(280)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._chart = QChart()
        self._chart.legend().hide()
        self._chart.setAnimationOptions(QChart.AnimationOption.NoAnimation)
        self._chart.setBackgroundVisible(False)
        self._chart.setPlotAreaBackgroundVisible(False)
        self._chart.setMargins(QMargins(0, 0, 0, 0))
        self._chart.layout().setContentsMargins(0, 0, 0, 0)

        self._chart_view = QChartView(self._chart, self)
        self._chart_view.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self._chart_view.setStyleSheet("background: transparent; border: none;")
        self._chart_view.setFrameShape(QChartView.Shape.NoFrame)
        self._chart_view.setBackgroundBrush(QColor("#060b13"))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._chart_view)

        self._x_axis = QDateTimeAxis(self)
        self._x_axis.setFormat("HH:mm")
        self._x_axis.setTickCount(7)
        self._x_axis.setLabelsColor(QColor(MUTED))
        self._x_axis.setGridLineVisible(False)
        self._x_axis.setMinorGridLineVisible(False)
        self._x_axis.setLineVisible(False)
        x_font = QFont(self.font())
        x_font.setPointSize(max(9, x_font.pointSize() - 1))
        self._x_axis.setLabelsFont(x_font)

        self._y_axis = QValueAxis(self)
        self._y_axis.setRange(0.0, 10.0)
        self._y_axis.setTickCount(5)
        self._y_axis.setLabelFormat("%d")
        self._y_axis.setLabelsColor(QColor(MUTED))
        self._y_axis.setGridLineVisible(False)
        self._y_axis.setMinorGridLineVisible(False)
        self._y_axis.setLineVisible(False)
        y_font = QFont(self.font())
        y_font.setPointSize(max(9, y_font.pointSize() - 1))
        self._y_axis.setLabelsFont(y_font)

        self._chart.addAxis(self._x_axis, Qt.AlignmentFlag.AlignBottom)
        self._chart.addAxis(self._y_axis, Qt.AlignmentFlag.AlignLeft)
        self._chart.setPlotAreaBackgroundVisible(False)
        self._recreate_chart_series()

    def set_series(self, values: list[int]) -> None:
        series = list(values)
        if not series:
            series = [0, 0]
        elif len(series) == 1:
            series = [series[0], series[0]]
        self._series = series
        self._rebuild_chart_series()

    def set_mode(self, mode: str) -> None:
        normalized = str(mode or "").strip().lower().replace("-", "_")
        next_mode = (
            normalized
            if normalized
            in {
                RAID_ACTIVITY_MODE_CUMULATIVE,
                RAID_ACTIVITY_MODE_PER_HOUR,
                RAID_ACTIVITY_MODE_ROLLING_60M,
                RAID_ACTIVITY_MODE_SMOOTHED_RATE,
            }
            else RAID_ACTIVITY_MODE_SMOOTHED_RATE
        )
        if self._mode == next_mode:
            return
        self._mode = next_mode
        self._recreate_chart_series()
        self._rebuild_chart_series()

    def sizeHint(self) -> QSize:
        return QSize(520, 300)

    def chart(self) -> QChart:
        return self._chart

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._chart_view.setRubberBand(QChartView.RubberBand.NoRubberBand)

    def _should_use_spline_series(self) -> bool:
        return self._mode == RAID_ACTIVITY_MODE_SMOOTHED_RATE

    def _recreate_chart_series(self) -> None:
        line_pen = QPen(QColor("#eee6d0"), 2.4)
        line_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        line_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)

        for series in list(self._chart.series()):
            self._chart.removeSeries(series)

        if self._should_use_spline_series():
            upper_series = QSplineSeries(self)
            fill_series = QSplineSeries(self)
        else:
            upper_series = QLineSeries(self)
            fill_series = QLineSeries(self)

        upper_series.setUseOpenGL(False)
        upper_series.setPen(line_pen)

        fill_series.setUseOpenGL(False)
        fill_series.setPen(Qt.PenStyle.NoPen)

        baseline_series = QLineSeries(self)
        baseline_series.setUseOpenGL(False)
        baseline_series.setPen(Qt.PenStyle.NoPen)

        area_series = QAreaSeries(fill_series, baseline_series)
        area_series.setPen(Qt.PenStyle.NoPen)
        area_series.setBrush(QColor(184, 167, 122, 34))

        self._upper_series = upper_series
        self._fill_series = fill_series
        self._baseline_series = baseline_series
        self._area_series = area_series

        self._chart.addSeries(self._area_series)
        self._chart.addSeries(self._upper_series)
        self._area_series.attachAxis(self._x_axis)
        self._area_series.attachAxis(self._y_axis)
        self._upper_series.attachAxis(self._x_axis)
        self._upper_series.attachAxis(self._y_axis)

    def _rebuild_chart_series(self) -> None:
        self._upper_series.clear()
        self._fill_series.clear()
        self._baseline_series.clear()

        now = datetime.now().replace(second=0, microsecond=0)
        if len(self._series) <= 24:
            start = now.replace(minute=0) - timedelta(hours=len(self._series) - 1)
            step = timedelta(hours=1)
        else:
            aligned_now = now - timedelta(minutes=now.minute % 5)
            start = aligned_now - timedelta(hours=24)
            step = timedelta(seconds=(24 * 60 * 60) / max(1, len(self._series) - 1))

        for index, value in enumerate(self._series):
            dt = start + (step * index)
            x_value = QDateTime.fromMSecsSinceEpoch(int(dt.timestamp() * 1000)).toMSecsSinceEpoch()
            numeric_value = float(value)
            self._upper_series.append(x_value, numeric_value)
            self._fill_series.append(x_value, numeric_value)
            self._baseline_series.append(x_value, 0.0)

        rounded_max = float(((max(10, max(self._series)) + 9) // 10) * 10 or 10)
        start_ms = QDateTime.fromMSecsSinceEpoch(int(start.timestamp() * 1000))
        end_ms = QDateTime.fromMSecsSinceEpoch(int((start + (step * (len(self._series) - 1))).timestamp() * 1000))
        self._x_axis.setRange(start_ms, end_ms)
        self._x_axis.setTickCount(7 if len(self._series) > 6 else max(2, len(self._series)))
        self._y_axis.setRange(0.0, rounded_max)


class TopTabStrip(QWidget):
    pageRequested = Signal(int)

    _NAV_ITEMS = [
        ("Dashboard", 0, "dashboard"),
        ("Settings", 1, "settings"),
        ("Bot Actions", 2, "bot_actions"),
    ]

    def __init__(
        self,
        *,
        badge_text: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("topTabStrip")
        self.setFixedWidth(96)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 22, 16, 22)
        layout.setSpacing(18)

        brand_halo = QFrame()
        brand_halo.setObjectName("shellBrandHalo")
        brand_halo.setFixedSize(76, 76)
        halo_layout = QVBoxLayout(brand_halo)
        halo_layout.setContentsMargins(11, 11, 11, 11)
        halo_layout.setSpacing(0)
        brand_mark = QLabel("")
        brand_mark.setObjectName("shellBrandMark")
        brand_mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand_mark.setFixedSize(54, 54)
        icon = app_icon()
        if not icon.isNull():
            brand_mark.setPixmap(icon.pixmap(QSize(54, 54)))
        halo_layout.addWidget(brand_mark, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(brand_halo, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addSpacing(8)

        self._buttons: list[QPushButton] = []
        self._button_icons: list[tuple[QIcon, QIcon]] = []
        for label, index, icon_name in self._NAV_ITEMS:
            btn = QPushButton("")
            btn.setObjectName("shellTabButton")
            btn.setAccessibleName(label)
            btn.setToolTip(label)
            btn.setFixedSize(48, 48)
            btn.setIconSize(QSize(22, 22))
            normal_icon = _build_shell_nav_icon(icon_name, color=MUTED)
            active_icon = _build_shell_nav_icon(icon_name, color=ACCENT_HOVER)
            btn.setIcon(normal_icon)
            btn.clicked.connect(lambda _, i=index: self._activate(i))
            layout.addWidget(btn, 0, Qt.AlignmentFlag.AlignHCenter)
            self._buttons.append(btn)
            self._button_icons.append((normal_icon, active_icon))

        layout.addStretch()
        account_button = QPushButton("")
        account_button.setObjectName("shellAccountButton")
        account_button.setAccessibleName("Account")
        account_button.setToolTip("Account")
        account_button.setFixedSize(48, 48)
        account_button.setIconSize(QSize(22, 22))
        account_button.setIcon(_build_shell_nav_icon("account", color=MUTED))
        layout.addWidget(account_button, 0, Qt.AlignmentFlag.AlignHCenter)
        self._session_stamp_label = QLabel(badge_text or "", self)
        self._session_stamp_label.setObjectName("shellSessionStamp")
        self._session_stamp_label.setProperty("muted", "true")
        self._session_stamp_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._session_stamp_label.hide()

        self._activate(0)

    def _activate(self, index: int) -> None:
        self._set_active_page(index)
        self.pageRequested.emit(index)

    def _set_active_page(self, index: int) -> None:
        for i, btn in enumerate(self._buttons):
            active = i == index
            btn.setProperty("active", "true" if active else "false")
            normal_icon, active_icon = self._button_icons[i]
            btn.setIcon(active_icon if active else normal_icon)
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def set_active_page(self, index: int) -> None:
        self._set_active_page(index)


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
        available_chats_loader=None,
        session_status_loader=None,
        slot_capture_service=None,
        sender_candidate_picker=None,
        profile_add_picker=None,
        profile_action_picker=None,
        hotkey_registrar_factory=None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.controller = controller
        self.storage = storage
        self.confirm_close = confirm_close or self._confirm_close
        self.available_profiles_loader = (
            available_profiles_loader or self._load_available_profiles
        )
        self.available_chats_loader = available_chats_loader or self._load_available_chats
        self.session_status_loader = session_status_loader or self._load_session_status
        self.slot_capture_service = slot_capture_service or SlotCaptureService(
            base_dir=getattr(self.storage, "base_dir", Path(".")),
        )
        self.sender_candidate_picker = (
            sender_candidate_picker or self._pick_sender_candidates
        )
        self.profile_add_picker = (
            profile_add_picker or self._pick_raid_profile_to_add
        )
        self.profile_action_picker = (
            profile_action_picker or self._pick_profile_action_overrides
        )
        self.hotkey_registrar_factory = (
            hotkey_registrar_factory or self._default_hotkey_registrar_factory
        )
        self.bot_state = "stopped"
        self.connection_state = "disconnected"
        self._automation_queue_state = "idle"
        self._bot_actions_status_text = "Idle"
        self._bot_actions_current_slot_text: str | None = None
        self._bot_actions_last_error_text: str | None = None
        self._bot_actions_run_slots_snapshot: tuple[tuple[int, str], ...] = ()
        self._slot_1_presets_dialog: Slot1PresetsDialog | None = None
        self._latest_state = DesktopAppState()
        self._raid_now_pending_profile_directory: str | None = None
        self._raid_now_started_profile_directory: str | None = None
        self._raid_now_feedback_by_profile: dict[str, str] = {}
        self.raid_profile_cards: dict[str, RaidProfileCard] = {}
        self._raid_profile_card_widgets: list[RaidProfileCard] = []
        self._profile_card_columns = 0
        self._restore_geometry: QRect | None = None
        self._restore_was_maximized = False
        self._bot_session_started_at: datetime | None = None
        self._available_chats_signature = self._chat_source_signature(
            self.controller.config
        )
        self._available_chats_cache = list(self.available_chats_loader())
        self._hotkey_registrar = self.hotkey_registrar_factory()

        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(960, 640)

        # ── Labels ────────────────────────────────────────────────────────────
        self.bot_state_label = QLabel("")
        self.connection_state_label = QLabel("")
        self.raids_detected_label = QLabel("0")
        self.raids_opened_label = QLabel("0")
        self.avg_raid_completion_time_label = QLabel("—")
        self.average_raids_per_hour_label = QLabel("—")
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
        self.sidebar_success_rate_label = QLabel("—")
        self.sidebar_uptime_label = QLabel("—")
        self.metric_title_labels: list[QLabel] = []
        self.metric_reset_buttons: dict[str, QPushButton] = {}
        self.activity_list = QListWidget()
        self.activity_list.setObjectName("activityList")
        self.activity_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.activity_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.raid_activity_chart = RaidActivityChart()
        self.raid_activity_chart.set_mode(self._raid_activity_chart_mode())

        # ── Dot indicators for command row ────────────────────────────────────
        self._bot_dot = QLabel()
        self._bot_dot.setObjectName("statusDot")
        self._bot_dot.setFixedSize(9, 9)
        self._conn_dot = QLabel()
        self._conn_dot.setObjectName("statusDot")
        self._conn_dot.setFixedSize(9, 9)

        # ── Buttons ────────────────────────────────────────────────────────────
        self.start_button = AttentionPulseButton("Start")
        self.stop_button = QPushButton("Stop")
        self.start_button.setProperty("dashboardActionButton", "true")
        self.stop_button.setProperty("dashboardActionButton", "true")
        self.start_button.setMinimumWidth(84)
        self.stop_button.setMinimumWidth(84)
        self.start_button.clicked.connect(self.controller.start_bot)
        self.stop_button.clicked.connect(self.controller.stop_bot)

        # ── Layout ─────────────────────────────────────────────────────────────
        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.top_tabs = TopTabStrip(badge_text=APP_VERSION_BADGE, parent=central)
        self.top_tabs.hide()

        self.stack = QStackedWidget(central)
        self.stack.hide()
        self._native_dashboard_shadow = self._build_dashboard_tab()
        self.stack.addWidget(self._wrap_page(self._native_dashboard_shadow))
        self.dashboard_web = DashboardWebView(
            on_start=self.controller.start_bot,
            on_stop=self.controller.stop_bot,
            on_toggle_pause=getattr(self.controller, "toggle_pause_resume", lambda: None),
            on_raid_now=self._handle_web_raid_now_requested,
            on_raid_now_for_profile=self._handle_raid_now_requested,
            on_reset_profile=getattr(self.controller, "reset_raid_profile", lambda _profile: None),
            on_configure_profile=self._configure_profile_action_overrides,
            on_reset_all_profiles=getattr(self.controller, "reset_all_raid_profiles", lambda: None),
            on_set_raid_on_restart=getattr(
                self.controller,
                "set_raid_on_restart_enabled",
                lambda _enabled: None,
            ),
            on_set_performance_mode=getattr(
                self.controller,
                "set_performance_mode_enabled",
                lambda _enabled: None,
            ),
            on_set_twenty_four_seven_mode=getattr(
                self.controller,
                "set_twenty_four_seven_mode_enabled",
                lambda _enabled: None,
            ),
            on_set_page_ready_timeout=getattr(
                self.controller,
                "set_page_ready_timeout_seconds",
                lambda _seconds: None,
            ),
            on_reauthorize=self._web_reauthorize_requested,
            on_export_diagnostics=self._web_export_diagnostics_requested,
            on_refresh_chats=self._web_refresh_chats_requested,
            on_scan_senders=self._web_scan_senders_requested,
            on_add_profile=self._web_add_profile_requested,
            on_move_profile=self._web_move_profile_requested,
            on_remove_profile=getattr(
                self.controller,
                "remove_raid_profile",
                lambda _profile: None,
            ),
            on_capture_page_template=self._web_capture_page_template_requested,
            on_test_page_template=self._web_test_page_template_requested,
            on_capture_slot=self._capture_bot_action_slot,
            on_test_slot=self.controller.test_bot_action_slot,
            on_open_slot_presets=self._open_bot_action_slot_presets,
            on_capture_slot_finish=lambda _slot_index: self._capture_slot_1_finish_template(),
            on_test_enabled_slots=self._web_test_enabled_slots_requested,
            on_capture_troubleshoot=self._capture_troubleshoot_template,
            on_test_troubleshoot=self._test_troubleshoot_template,
        )
        root.addWidget(self.dashboard_web, 1)
        self.settings_page = SettingsPage(
            config=self.controller.config,
            available_profiles=self.available_profiles_loader(),
            available_chats=self._available_chats_cache,
            session_status=self.session_status_loader(),
            reauthorize_available=hasattr(self.controller, "reauthorize_session"),
        )
        self.settings_page.applyRequested.connect(self._apply_settings_config)
        self.settings_page.senderScanRequested.connect(self._scan_allowed_senders)
        self.settings_page.raidProfileOptionsRefreshRequested.connect(
            self._refresh_available_profiles_for_settings
        )
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
        self.bot_actions_page.pageExitCaptureRequested.connect(
            self._capture_page_exit_template
        )
        self.bot_actions_page.slotCaptureRequested.connect(self._capture_bot_action_slot)
        self.bot_actions_page.slotTestRequested.connect(self.controller.test_bot_action_slot)
        self.bot_actions_page.slotPresetsRequested.connect(self._open_bot_action_slot_presets)
        self.bot_actions_page.slotEnabledChanged.connect(
            self.controller.set_bot_action_slot_enabled
        )
        self.bot_actions_page.slot1FinishDelayChanged.connect(
            self.controller.set_slot_1_finish_delay_seconds
        )
        self.bot_actions_page.pageReadyTimeoutChanged.connect(
            getattr(
                self.controller,
                "set_page_ready_timeout_seconds",
                lambda _seconds: None,
            )
        )
        self.bot_actions_page.troubleshootCaptureRequested.connect(
            self._capture_troubleshoot_template
        )
        self.bot_actions_page.troubleshootTestRequested.connect(
            self._test_troubleshoot_template
        )
        self.stack.addWidget(self._wrap_page(self.bot_actions_page))

        self.top_tabs.pageRequested.connect(self.stack.setCurrentIndex)
        self.stack.currentChanged.connect(self.top_tabs.set_active_page)

        # Keep self.tabs alias for any external code that references it
        self.tabs = self.stack

        self.setCentralWidget(central)
        self._connect_controller_signals()
        state = self.storage.load_state()
        self._apply_state(state, include_activity=True)
        self._sync_config(self.controller.config)
        self._render_bot_actions_status()
        self._ensure_window_icon()
        tray_icon = self._tray_icon()
        self.tray_controller = tray_controller_factory(
            window=self,
            controller=self.controller,
            icon=tray_icon,
            initial_bot_state=self.bot_state,
        )

    # ── Page builders ─────────────────────────────────────────────────────────

    def _build_dashboard_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(18)
        layout.setContentsMargins(20, 20, 20, 28)

        layout.addWidget(self._build_dashboard_topbar())

        hero_row = QHBoxLayout()
        hero_row.setSpacing(18)
        self.status_panel = self._build_raid_activity_panel()
        self.command_execution_panel = self._build_command_execution_panel()
        hero_row.addWidget(self.status_panel, 3)
        hero_row.addWidget(self.command_execution_panel, 1)
        layout.addLayout(hero_row)

        self.profiles_panel = self._build_profiles_panel()
        layout.addWidget(self.profiles_panel)
        layout.addStretch()
        return widget

    def _build_dashboard_topbar(self) -> QWidget:
        topbar = QWidget()
        topbar.setObjectName("dashboardTopbar")
        layout = QHBoxLayout(topbar)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(16)

        title_block = QWidget()
        title_layout = QVBoxLayout(title_block)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(3)
        title = QLabel(APP_NAME)
        title.setObjectName("dashboardAppTitle")
        subtitle = QLabel("Navy soft sand surface")
        subtitle.setObjectName("dashboardAppSubtitle")
        title_layout.addWidget(title)
        title_layout.addWidget(subtitle)
        layout.addWidget(title_block, 1)

        state_pill = QWidget()
        state_pill.setObjectName("dashboardStatePill")
        state_layout = QHBoxLayout(state_pill)
        state_layout.setContentsMargins(12, 7, 12, 7)
        state_layout.setSpacing(8)
        state_layout.addWidget(self._bot_dot)
        self.bot_state_label.setObjectName("dashboardBotState")
        state_layout.addWidget(self.bot_state_label)
        layout.addWidget(state_pill, 0, Qt.AlignmentFlag.AlignVCenter)
        return topbar

    def _add_vertical_separator(self, layout: QHBoxLayout) -> None:
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet("background: #1e3252; max-width: 1px; border: none; margin: 6px 4px;")
        layout.addWidget(sep)

    def _build_raid_activity_panel(self) -> QWidget:
        panel, surface = self._build_panel("raidActivityPanel")
        layout = QVBoxLayout(surface)
        layout.setSpacing(16)
        layout.setContentsMargins(22, 20, 22, 22)

        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(12)
        header_text = QWidget()
        header_text_layout = QVBoxLayout(header_text)
        header_text_layout.setContentsMargins(0, 0, 0, 0)
        header_text_layout.setSpacing(8)
        kicker = QLabel("Raid Activity")
        kicker.setObjectName("dashboardKicker")
        title = QLabel("Live raid throughput.")
        title.setObjectName("dashboardHeroTitle")
        copy = self._build_helper_label(
            "A command-center view of completed and failed raids across the current session."
        )
        copy.setObjectName("dashboardHeroCopy")
        header_text_layout.addWidget(kicker)
        header_text_layout.addWidget(title)
        header_text_layout.addWidget(copy)
        header_layout.addWidget(header_text, 1)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        chart_card = QFrame()
        chart_card.setObjectName("raidActivityCard")
        chart_layout = QVBoxLayout(chart_card)
        chart_layout.setContentsMargins(14, 14, 14, 12)
        chart_layout.setSpacing(10)
        chart_header = QHBoxLayout()
        chart_header.setContentsMargins(0, 0, 0, 0)
        chart_header.setSpacing(8)
        chart_title = QLabel("Raid Activity")
        chart_title.setObjectName("raidActivityTitle")
        chart_subtitle = QLabel(self._raid_activity_subtitle_text())
        chart_subtitle.setObjectName("raidActivitySubtitle")
        chart_subtitle.setProperty("muted", "true")
        self.raid_activity_subtitle_label = chart_subtitle
        chart_header.addWidget(chart_title)
        chart_header.addStretch()
        chart_header.addWidget(chart_subtitle)
        chart_layout.addLayout(chart_header)
        chart_layout.addWidget(self.raid_activity_chart)
        layout.addWidget(chart_card)
        return panel

    def _build_command_execution_panel(self) -> QWidget:
        panel, surface = self._build_panel("commandExecutionPanel")
        layout = QVBoxLayout(surface)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 18, 20, 18)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(12)
        title_block = QWidget()
        title_layout = QVBoxLayout(title_block)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(2)
        kicker = QLabel("Command")
        kicker.setObjectName("dashboardKicker")
        title = QLabel("Execution")
        title.setObjectName("dashboardPanelTitle")
        title_layout.addWidget(kicker)
        title_layout.addWidget(title)
        header_row.addWidget(title_block, 1)
        status_pill = QWidget()
        status_pill.setObjectName("commandStatusPill")
        status_layout = QHBoxLayout(status_pill)
        status_layout.setContentsMargins(12, 6, 12, 6)
        status_layout.setSpacing(8)
        status_layout.addWidget(self._conn_dot)
        self.connection_state_label.setObjectName("commandConnectionState")
        status_layout.addWidget(self.connection_state_label)
        header_row.addWidget(status_pill, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(header_row)

        button_stack = QWidget()
        button_stack.setObjectName("commandButtonStack")
        button_layout = QVBoxLayout(button_stack)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(10)
        self.start_button.setText("Start")
        self.stop_button.setText("Stop")
        self.pause_queue_button = QPushButton("Pause queue after current action")
        self.pause_queue_button.setProperty("dashboardActionButton", "true")
        self.pause_queue_button.setProperty("variant", "secondary")
        pause_handler = getattr(self.controller, "toggle_pause_resume", None)
        if callable(pause_handler):
            self.pause_queue_button.clicked.connect(pause_handler)
        else:
            self.pause_queue_button.setEnabled(False)
        button_layout.addWidget(self.start_button)
        button_layout.addWidget(self.pause_queue_button)
        button_layout.addWidget(self.stop_button)
        layout.addWidget(button_stack)

        self.metric_cards = [
            self._build_metric_card(
                "raids_completed",
                "Raids Completed",
                self.raids_completed_label,
            ),
            self._build_metric_card(
                "raids_failed",
                "Raids Failed",
                self.raids_failed_label,
            ),
            self._build_metric_card(
                "success_rate",
                "Success Rate",
                self.sidebar_success_rate_label,
            ),
            self._build_metric_card("uptime", "Uptime", self.sidebar_uptime_label),
        ]
        metrics_grid_widget = QWidget()
        metrics_grid_widget.setObjectName("commandMetricsGrid")
        metrics_grid = QGridLayout(metrics_grid_widget)
        metrics_grid.setContentsMargins(0, 4, 0, 0)
        metrics_grid.setHorizontalSpacing(10)
        metrics_grid.setVerticalSpacing(10)
        for index, card in enumerate(self.metric_cards):
            metrics_grid.addWidget(card, index // 2, index % 2)
        layout.addWidget(metrics_grid_widget)
        layout.addStretch()
        return panel

    def _build_profiles_panel(self) -> QWidget:
        panel, surface = self._build_panel("profilesPanel")
        layout = QVBoxLayout(surface)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 18, 20, 18)
        header_row = QWidget()
        header_row.setObjectName("profilesHeaderRow")
        header_layout = QHBoxLayout(header_row)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(12)
        header_layout.addWidget(self._build_section_title("Profiles"))
        header_layout.addStretch()
        self.restart_all_profiles_button = AttentionPulseButton("Restart All")
        self.restart_all_profiles_button.setProperty("dashboardActionButton", "true")
        self.restart_all_profiles_button.setMinimumWidth(112)
        reset_all_handler = getattr(self.controller, "reset_all_raid_profiles", None)
        if callable(reset_all_handler):
            self.restart_all_profiles_button.clicked.connect(reset_all_handler)
        else:
            self.restart_all_profiles_button.setEnabled(False)
        header_layout.addWidget(
            self.restart_all_profiles_button,
            0,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        )
        self.restart_all_raid_checkbox = QCheckBox("Raid?")
        self.restart_all_raid_checkbox.setChecked(
            bool(getattr(self.controller.config, "raid_on_restart_enabled", False))
        )
        raid_on_restart_handler = getattr(
            self.controller,
            "set_raid_on_restart_enabled",
            None,
        )
        if callable(raid_on_restart_handler):
            self.restart_all_raid_checkbox.toggled.connect(raid_on_restart_handler)
        else:
            self.restart_all_raid_checkbox.setEnabled(False)
        header_layout.addWidget(
            self.restart_all_raid_checkbox,
            0,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        )
        layout.addWidget(header_row)
        layout.addWidget(self._build_divider())
        layout.addWidget(
            self._build_helper_label(
                "Healthy profiles stay green. Failed profiles turn red until restarted."
            )
        )
        self.profile_cards_container = QWidget()
        self.profile_cards_container.setObjectName("profileCardsContainer")
        self.profile_cards_layout = QGridLayout(self.profile_cards_container)
        self.profile_cards_layout.setContentsMargins(0, 0, 0, 0)
        self.profile_cards_layout.setHorizontalSpacing(12)
        self.profile_cards_layout.setVerticalSpacing(12)
        layout.addWidget(self.profile_cards_container)
        self.activity_panel = self._build_activity_panel()
        layout.addWidget(self.activity_panel)
        return panel

    def _build_metric_card(
        self,
        metric_key: str,
        title: str,
        value_label: QLabel,
    ) -> QFrame:
        card = QFrame()
        card.setObjectName(CARD_OBJECT_NAME)
        layout = QVBoxLayout(card)
        layout.setSpacing(4)
        layout.setContentsMargins(14, 14, 14, 14)
        header_row = QHBoxLayout()
        header_row.setSpacing(8)
        header_row.setContentsMargins(0, 0, 0, 0)
        title_label = QLabel(title)
        title_label.setObjectName("metricTitle")
        value_label.setObjectName("metricValue")
        reset_button = QPushButton("")
        reset_button.setObjectName("metricResetButton")
        reset_button.setFixedSize(18, 18)
        reset_button.setFlat(True)
        reset_button.setIcon(_build_metric_reset_icon(size=13))
        reset_button.setIconSize(QSize(13, 13))
        reset_button.clicked.connect(
            lambda _checked=False, key=metric_key: self.controller.reset_dashboard_metric(key)
        )
        self.metric_reset_buttons[metric_key] = reset_button
        self.metric_title_labels.append(title_label)
        header_row.addWidget(title_label)
        header_row.addStretch()
        header_row.addWidget(reset_button, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(header_row)
        layout.addWidget(value_label)
        layout.addStretch()
        return card

    def _build_status_summary_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("statusSummaryCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)
        for title, value_label, dot_label in (
            ("Bot state", self.bot_state_label, self._bot_dot),
            ("Telegram", self.connection_state_label, self._conn_dot),
            ("Last successful raid", self.last_successful_label, None),
        ):
            row = QWidget()
            row.setObjectName("statusSummaryRow")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(12, 10, 12, 10)
            row_layout.setSpacing(12)

            title_label = QLabel(title)
            title_label.setObjectName("statusSummaryKey")
            value_label.setObjectName("statusSummaryValue")

            row_layout.addWidget(title_label)
            row_layout.addStretch()
            row_layout.addWidget(value_label, 0, Qt.AlignmentFlag.AlignRight)
            if dot_label is not None:
                row_layout.addWidget(dot_label, 0, Qt.AlignmentFlag.AlignVCenter)
            layout.addWidget(row)
        return card

    def _build_activity_panel(self) -> QWidget:
        panel, surface = self._build_panel("activityPanel")
        panel.setProperty("dashboardRecentActivity", "true")
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
        self.last_error_label.setObjectName("dashboardErrorValue")
        error_card = QFrame()
        error_card.setObjectName("dashboardErrorCard")
        error_layout = QVBoxLayout(error_card)
        error_layout.setContentsMargins(14, 12, 14, 12)
        error_layout.setSpacing(4)
        error_heading = QLabel("Latest Issue")
        error_heading.setProperty("muted", "true")
        error_layout.addWidget(error_heading)
        error_layout.addWidget(self.last_error_label)
        layout.addWidget(error_card)
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

    def _refresh_web_dashboard(self) -> None:
        dashboard = getattr(self, "dashboard_web", None)
        if dashboard is None:
            return
        dashboard.set_state(self._build_web_dashboard_state())

    def _build_web_dashboard_state(self) -> dict[str, object]:
        series = list(getattr(self.raid_activity_chart, "_series", []) or [])
        if not series:
            series = [0] * 24
        chart_max = max(max(series), 1)
        chart_top = self._chart_axis_top(chart_max)
        return {
            "appVersion": APP_VERSION_BADGE,
            "botStateText": self._web_bot_state_text(),
            "botVariant": self._web_bot_state_variant(),
            "connectionStateText": _format_status_caption(self.connection_state),
            "connectionVariant": _connection_state_variant(self.connection_state),
            "canStart": self.bot_state not in {"starting", "running"},
            "canStop": self.bot_state in {"starting", "running"},
            "canPause": callable(getattr(self.controller, "toggle_pause_resume", None))
            and self.bot_state in {"starting", "running"},
            "pauseButtonText": self._web_pause_button_text(),
            "canRaidNow": self._web_can_raid_now(),
            "raidNowDisabledReason": self._web_raid_now_disabled_reason(),
            "globalRaidNowText": self._web_global_raid_now_text(),
            "raidOnRestart": bool(
                getattr(self.controller.config, "raid_on_restart_enabled", False)
            ),
            "performanceMode": bool(
                getattr(self.controller.config, "performance_mode_enabled", False)
            ),
            "twentyFourSevenMode": bool(
                getattr(
                    self.controller.config,
                    "twenty_four_seven_mode_enabled",
                    False,
                )
            ),
            "metrics": [
                {"label": "Raids Completed", "value": self.raids_completed_label.text()},
                {"label": "Raids Failed", "value": self.raids_failed_label.text()},
                {
                    "label": "Success Rate",
                    "value": self.sidebar_success_rate_label.text(),
                },
                {"label": "Uptime", "value": self.sidebar_uptime_label.text()},
            ],
            "chartSeries": series,
            "chartMax": chart_top,
            "chartAxis": self._chart_axis_labels(chart_top),
            "chartTimes": self._chart_time_labels(len(series)),
            "lastRaidText": self._web_last_raid_text(),
            "profiles": self._web_profile_cards(),
            "activity": self._web_activity_entries(),
            "settings": self._web_settings_state(),
            "botActions": self._web_bot_actions_state(),
            "troubleshoot": self._web_troubleshoot_state(),
        }

    def _web_bot_state_text(self) -> str:
        if self._automation_queue_state == "suspended":
            return "Paused"
        if self._automation_queue_state == "paused":
            return "Stopped"
        return _format_status_caption(self.bot_state)

    def _web_bot_state_variant(self) -> str:
        if self._automation_queue_state == "suspended":
            return "warning"
        if self._automation_queue_state == "paused":
            return "error"
        return _bot_state_variant(self.bot_state)

    def _web_pause_button_text(self) -> str:
        if self._automation_queue_state in {"paused", "suspended"}:
            return "Resume"
        return "Pause"

    def _web_can_raid_now(self) -> bool:
        return (
            self.connection_state == "connected"
            and self.bot_state in {"starting", "running"}
            and self._automation_queue_state not in {"paused", "suspended"}
            and self._raid_now_pending_profile_directory is None
            and self._raid_now_started_profile_directory is None
            and self._first_raid_now_profile_directory() is not None
        )

    def _web_global_raid_now_text(self) -> str:
        if self._raid_now_started_profile_directory is not None:
            return "Raiding..."
        if self._raid_now_pending_profile_directory is not None:
            return "Fetching..."
        return "Raid NOW!"

    def _web_last_raid_text(self) -> str:
        value = getattr(self._latest_state, "last_successful_raid_open_at", None)
        if value in {None, ""}:
            successful_runs = self._recent_successful_profile_runs(self._latest_state)
            if not successful_runs:
                return "--"
            timestamp = max(timestamp for timestamp, _duration in successful_runs)
        else:
            try:
                timestamp = (
                    value
                    if isinstance(value, datetime)
                    else datetime.fromisoformat(str(value))
                )
            except (TypeError, ValueError):
                return str(value)
        elapsed = max(datetime.now() - timestamp, timedelta())
        total_seconds = int(elapsed.total_seconds())
        if total_seconds < 60:
            return f"{total_seconds:02d}s"
        total_minutes = total_seconds // 60
        if total_minutes < 60:
            return f"{total_minutes}m"
        return f"{total_minutes // 60}h"

    def _chart_axis_top(self, maximum_value: int) -> int:
        maximum_value = max(1, int(maximum_value))
        if maximum_value <= 4:
            return 4
        if maximum_value <= 10:
            return 10
        magnitude = 10 ** (len(str(maximum_value)) - 1)
        return ((maximum_value + magnitude - 1) // magnitude) * magnitude

    def _chart_axis_labels(self, chart_top: int) -> list[int]:
        return [
            int(round(chart_top * 1.0)),
            int(round(chart_top * 0.75)),
            int(round(chart_top * 0.5)),
            int(round(chart_top * 0.25)),
            0,
        ]

    def _chart_time_labels(self, series_length: int) -> list[str]:
        now = datetime.now()
        start = now - timedelta(hours=24 if series_length > 24 else 23)
        return [
            (start + timedelta(hours=offset)).strftime("%H:%M")
            for offset in (0, 6, 12, 18)
        ] + ["NOW"]

    def _web_profile_cards(self) -> list[dict[str, object]]:
        states_by_directory = {
            ps.profile_directory: ps
            for ps in getattr(self._latest_state, "raid_profile_states", ())
        }
        cards: list[dict[str, object]] = []
        for profile in self.controller.config.raid_profiles:
            state = states_by_directory.get(
                profile.profile_directory,
                RaidProfileState(
                    profile_directory=profile.profile_directory,
                    label=profile.label,
                    status="green",
                    last_error=None,
                ),
            )
            profile_status, dot_variant, status_text = self._web_profile_status(
                profile,
                state,
            )
            can_raid_now = self._web_profile_can_raid_now(profile, profile_status)
            cards.append(
                {
                    "directory": profile.profile_directory,
                    "label": state.label,
                    "statusClass": profile_status,
                    "dotVariant": dot_variant,
                    "statusText": status_text,
                    "chips": self._web_profile_chips(
                        profile,
                        profile_status,
                        state.last_error,
                    ),
                    "warmup": bool(getattr(profile, "warmup_enabled", False)),
                    "warmupProgress": self._web_warmup_progress(profile),
                    "error": state.last_error if profile_status == "failed" else None,
                    "errorCount": max(0, int(getattr(state, "error_count", 0) or 0)),
                    "errorReasons": [
                        self._web_profile_failure_chip_label(reason)
                        for reason in getattr(state, "error_reasons", ()) or ()
                    ],
                    "raidNowFeedback": self._raid_now_feedback_by_profile.get(
                        profile.profile_directory,
                        "",
                    ),
                    "canRaidNow": can_raid_now,
                    "raidNowDisabledReason": (
                        ""
                        if can_raid_now
                        else self._web_raid_now_disabled_reason(profile, profile_status)
                    ),
                    "raidNowText": self._web_profile_raid_now_text(
                        profile.profile_directory
                    ),
                }
            )
        return cards

    def _web_profile_status(
        self,
        profile: RaidProfileConfig,
        state: RaidProfileState,
    ) -> tuple[str, str, str]:
        overlay_state = self._raid_profile_execution_overlay_state()
        if overlay_state == "stopped":
            return "stopped", "error", "Stopped"
        if overlay_state == "paused":
            return "paused", "warning", "Paused"
        if state.status == "red" and raid_profile_has_any_actions_enabled(profile):
            return "failed", "error", "Needs attention"
        if bool(getattr(profile, "warmup_enabled", False)):
            return "warmup", "warmup", "Warmup"
        if not raid_profile_has_any_actions_enabled(profile):
            return "paused", "warning", "Paused"
        return "healthy", "running", "Healthy"

    def _web_profile_chips(
        self,
        profile: RaidProfileConfig,
        profile_status: str,
        failure_reason: str | None = None,
    ) -> list[dict[str, str]]:
        if profile_status == "failed":
            return [
                {"label": self._web_profile_failure_chip_label(failure_reason), "tone": ""},
                {"label": "Ready to reset", "tone": ""},
            ]
        if bool(getattr(profile, "warmup_enabled", False)):
            return [
                {"label": "Warm me up baby", "tone": "warm"},
            ]
        chips = []
        for field_name, label, _slot_key in raid_profile_action_specs():
            if bool(getattr(profile, field_name, True)):
                chips.append({"label": label, "tone": "live"})
        if not chips:
            chips.append({"label": "Paused", "tone": ""})
        return chips

    def _web_profile_failure_chip_label(self, failure_reason: str | None) -> str:
        normalized_reason = str(failure_reason or "").strip()
        labels = {
            "target_window_not_found": "Chrome window not found",
            "window_not_focusable": "Chrome window not focusable",
            "window_close_failed": "Window close failed",
            "bot_action_not_configured": "Bot action not configured",
            "page_ready_not_found": "Page ready not found",
            "ui_did_not_change": "UI did not change",
        }
        if normalized_reason in labels:
            return labels[normalized_reason]
        if normalized_reason:
            return normalized_reason.replace("_", " ").title()
        return "Automation failed"

    def _web_warmup_progress(self, profile: RaidProfileConfig) -> int:
        warmup_completed_cycles = max(
            0,
            min(int(getattr(profile, "warmup_completed_cycles", 0) or 0), 20),
        )
        warmup_cycle_index = max(
            0,
            min(int(getattr(profile, "warmup_cycle_index", 0) or 0), 2),
        )
        completed_warmup_raids = min(
            warmup_completed_cycles * 3 + warmup_cycle_index,
            60,
        )
        return int(round((completed_warmup_raids / 60) * 100))

    def _web_profile_raid_now_text(self, profile_directory: str) -> str:
        if profile_directory == self._raid_now_started_profile_directory:
            return "Raiding..."
        if profile_directory == self._raid_now_pending_profile_directory:
            return "Fetching..."
        return "Raid NOW!"

    def _web_profile_has_runnable_mode(self, profile: RaidProfileConfig) -> bool:
        return bool(getattr(profile, "warmup_enabled", False)) or raid_profile_has_any_actions_enabled(
            profile
        )

    def _web_profile_can_raid_now(
        self,
        profile: RaidProfileConfig,
        profile_status: str,
    ) -> bool:
        if not self._web_can_raid_now():
            return False
        if profile_status in {"failed", "paused", "stopped"}:
            return False
        return self._web_profile_has_runnable_mode(profile)

    def _web_raid_now_disabled_reason(
        self,
        profile: RaidProfileConfig | None = None,
        profile_status: str | None = None,
    ) -> str:
        if self._raid_now_started_profile_directory is not None:
            return "Raid NOW is already running."
        if self._raid_now_pending_profile_directory is not None:
            return "Raid NOW is fetching the latest Telegram raid."
        if self._automation_queue_state == "suspended":
            return "Bot is paused. Resume before using Raid NOW."
        if self._automation_queue_state == "paused":
            return "Bot is stopped. Press Start before using Raid NOW."
        if self.bot_state not in {"starting", "running"} and self.connection_state != "connected":
            return "Press Start and connect Telegram to use Raid NOW."
        if self.bot_state not in {"starting", "running"}:
            return "Press Start to use Raid NOW."
        if self.connection_state != "connected":
            return "Connect Telegram to use Raid NOW."
        if profile_status == "failed":
            return "Restart this profile before using Raid NOW."
        if profile is not None and not self._web_profile_has_runnable_mode(profile):
            return "Open the gear and enable at least one action, or Warm me up baby."
        if self._first_raid_now_profile_directory() is None:
            return "No healthy profile is ready for Raid NOW."
        return ""

    def _web_activity_entries(self) -> list[dict[str, str]]:
        entries = []
        for entry in reversed(list(getattr(self._latest_state, "activity", []) or [])):
            if not self._should_display_activity(entry.action):
                continue
            reason_text = self._activity_reason_text(
                entry.action,
                getattr(entry, "reason", None),
            )
            detail_parts = []
            if getattr(entry, "url", None):
                detail_parts.append(str(entry.url))
            if reason_text:
                detail_parts.append(reason_text)
            entries.append(
                {
                    "profile": getattr(entry, "profile_directory", None) or "System",
                    "title": self._format_activity_action(entry.action),
                    "detail": " | ".join(detail_parts)
                    or self._activity_badge(entry.action),
                    "time": self._format_activity_timestamp(entry.timestamp),
                    "tone": self._web_activity_tone(entry.action),
                }
            )
        return entries

    def _web_activity_tone(self, action: str) -> str:
        tone = self._activity_tone(action)
        if tone == "success":
            return ""
        if tone == "warning":
            return "warning"
        if tone == "error":
            return "error"
        return "neutral"

    def _first_raid_now_profile_directory(self) -> str | None:
        states_by_directory = {
            ps.profile_directory: ps
            for ps in getattr(self._latest_state, "raid_profile_states", ())
        }
        for profile in self.controller.config.raid_profiles:
            if not bool(getattr(profile, "enabled", True)):
                continue
            if not self._web_profile_has_runnable_mode(profile):
                continue
            state = states_by_directory.get(profile.profile_directory)
            if state is not None and state.status == "red":
                continue
            return profile.profile_directory
        return None

    def _web_settings_state(self) -> dict[str, object]:
        config = self.controller.config
        states_by_directory = {
            ps.profile_directory: ps
            for ps in getattr(self._latest_state, "raid_profile_states", ())
        }
        allowed_chat_ids = list(getattr(config, "whitelisted_chat_ids", []) or [])
        chats = []
        chats_by_id = {int(chat.chat_id): chat for chat in self._available_chats_cache}
        chat_titles = getattr(config, "whitelisted_chat_titles", {}) or {}
        for chat_id in allowed_chat_ids:
            chat = chats_by_id.get(int(chat_id))
            chats.append(
                {
                    "id": str(chat_id),
                    "label": (
                        getattr(chat, "title", None)
                        or chat_titles.get(int(chat_id))
                        or "Saved Telegram chat"
                    ),
                }
            )
        sender_entries = list(
            getattr(config, "allowed_sender_entries", ())
            or tuple(str(sender_id) for sender_id in getattr(config, "allowed_sender_ids", ()))
        )
        return {
            "sessionStatus": self.settings_page.session_status_label.text(),
            "connection": _format_status_caption(self.connection_state),
            "pauseHotkey": getattr(config, "pause_resume_hotkey", None),
            "apiId": str(getattr(config, "telegram_api_id", "")),
            "apiHashMasked": "*" * min(max(len(str(getattr(config, "telegram_api_hash", ""))), 8), 20),
            "allowedChats": chats,
            "allowedSenders": sender_entries,
            "raidProfiles": [
                {
                    "directory": profile.profile_directory,
                    "label": profile.label,
                    "status": self._web_profile_status(
                        profile,
                        states_by_directory.get(
                            profile.profile_directory,
                            RaidProfileState(
                                profile_directory=profile.profile_directory,
                                label=profile.label,
                                status="green",
                                last_error=None,
                            ),
                        ),
                    )[2],
                }
                for profile in getattr(config, "raid_profiles", ())
            ],
        }

    def _web_bot_actions_state(self) -> dict[str, object]:
        config = self.controller.config
        slots = list(getattr(config, "bot_action_slots", ()) or ())
        slot_names = {
            "slot_1_r": "Reply",
            "slot_2_l": "Like",
            "slot_3_r": "Repost",
            "slot_4_b": "Bookmark",
        }
        slot_delays = {
            "slot_1_r": f"{getattr(config, 'slot_1_finish_delay_seconds', 0)}s",
            "slot_2_l": "0.25s",
            "slot_3_r": "0.25s",
            "slot_4_b": "0.25s",
        }
        first_slot = slots[0] if slots else None
        presets = list(getattr(first_slot, "presets", ()) or ())
        return {
            "status": {
                "latest": self._bot_actions_status_text,
                "currentSlot": self._bot_actions_current_slot_text,
                "lastError": self._bot_actions_last_error_text,
            },
            "pageTemplates": {
                "page_ready": self._web_template_state(
                    "Page Ready",
                    getattr(config, "page_ready_template_path", None),
                ),
                "page_exit": self._web_template_state(
                    "Page Exit",
                    getattr(config, "page_exit_template_path", None),
                ),
            },
            "pageReadyTimeoutSeconds": float(
                getattr(config, "page_ready_timeout_seconds", 12.0)
            ),
            "slots": [
                {
                    "name": slot_names.get(getattr(slot, "key", ""), str(getattr(slot, "label", "?"))),
                    "enabled": bool(getattr(slot, "enabled", False)),
                    "path": self._web_path_text(getattr(slot, "template_path", None)),
                    "saved": self._web_template_saved(getattr(slot, "template_path", None)),
                    "imageSrc": self._web_template_image_src(
                        getattr(slot, "template_path", None)
                    ),
                    "delay": slot_delays.get(getattr(slot, "key", ""), "0.25s"),
                }
                for slot in slots
            ],
            "presetCount": len(presets),
            "presets": [
                {
                    "label": f"Preset {index + 1}",
                    "detail": "Image + text"
                    if getattr(preset, "image_path", None) is not None
                    else "Text only",
                }
                for index, preset in enumerate(presets)
            ],
            "finishTemplatePath": self._web_path_text(
                getattr(first_slot, "finish_template_path", None)
                if first_slot is not None
                else None
            ),
            "finishTemplateSaved": self._web_template_saved(
                getattr(first_slot, "finish_template_path", None)
                if first_slot is not None
                else None
            ),
            "finishTemplateImageSrc": self._web_template_image_src(
                getattr(first_slot, "finish_template_path", None)
                if first_slot is not None
                else None
            ),
        }

    def _web_troubleshoot_state(self) -> dict[str, object]:
        return {
            "cldf": [
                self._web_template_state(
                    f"CLDF {index + 1}",
                    self._troubleshoot_template_path("cldf", index),
                )
                for index in range(3)
            ],
            "black_box": [
                self._web_template_state(
                    "Black Box",
                    self._troubleshoot_template_path("black_box", 0),
                )
            ],
        }

    def _web_template_state(
        self,
        label: str,
        path: Path | str | None,
    ) -> dict[str, object]:
        return {
            "label": label,
            "path": self._web_path_text(path),
            "saved": self._web_template_saved(path),
            "imageSrc": self._web_template_image_src(path),
        }

    def _web_path_text(self, path: Path | str | None) -> str | None:
        if path is None:
            return None
        return str(path)

    def _web_template_saved(self, path: Path | str | None) -> bool:
        if path is None:
            return False
        try:
            return Path(path).exists()
        except OSError:
            return False

    def _web_template_image_src(self, path: Path | str | None) -> str | None:
        if path is None:
            return None
        try:
            template_path = Path(path)
            if not template_path.exists():
                return None
            mime_type = mimetypes.guess_type(str(template_path))[0] or "image/png"
            encoded = base64.b64encode(template_path.read_bytes()).decode("ascii")
            return f"data:{mime_type};base64,{encoded}"
        except OSError:
            return None

    def _web_reauthorize_requested(self) -> None:
        handler = getattr(self.controller, "reauthorize_session", None)
        if callable(handler):
            handler()
            return
        self._show_bot_actions_error("Reauthorize is not available in this build.")

    def _web_export_diagnostics_requested(self) -> None:
        try:
            archive_path = export_diagnostics(
                Path(getattr(self.storage, "base_dir", Path(".")))
            )
        except Exception as exc:
            message = f"Diagnostic export failed: {exc}"
            self._show_bot_actions_error(message)
            QMessageBox.warning(self, "Diagnostics", message)
            return
        message = f"Diagnostics exported: {archive_path}"
        self._show_bot_actions_error(message)
        QMessageBox.information(self, "Diagnostics", message)

    def _web_refresh_chats_requested(self) -> None:
        self._available_chats_cache = list(self.available_chats_loader())
        self.settings_page.set_available_chats(self._available_chats_cache)
        self._refresh_web_dashboard()

    def _web_scan_senders_requested(self) -> None:
        chat_ids = list(getattr(self.controller.config, "whitelisted_chat_ids", []) or [])
        try:
            candidates = list(self.controller.infer_recent_sender_candidates(chat_ids))
        except Exception as exc:
            self.settings_page.show_error(str(exc))
            return
        if not candidates:
            self.settings_page.show_error("No recent sender candidates found.")
            return
        selected_entries = [
            str(entry).strip()
            for entry in self.sender_candidate_picker(candidates)
            if str(entry).strip()
        ]
        if not selected_entries:
            return
        self.settings_page.append_allowed_sender_entries(selected_entries)
        self.settings_page.show_success("Sender scan complete.")
        self._refresh_web_dashboard()

    def _web_add_profile_requested(self) -> None:
        available_profiles = self._refresh_available_profiles_for_settings()
        configured_directories = {
            profile.profile_directory for profile in self.controller.config.raid_profiles
        }
        candidates = [
            profile
            for profile in available_profiles
            if profile.directory_name not in configured_directories
        ]
        if not candidates:
            self.settings_page.show_error("No unused Chrome profile found.")
            return
        selected_profile = self.profile_add_picker(candidates)
        if selected_profile is None:
            self.settings_page.show_error("Profile add cancelled.")
            return
        directory = selected_profile.directory_name
        label = selected_profile.label
        if directory in configured_directories:
            self.settings_page.show_error("Profile already added.")
            return
        self.controller.add_raid_profile(directory, label)
        self.settings_page.show_success(f"Profile added: {label} [{directory}]")

    def _web_move_profile_requested(self, profile_directory: str, direction: str) -> None:
        if not profile_directory:
            return
        self.controller.move_raid_profile(profile_directory, direction)

    def _web_capture_page_template_requested(self, template_key: str) -> None:
        if template_key == "page_exit":
            self._capture_page_exit_template()
            return
        self._capture_page_ready_template()

    def _web_test_page_template_requested(self, template_key: str) -> None:
        if template_key == "page_exit":
            self.controller.test_troubleshoot_template(
                "page_exit",
                0,
                self.controller.config.page_exit_template_path,
            )
            return
        self.controller.test_troubleshoot_template(
            "page_ready",
            0,
            self.controller.config.page_ready_template_path,
        )

    def _web_test_enabled_slots_requested(self) -> None:
        for index, slot in enumerate(self.controller.config.bot_action_slots):
            if bool(getattr(slot, "enabled", False)):
                self.controller.test_bot_action_slot(index)
                return
        self._show_bot_actions_error("No enabled bot action slots to test.")

    def _handle_web_raid_now_requested(self) -> None:
        profile_directory = self._first_raid_now_profile_directory()
        if profile_directory is None:
            self.controller.errorRaised.emit("No healthy raid profile is available")
            return
        self._handle_raid_now_requested(profile_directory)

    # ── Controller signals ────────────────────────────────────────────────────

    def _connect_controller_signals(self) -> None:
        self.controller.botStateChanged.connect(self._update_bot_state)
        self.controller.connectionStateChanged.connect(self._update_connection_state)
        self.controller.statsChanged.connect(self._apply_stats_state)
        self.controller.activityAdded.connect(self._append_activity_entry)
        self.controller.errorRaised.connect(self._handle_controller_error)
        self.controller.configChanged.connect(self._sync_config)
        self.controller.automationQueueStateChanged.connect(
            self._handle_automation_queue_state_changed
        )
        self.controller.botActionRunEvent.connect(self._handle_bot_actions_run_event)

    def _update_bot_state(self, state: str) -> None:
        previous_state = self.bot_state
        self.bot_state = state
        if state in {"starting", "running"} and previous_state not in {"starting", "running"}:
            self._bot_session_started_at = datetime.now()
        self._refresh_displayed_bot_state()
        self._sync_dashboard_action_buttons()
        self._refresh_dashboard_metrics()
        self._refresh_web_dashboard()

    def _refresh_displayed_bot_state(self) -> None:
        if self._automation_queue_state == "suspended":
            display_state = "Paused"
            variant = "active"
        elif self._automation_queue_state == "paused":
            display_state = "Stopped"
            variant = "error"
        else:
            display_state = _format_status_caption(self.bot_state)
            variant = _bot_state_variant(self.bot_state)
        for label in (self.bot_state_label,):
            label.setText(display_state)
            _apply_variant(label, variant)
        _apply_variant(self._bot_dot, variant)

    def _update_connection_state(self, state: str) -> None:
        self.connection_state = state
        variant = _connection_state_variant(state)
        display_state = _format_status_caption(state)
        for label in (self.connection_state_label,):
            label.setText(display_state)
            _apply_variant(label, variant)
        _apply_variant(self._conn_dot, variant)
        self._update_raid_now_buttons_enabled_state()
        self._refresh_web_dashboard()

    def _handle_controller_error(self, message: str) -> None:
        self.last_error_label.setText(message)
        self._show_bot_actions_error(message)
        pending_profile_directory = self._raid_now_pending_profile_directory
        started_profile_directory = self._raid_now_started_profile_directory
        feedback_profile_directory = pending_profile_directory or started_profile_directory
        if feedback_profile_directory is None:
            self._refresh_web_dashboard()
            return
        card = self.raid_profile_cards.get(feedback_profile_directory)
        if card is not None:
            card.reset_raid_now_button()
            card.show_raid_now_feedback(message)
        self._raid_now_feedback_by_profile[feedback_profile_directory] = str(message)
        self._raid_now_pending_profile_directory = None
        self._raid_now_started_profile_directory = None
        self._refresh_web_dashboard()

    def _set_button_variant(self, button: QPushButton, variant: str) -> None:
        if button.property("variant") == variant:
            return
        button.setProperty("variant", variant)
        button.style().unpolish(button)
        button.style().polish(button)

    def _sync_dashboard_action_buttons(self) -> None:
        if self.bot_state in {"starting", "running"}:
            self._set_button_variant(self.start_button, "primary")
            self.start_button.set_pulse_enabled(False)
            self._set_button_variant(self.stop_button, "secondary")
            return
        self._set_button_variant(self.start_button, "secondary")
        self.start_button.set_pulse_enabled(not self._performance_mode_enabled())
        self._set_button_variant(self.stop_button, "danger")

    def _performance_mode_enabled(self) -> bool:
        return bool(getattr(self.controller.config, "performance_mode_enabled", False))

    def _sync_performance_mode(self) -> None:
        enabled = self._performance_mode_enabled()
        self.setProperty("performanceMode", enabled)
        for button in (
            getattr(self, "start_button", None),
            getattr(self, "restart_all_profiles_button", None),
        ):
            if hasattr(button, "set_pulse_enabled"):
                button.set_pulse_enabled(not enabled)
        self._sync_dashboard_action_buttons()

    def _apply_state(
        self, state: DesktopAppState, *, include_activity: bool = False
    ) -> None:
        self._latest_state = state
        self._automation_queue_state = str(getattr(state, "automation_queue_state", "idle") or "idle")
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
        self.last_successful_label.setText(
            self._format_last_successful_raid(state.last_successful_raid_open_at)
        )
        self.last_error_label.setText(state.last_error or "")
        self._refresh_dashboard_metrics()
        self._sync_raid_profile_cards(self.controller.config, state)
        if include_activity:
            self._populate_activity_list(state.activity)
        self._refresh_web_dashboard()

    def _apply_stats_state(self, state: DesktopAppState) -> None:
        self._apply_state(state, include_activity=False)

    def _append_activity_entry(self, entry) -> None:
        if not self._should_display_activity(entry.action):
            return
        if hasattr(self._latest_state, "activity"):
            self._latest_state.activity.append(entry)
        self._insert_activity_entry(entry, at_top=True)
        self._refresh_web_dashboard()

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
        return action not in {
            "duplicate",
            "sender_rejected",
            "chat_rejected",
            "not_a_raid",
        }

    def _activity_reason_text(self, action: str, reason: str | None) -> str | None:
        normalized_reason = str(reason or "").strip()
        if not normalized_reason:
            return None
        if normalized_reason.lower() in {
            action.lower(),
            action.replace("_", " ").lower(),
            self._format_activity_action(action).lower(),
            "opened",
            "done",
            "page ready",
            "page_ready",
            "automation_started",
            "automation_succeeded",
            "automation_failed",
            "session_closed",
        }:
            return None
        return normalized_reason

    def _insert_activity_entry(self, entry, *, at_top: bool) -> None:
        tone = self._activity_tone(entry.action)
        list_item = QListWidgetItem(self._format_activity(entry))
        row_widget = ActivityFeedRow(
            title=self._format_activity_action(entry.action),
            tone=tone,
            timestamp_text=self._format_activity_timestamp(entry.timestamp),
            url=getattr(entry, "url", None),
            reason_text=self._activity_reason_text(
                entry.action,
                getattr(entry, "reason", None),
            ),
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

    def _refresh_dashboard_metrics(self) -> None:
        successful_runs = self._recent_successful_profile_runs(self._latest_state)
        resets = self._latest_state.dashboard_metric_resets
        completion_runs = self._successful_runs_after(
            successful_runs,
            resets.avg_completion_reset_at,
        )
        rate_runs = self._successful_runs_after(
            successful_runs,
            resets.avg_raids_per_hour_reset_at,
        )
        completion_durations = [
            duration
            for _timestamp, duration in completion_runs
            if duration is not None and duration >= 0
        ]
        displayed_completed = max(
            0,
            self._latest_state.raids_completed - resets.raids_completed_offset,
        )
        displayed_failed = max(
            0,
            self._latest_state.raids_failed - resets.raids_failed_offset,
        )
        success_rate_completed = max(
            0,
            self._latest_state.raids_completed - resets.success_rate_completed_offset,
        )
        success_rate_failed = max(
            0,
            self._latest_state.raids_failed - resets.success_rate_failed_offset,
        )
        self.raid_activity_chart.set_series(
            self._build_recent_raid_activity_series(successful_runs)
        )
        self.raids_completed_label.setText(str(displayed_completed))
        self.raids_failed_label.setText(str(displayed_failed))
        self.avg_raid_completion_time_label.setText(
            self._format_average_completion_time(completion_durations)
        )
        self.average_raids_per_hour_label.setText(
            self._format_raids_per_hour([timestamp for timestamp, _duration in rate_runs])
        )
        self.sidebar_success_rate_label.setText(
            self._format_success_rate(
                success_rate_completed,
                success_rate_failed,
            )
        )
        self.sidebar_uptime_label.setText(
            self._format_uptime(resets.uptime_reset_at)
        )

    def _summarize_recent_raid_activity(
        self, state: DesktopAppState
    ) -> tuple[int, list[float]]:
        successful_runs = self._recent_successful_profile_runs(state)
        completion_durations = [
            duration
            for _timestamp, duration in successful_runs
            if duration is not None and duration >= 0
        ]
        return len(successful_runs), completion_durations

    def _recent_successful_profile_runs(
        self,
        state: DesktopAppState,
    ) -> list[tuple[datetime, float | None]]:
        successful_profile_runs = list(getattr(state, "successful_profile_runs", []) or [])
        return self._filter_recent_successful_profile_runs(successful_profile_runs)

    def _successful_runs_after(
        self,
        successful_runs: list[tuple[datetime, float | None]],
        reset_at: datetime | None,
    ) -> list[tuple[datetime, float | None]]:
        if reset_at is None:
            return successful_runs
        return [
            (timestamp, duration)
            for timestamp, duration in successful_runs
            if timestamp >= reset_at
        ]

    def _collect_recent_successful_profile_runs(
        self, entries: list
    ) -> list[tuple[datetime, float | None]]:
        pending_starts: dict[tuple[str, str | None], deque[datetime]] = defaultdict(
            deque
        )
        successful_runs: list[tuple[datetime, float | None]] = []
        now = datetime.now()
        cutoff = now - timedelta(hours=24)
        future_cutoff = now + timedelta(minutes=5)
        for entry in entries:
            timestamp = getattr(entry, "timestamp", None)
            url = getattr(entry, "url", None)
            if not isinstance(timestamp, datetime):
                continue
            if timestamp > future_cutoff:
                continue
            action = getattr(entry, "action", "")
            profile_directory = getattr(entry, "profile_directory", None)
            legacy_key = (url, "__legacy_executor__") if url else None
            if action == "executor_succeeded":
                duration: float | None = None
                if legacy_key is not None and pending_starts[legacy_key]:
                    started_at = pending_starts[legacy_key].popleft()
                    if timestamp >= started_at:
                        duration = (timestamp - started_at).total_seconds()
                if timestamp >= cutoff:
                    successful_runs.append((timestamp, duration))
                continue
            if not url:
                continue
            key = (url, profile_directory)
            if action in {"browser_session_opened", "raid_detected"}:
                pending_starts[legacy_key].append(timestamp)
                continue
            if action == "automation_started":
                pending_starts[key].append(timestamp)
                continue
            if action == "executor_failed":
                if pending_starts[legacy_key]:
                    pending_starts[legacy_key].popleft()
                continue
            if action == "automation_failed":
                if pending_starts[key]:
                    pending_starts[key].popleft()
                continue
            if action != "automation_succeeded":
                continue
            duration: float | None = None
            if pending_starts[key]:
                started_at = pending_starts[key].popleft()
                if timestamp >= started_at:
                    duration = (timestamp - started_at).total_seconds()
            if timestamp >= cutoff:
                successful_runs.append((timestamp, duration))
        return successful_runs

    def _filter_recent_successful_profile_runs(
        self,
        entries: list[SuccessfulProfileRun],
    ) -> list[tuple[datetime, float | None]]:
        successful_runs: list[tuple[datetime, float | None]] = []
        now = datetime.now()
        cutoff = now - timedelta(hours=24)
        future_cutoff = now + timedelta(minutes=5)
        for entry in entries:
            timestamp = getattr(entry, "timestamp", None)
            if not isinstance(timestamp, datetime):
                continue
            if timestamp < cutoff or timestamp > future_cutoff:
                continue
            successful_runs.append((timestamp, getattr(entry, "duration_seconds", None)))
        return successful_runs

    def _build_recent_raid_activity_series(
        self,
        successful_runs: list[tuple[datetime, float | None]],
    ) -> list[int]:
        if successful_runs and not isinstance(successful_runs[0], tuple):
            successful_runs = self._collect_recent_successful_profile_runs(
                successful_runs
            )
        series = [0] * 24
        current_hour = datetime.now().replace(minute=0, second=0, microsecond=0)
        for timestamp, _duration in successful_runs:
            bucket_hour = timestamp.replace(minute=0, second=0, microsecond=0)
            delta_hours = int((current_hour - bucket_hour).total_seconds() // 3600)
            if 0 <= delta_hours < 24:
                series[23 - delta_hours] += 1
        chart_mode = self._raid_activity_chart_mode()
        if chart_mode == RAID_ACTIVITY_MODE_PER_HOUR:
            return series
        if chart_mode == RAID_ACTIVITY_MODE_ROLLING_60M:
            now = datetime.now().replace(second=0, microsecond=0)
            aligned_now = now - timedelta(minutes=now.minute % 5)
            checkpoints = [
                aligned_now - timedelta(hours=24) + timedelta(minutes=5 * index)
                for index in range(289)
            ]
            rolling_series: list[int] = []
            for checkpoint in checkpoints:
                window_start = checkpoint - timedelta(minutes=60)
                rolling_series.append(
                    sum(
                        1
                        for timestamp, _duration in successful_runs
                        if window_start < timestamp <= checkpoint
                    )
                )
            return rolling_series
        if chart_mode == RAID_ACTIVITY_MODE_SMOOTHED_RATE:
            return _smooth_hourly_activity_series(series)
        running_total = 0
        for index, value in enumerate(series):
            running_total += value
            series[index] = running_total
        return series

    def _raid_activity_chart_mode(self) -> str:
        raw_value = os.environ.get(
            "RAIDBOT_CHART_MODE", RAID_ACTIVITY_MODE_SMOOTHED_RATE
        )
        normalized = raw_value.strip().lower().replace("-", "_")
        if normalized == RAID_ACTIVITY_MODE_SMOOTHED_RATE:
            return RAID_ACTIVITY_MODE_SMOOTHED_RATE
        if normalized == RAID_ACTIVITY_MODE_ROLLING_60M:
            return RAID_ACTIVITY_MODE_ROLLING_60M
        if normalized == RAID_ACTIVITY_MODE_PER_HOUR:
            return RAID_ACTIVITY_MODE_PER_HOUR
        return RAID_ACTIVITY_MODE_CUMULATIVE

    def _raid_activity_subtitle_text(self) -> str:
        chart_mode = self._raid_activity_chart_mode()
        labels = {
            RAID_ACTIVITY_MODE_SMOOTHED_RATE: "Last 24 Hours | Smoothed Rate",
            RAID_ACTIVITY_MODE_ROLLING_60M: "Last 24 Hours | Rolling 60m",
            RAID_ACTIVITY_MODE_PER_HOUR: "Last 24 Hours | Per Hour",
            RAID_ACTIVITY_MODE_CUMULATIVE: "Last 24 Hours | Cumulative",
        }
        return labels.get(chart_mode, labels[RAID_ACTIVITY_MODE_SMOOTHED_RATE])
        if chart_mode == RAID_ACTIVITY_MODE_SMOOTHED_RATE:
            return "Last 24 Hours · Smoothed Rate"
        if chart_mode == RAID_ACTIVITY_MODE_ROLLING_60M:
            return "Last 24 Hours · Rolling 60m"
        if chart_mode == RAID_ACTIVITY_MODE_PER_HOUR:
            return "Last 24 Hours · Per Hour"
        return "Last 24 Hours | Cumulative"

    def _format_average_completion_time(self, durations: list[float]) -> str:
        if not durations:
            return "0s"
        average_seconds = sum(durations) / len(durations)
        return f"{round(average_seconds)}s"

    def _format_raids_per_hour(self, timestamps: list[datetime]) -> str:
        if not timestamps:
            return "0.0/hr"
        occupied_hours = {
            timestamp.replace(minute=0, second=0, microsecond=0)
            for timestamp in timestamps
        }
        raids_per_hour = len(timestamps) / max(len(occupied_hours), 1)
        precision = 2 if raids_per_hour < 1 else 1
        return f"{raids_per_hour:.{precision}f}/hr"

    def _format_success_rate(self, completed_count: int, failed_count: int) -> str:
        total = completed_count + failed_count
        if total <= 0:
            return "0%"
        return f"{(completed_count / total) * 100:.1f}%"

    def _format_last_successful_raid(
        self,
        value: str | datetime | None,
        *,
        now: datetime | None = None,
    ) -> str:
        if value in {None, ""}:
            return "No successful raid yet"
        if isinstance(value, datetime):
            timestamp = value
        else:
            try:
                timestamp = datetime.fromisoformat(str(value))
            except (TypeError, ValueError):
                return str(value)
        reference = now or datetime.now()
        if timestamp.date() == reference.date():
            return f"Today, {timestamp:%H:%M}"
        if timestamp.date() == (reference - timedelta(days=1)).date():
            return f"Yesterday, {timestamp:%H:%M}"
        if timestamp.year == reference.year:
            return f"{timestamp:%b %d, %H:%M}"
        return f"{timestamp:%b %d, %Y, %H:%M}"

    def _format_uptime(self, reset_at: datetime | None = None) -> str:
        baseline = reset_at or self._bot_session_started_at
        if baseline is None:
            return "—"
        elapsed = max(datetime.now() - baseline, timedelta())
        total_minutes = int(elapsed.total_seconds() // 60)
        hours, minutes = divmod(total_minutes, 60)
        if hours > 0:
            return f"{hours}h {minutes}m"
        return f"{minutes}m"

    def _tray_icon(self) -> QIcon:
        icon = app_icon()
        if not icon.isNull():
            return icon
        return QIcon()

    def _ensure_window_icon(self) -> None:
        if not self.windowIcon().isNull():
            return
        icon = app_icon()
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
                self.setGeometry(self._normalize_to_available_screen(restore_geometry))
            else:
                self.ensure_visible_on_screen()
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
            self._reflow_raid_profile_cards()

    def moveEvent(self, event) -> None:
        super().moveEvent(event)
        if not self.isMinimized():
            self._remember_restore_geometry()

    def _available_screen_geometries(self) -> list[QRect]:
        instance = QApplication.instance()
        screens = instance.screens() if instance is not None else []
        geometries: list[QRect] = []
        for screen in screens:
            geometry = screen.availableGeometry()
            if not geometry.isNull():
                geometries.append(QRect(geometry))
        return geometries

    def _primary_screen_geometry(self) -> QRect | None:
        instance = QApplication.instance()
        if instance is None:
            return None
        screen = instance.primaryScreen()
        if screen is None:
            return None
        geometry = screen.availableGeometry()
        return QRect(geometry) if not geometry.isNull() else None

    def _normalize_to_available_screen(self, rect: QRect) -> QRect:
        target = QRect(rect)
        screens = self._available_screen_geometries()
        if target.isNull() or not screens:
            return target
        if any(target.intersects(screen_rect) for screen_rect in screens):
            return target
        primary = self._primary_screen_geometry() or screens[0]
        width = min(target.width(), primary.width())
        height = min(target.height(), primary.height())
        x = primary.x() + max(0, (primary.width() - width) // 2)
        y = primary.y() + max(0, (primary.height() - height) // 2)
        return QRect(x, y, width, height)

    def ensure_visible_on_screen(self) -> None:
        normalized = self._normalize_to_available_screen(self.geometry())
        if normalized != self.geometry():
            self.setGeometry(normalized)
        if self._restore_geometry is not None and not self._restore_geometry.isNull():
            self._restore_geometry = self._normalize_to_available_screen(
                self._restore_geometry
            )

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if self.isMinimized():
            self._remember_restore_geometry()
            self.handle_minimize_requested()
            self.setWindowState(Qt.WindowState.WindowNoState)

    def closeEvent(self, event) -> None:
        if not self._should_wait_for_shutdown():
            self._close_hotkey_registrar()
            event.accept()
            return
        if not self.confirm_close():
            event.ignore()
            return
        if self.controller.stop_bot_and_wait():
            self._close_hotkey_registrar()
            event.accept()
            return
        event.ignore()

    def _close_hotkey_registrar(self) -> None:
        if self._hotkey_registrar is None:
            return
        self._hotkey_registrar.close()
        self._hotkey_registrar = None

    def _default_hotkey_registrar_factory(self):
        if os.name != "nt":
            return None
        application = QApplication.instance()
        install_filter = (
            application.installNativeEventFilter if application is not None else None
        )
        remove_filter = (
            application.removeNativeEventFilter if application is not None else None
        )
        return WindowsGlobalHotkeyRegistrar(
            install_native_event_filter=install_filter,
            remove_native_event_filter=remove_filter,
        )

    def _sync_pause_resume_hotkey(self, config) -> None:
        if self._hotkey_registrar is None or not hasattr(
            self.controller,
            "toggle_pause_resume",
        ):
            return
        try:
            self._hotkey_registrar.set_hotkey(
                config.pause_resume_hotkey,
                self.controller.toggle_pause_resume,
            )
        except Exception as exc:
            self._handle_controller_error(str(exc))

    def _should_wait_for_shutdown(self) -> bool:
        if hasattr(self.controller, "is_bot_active"):
            return bool(self.controller.is_bot_active())
        return self.bot_state in {"starting", "running", "stopping"}

    def _confirm_close(self) -> bool:
        if self.isVisible() and not self.isMinimized():
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
        self._prepare_close_confirmation_window()
        return self._show_centered_close_confirmation()

    def _prepare_close_confirmation_window(self) -> None:
        if hasattr(self, "restore_from_tray"):
            self.restore_from_tray()
            return
        self.show()
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _show_centered_close_confirmation(self) -> bool:
        message_box = QMessageBox(self)
        message_box.setWindowTitle("Stop bot and exit")
        message_box.setText("The bot is still running. Stop it and close the app?")
        message_box.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        message_box.setDefaultButton(QMessageBox.StandardButton.No)
        self._center_dialog_on_primary_screen(message_box)
        return message_box.exec() == QMessageBox.StandardButton.Yes

    def _center_dialog_on_primary_screen(self, dialog) -> None:
        dialog.adjustSize()
        frame = dialog.frameGeometry()
        if frame.isNull() or frame.width() <= 0 or frame.height() <= 0:
            size_hint = dialog.sizeHint() if hasattr(dialog, "sizeHint") else QSize(0, 0)
            frame = QRect(0, 0, size_hint.width(), size_hint.height())
        if frame.isNull() or frame.width() <= 0 or frame.height() <= 0:
            return
        primary = self._primary_screen_geometry()
        if primary is None or primary.isNull():
            return
        target = QRect(
            primary.x() + max(0, (primary.width() - frame.width()) // 2),
            primary.y() + max(0, (primary.height() - frame.height()) // 2),
            frame.width(),
            frame.height(),
        )
        dialog.move(target.x(), target.y())

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

    def _refresh_available_profiles_for_settings(self) -> list[ChromeProfile]:
        profiles = self._normalize_chrome_profiles(self.available_profiles_loader())
        self.settings_page.set_available_profiles(profiles)
        return profiles

    def _normalize_chrome_profiles(self, profiles) -> list[ChromeProfile]:
        normalized_profiles: list[ChromeProfile] = []
        for profile in profiles:
            if isinstance(profile, ChromeProfile):
                normalized_profiles.append(profile)
                continue
            directory_name = str(profile).strip()
            if not directory_name:
                continue
            normalized_profiles.append(
                ChromeProfile(directory_name=directory_name, label=directory_name)
            )
        return normalized_profiles

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

    def _load_available_chats(self) -> list[AccessibleChat]:
        try:
            service = TelegramSetupService(
                api_id=self.controller.config.telegram_api_id,
                api_hash=self.controller.config.telegram_api_hash,
                session_path=self.controller.config.telegram_session_path,
            )
            chats = asyncio.run(
                asyncio.wait_for(service.list_accessible_chats(), timeout=1.0)
            )
        except Exception:
            return []
        return list(chats)

    def _chat_source_signature(self, config) -> tuple[int, str, Path]:
        return (
            int(config.telegram_api_id),
            str(config.telegram_api_hash),
            Path(config.telegram_session_path),
        )

    def _apply_settings_config(self, config) -> None:
        try:
            self.controller.apply_config(config)
        except Exception as exc:
            self.settings_page.show_error(str(exc))
            return
        self.settings_page.show_success("Settings saved.")

    def _scan_allowed_senders(self, button, chat_ids) -> None:
        QApplication.processEvents()
        try:
            candidates = list(self.controller.infer_recent_sender_candidates(chat_ids))
        except Exception as exc:
            self.settings_page.show_error(str(exc))
        else:
            if not candidates:
                self.settings_page.show_error("No recent sender candidates found.")
                return
            selected_entries = [
                str(entry).strip()
                for entry in self.sender_candidate_picker(candidates)
                if str(entry).strip()
            ]
            if not selected_entries:
                return
            self.settings_page.append_allowed_sender_entries(selected_entries)
            self.settings_page.show_success("Sender scan complete.")
        finally:
            try:
                self.settings_page.set_sender_scan_button_busy(button, False)
            except RuntimeError:
                pass

    def _pick_sender_candidates(self, candidates) -> list[str]:
        dialog = QDialog(self)
        dialog.setWindowTitle("Scan Allowed Senders")
        dialog.setModal(True)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        help_label = QLabel("Select any raid senders you want to append.")
        help_label.setWordWrap(True)
        layout.addWidget(help_label)
        candidate_list = QListWidget(dialog)
        candidate_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        for candidate in candidates:
            item = QListWidgetItem(str(candidate.label).strip())
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            candidate_list.addItem(item)
        layout.addWidget(candidate_list)
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            parent=dialog,
        )
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)
        if dialog.exec() != int(QDialog.DialogCode.Accepted):
            return []
        selected_entries: list[str] = []
        for index in range(candidate_list.count()):
            item = candidate_list.item(index)
            if item.checkState() == Qt.CheckState.Checked:
                entry = item.text().strip()
                if entry and entry not in selected_entries:
                    selected_entries.append(entry)
        return selected_entries

    def _pick_profile_action_overrides(
        self,
        profile: RaidProfileConfig,
        slots: tuple[BotActionSlotConfig, ...],
    ) -> dict[str, bool] | None:
        slots_by_key = {slot.key: slot for slot in slots}
        dialog = QDialog(self)
        dialog.setWindowTitle(f"{profile.label} Actions")
        dialog.setModal(True)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        checkbox_map: dict[str, tuple[QCheckBox, bool]] = {}
        for field_name, label, slot_key in raid_profile_action_specs():
            slot = slots_by_key.get(slot_key)
            checkbox = QCheckBox(label, dialog)
            action_available = slot is not None
            checkbox.setChecked(
                bool(getattr(profile, field_name, True)) if action_available else False
            )
            checkbox.setEnabled(action_available)
            if not action_available:
                checkbox.setToolTip("This action slot is not available.")
            layout.addWidget(checkbox)
            checkbox_map[field_name] = (checkbox, action_available)
        warmup_checkbox = QCheckBox("Warm me up baby", dialog)
        warmup_checkbox.setChecked(bool(getattr(profile, "warmup_enabled", False)))
        layout.addWidget(warmup_checkbox)

        def sync_action_checkbox_enabled_state() -> None:
            warmup_enabled = warmup_checkbox.isChecked()
            for checkbox, globally_enabled in checkbox_map.values():
                checkbox.setEnabled(bool(globally_enabled) and not warmup_enabled)

        warmup_checkbox.toggled.connect(sync_action_checkbox_enabled_state)
        sync_action_checkbox_enabled_state()
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            parent=dialog,
        )
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)
        if dialog.exec() != int(QDialog.DialogCode.Accepted):
            return None
        return {
            field_name: (
                checkbox.isChecked()
                if globally_enabled
                else bool(getattr(profile, field_name, True))
            )
            for field_name, (checkbox, globally_enabled) in checkbox_map.items()
        } | {"warmup_enabled": warmup_checkbox.isChecked()}

    def _pick_raid_profile_to_add(
        self,
        profiles: list[ChromeProfile],
    ) -> ChromeProfile | None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Add Raid Profile")
        dialog.setModal(True)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        helper_label = QLabel("Select the Chrome profile to add for raiding.", dialog)
        helper_label.setWordWrap(True)
        helper_label.setProperty("muted", "true")
        layout.addWidget(helper_label)
        profile_list = QListWidget(dialog)
        for profile in profiles:
            item = QListWidgetItem(f"{profile.label} [{profile.directory_name}]")
            item.setData(Qt.ItemDataRole.UserRole, profile)
            profile_list.addItem(item)
        if profile_list.count():
            profile_list.setCurrentRow(0)
        layout.addWidget(profile_list)
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            parent=dialog,
        )
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)
        profile_list.itemDoubleClicked.connect(lambda _item: dialog.accept())
        if dialog.exec() != int(QDialog.DialogCode.Accepted):
            return None
        item = profile_list.currentItem()
        if item is None:
            return None
        selected_profile = item.data(Qt.ItemDataRole.UserRole)
        return selected_profile if isinstance(selected_profile, ChromeProfile) else None

    def _configure_profile_action_overrides(self, profile_directory: str) -> None:
        profile = next(
            (
                candidate
                for candidate in self.controller.config.raid_profiles
                if candidate.profile_directory == profile_directory
            ),
            None,
        )
        if profile is None:
            return
        selection = self.profile_action_picker(
            profile,
            self.controller.config.bot_action_slots,
        )
        if not selection:
            return
        self.controller.set_raid_profile_action_overrides(
            profile_directory,
            reply_enabled=bool(selection["reply_enabled"]),
            like_enabled=bool(selection["like_enabled"]),
            repost_enabled=bool(selection["repost_enabled"]),
            bookmark_enabled=bool(selection["bookmark_enabled"]),
            warmup_enabled=bool(selection["warmup_enabled"]),
        )

    def _capture_bot_action_slot(self, slot_index: int) -> None:
        slot = self.controller.config.bot_action_slots[slot_index]
        try:
            template_path = self.slot_capture_service.capture_slot(
                slot, existing_path=slot.template_path,
            )
            self.controller.set_bot_action_slot_template_path(slot_index, template_path)
            refreshed_slots = list(self.controller.config.bot_action_slots)
            refreshed_slots[slot_index] = replace(
                refreshed_slots[slot_index],
                template_path=template_path,
            )
            self.bot_actions_page.set_slots(tuple(refreshed_slots))
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
            self.bot_actions_page.set_page_ready_template_path(template_path)
            if template_path is not None:
                self._bot_actions_status_text = "Page Ready: image saved"
                self._bot_actions_last_error_text = None
                self._bot_actions_current_slot_text = None
                self._render_bot_actions_status()
        except Exception as exc:
            self._show_bot_actions_error(str(exc))

    def _capture_page_exit_template(self) -> None:
        try:
            template_path = self.slot_capture_service.capture_to_path(
                Path("bot_actions/page_exit.png"),
                existing_path=self.controller.config.page_exit_template_path,
            )
            self.controller.set_page_exit_template_path(template_path)
            self.bot_actions_page.set_page_exit_template_path(template_path)
            if template_path is not None:
                self._bot_actions_status_text = "Page Exit: image saved"
                self._bot_actions_last_error_text = None
                self._bot_actions_current_slot_text = None
                self._render_bot_actions_status()
        except Exception as exc:
            self._show_bot_actions_error(str(exc))

    def _capture_troubleshoot_template(self, group_key: str, item_index: int) -> None:
        try:
            template_path = self.slot_capture_service.capture_to_path(
                self._troubleshoot_template_relative_path(group_key, item_index),
                existing_path=self._troubleshoot_template_path(group_key, item_index),
            )
            self.bot_actions_page.set_troubleshoot_template_path(
                group_key,
                item_index,
                template_path,
            )
            if template_path is not None:
                self._bot_actions_status_text = (
                    f"{self._format_troubleshoot_name(group_key, item_index)}: image saved"
                )
                self._bot_actions_last_error_text = None
                self._bot_actions_current_slot_text = None
                self._render_bot_actions_status()
            self._refresh_web_dashboard()
        except Exception as exc:
            self._show_bot_actions_error(str(exc))

    def _test_troubleshoot_template(self, group_key: str, item_index: int) -> None:
        self.controller.test_troubleshoot_template(
            group_key,
            item_index,
            self._troubleshoot_template_path(group_key, item_index),
        )

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
        current_slot = self.controller.config.bot_action_slots[0]
        existing_finish_path = (
            dialog.finish_template_path
            if dialog is not None
            else current_slot.finish_template_path
        )
        try:
            finish_template_path = self.slot_capture_service.capture_to_path(
                Path("bot_actions/slot_1_r_finish.png"),
                existing_path=existing_finish_path,
            )
            if dialog is not None:
                dialog.finish_template_path = finish_template_path
                dialog.finish_image_status_label.setText(
                    str(finish_template_path)
                    if finish_template_path is not None
                    else "No finish image"
                )
                updated_slot = dialog.build_updated_slot()
                presets = updated_slot.presets
                updated_finish_template_path = updated_slot.finish_template_path
            else:
                presets = current_slot.presets
                updated_finish_template_path = finish_template_path
            self.controller.set_bot_action_slot_1_presets(
                presets=presets,
                finish_template_path=updated_finish_template_path,
            )
            refreshed_slots = list(self.controller.config.bot_action_slots)
            refreshed_slots[0] = replace(
                refreshed_slots[0],
                presets=presets,
                finish_template_path=updated_finish_template_path,
            )
            self.bot_actions_page.set_slots(tuple(refreshed_slots))
            if finish_template_path is not None:
                self._bot_actions_status_text = "Slot 1 (R): finish image saved"
                self._bot_actions_last_error_text = None
                self._bot_actions_current_slot_text = None
                self._render_bot_actions_status()
            self._refresh_web_dashboard()
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
        self._sync_pause_resume_hotkey(config)
        if hasattr(self, "restart_all_raid_checkbox"):
            previous = self.restart_all_raid_checkbox.blockSignals(True)
            self.restart_all_raid_checkbox.setChecked(
                bool(getattr(config, "raid_on_restart_enabled", False))
            )
            self.restart_all_raid_checkbox.blockSignals(previous)
        chat_source_signature = self._chat_source_signature(config)
        if chat_source_signature != self._available_chats_signature:
            self._available_chats_cache = list(self.available_chats_loader())
            self._available_chats_signature = chat_source_signature
        self.settings_page.set_available_chats(self._available_chats_cache)
        self.bot_actions_page.set_page_ready_template_path(config.page_ready_template_path)
        self.bot_actions_page.set_page_exit_template_path(config.page_exit_template_path)
        self.bot_actions_page.set_slots(config.bot_action_slots)
        self._sync_troubleshoot_templates()
        self.bot_actions_page.set_slot_1_finish_delay_seconds(
            config.slot_1_finish_delay_seconds
        )
        self.bot_actions_page.set_page_ready_timeout_seconds(
            getattr(config, "page_ready_timeout_seconds", 12.0)
        )
        self._sync_performance_mode()
        self._sync_raid_profile_cards(config, self._latest_state)
        self._refresh_web_dashboard()

    def _sync_raid_profile_cards(self, config, state: DesktopAppState) -> None:
        for card in self._raid_profile_card_widgets:
            card.deleteLater()
        self._raid_profile_card_widgets = []
        while self.profile_cards_layout.count():
            item = self.profile_cards_layout.takeAt(0)
        states_by_directory = {
            ps.profile_directory: ps
            for ps in getattr(state, "raid_profile_states", ())
        }
        self.raid_profile_cards = {}
        for profile in config.raid_profiles:
            card = RaidProfileCard(
                profile.profile_directory, parent=self.profile_cards_container
            )
            card.raidNowRequested.connect(self._handle_raid_now_requested)
            card.resetProfileRequested.connect(self.controller.reset_raid_profile)
            card.actionOverridesRequested.connect(
                self._configure_profile_action_overrides
            )
            card.apply_state(
                profile,
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
            card.set_execution_overlay_state(self._raid_profile_execution_overlay_state())
            card.set_raid_now_enabled(self.connection_state == "connected")
            self.raid_profile_cards[profile.profile_directory] = card
            self._raid_profile_card_widgets.append(card)
        self._reflow_raid_profile_cards()

    def _update_raid_now_buttons_enabled_state(self) -> None:
        enabled = self.connection_state == "connected"
        for card in self.raid_profile_cards.values():
            card.set_raid_now_enabled(enabled)

    def _handle_raid_now_requested(self, profile_directory: str) -> None:
        self._raid_now_pending_profile_directory = str(profile_directory)
        self._raid_now_started_profile_directory = None
        self._raid_now_feedback_by_profile.pop(str(profile_directory), None)
        card = self.raid_profile_cards.get(profile_directory)
        if card is not None:
            card.clear_raid_now_feedback()
            card.set_raid_now_busy("Fetching...")
        self.controller.run_raid_now_for_profile(profile_directory)
        self._refresh_web_dashboard()

    def _reflow_raid_profile_cards(self) -> None:
        if not hasattr(self, "profile_cards_layout"):
            return
        while self.profile_cards_layout.count():
            self.profile_cards_layout.takeAt(0)
        if not self._raid_profile_card_widgets:
            self._profile_card_columns = 0
            return

        container_width = self.profile_cards_container.contentsRect().width()
        if container_width <= 0:
            container_width = max(1, self.profiles_panel.width() - 48)
        sample_card = self._raid_profile_card_widgets[0]
        card_width = max(sample_card.minimumWidth(), sample_card.sizeHint().width())
        spacing = max(0, self.profile_cards_layout.horizontalSpacing())
        columns = max(1, (container_width + spacing) // (card_width + spacing))

        for column in range(max(self._profile_card_columns, columns) + 1):
            self.profile_cards_layout.setColumnStretch(column, 0)

        for index, card in enumerate(self._raid_profile_card_widgets):
            row = index // columns
            column = index % columns
            self.profile_cards_layout.addWidget(card, row, column)

        self.profile_cards_layout.setColumnStretch(columns, 1)
        self._profile_card_columns = columns

    def _show_bot_actions_error(self, message: str) -> None:
        self._bot_actions_last_error_text = str(message)
        self._render_bot_actions_status()

    def _handle_automation_queue_state_changed(self, state: str) -> None:
        self._automation_queue_state = str(state or "idle")
        self._update_bot_actions_queue_state(self._automation_queue_state)
        self._refresh_displayed_bot_state()
        self._refresh_raid_profile_execution_overlays()
        self._refresh_web_dashboard()

    def _raid_profile_execution_overlay_state(self) -> str:
        if self._automation_queue_state == "suspended":
            return "paused"
        if self._automation_queue_state == "paused":
            return "stopped"
        return "none"

    def _refresh_raid_profile_execution_overlays(self) -> None:
        overlay_state = self._raid_profile_execution_overlay_state()
        for card in self.raid_profile_cards.values():
            card.set_execution_overlay_state(overlay_state)

    def _update_bot_actions_queue_state(self, state: str) -> None:
        queue_status_map = {
            "queued": "Queued", "running": "Running",
            "paused": "Stopped", "suspended": "Paused", "idle": "Idle",
        }
        self._bot_actions_status_text = queue_status_map.get(str(state), "Idle")
        if state == "idle":
            self._clear_bot_actions_run_snapshot()
        self._render_bot_actions_status()

    def _handle_bot_actions_run_event(self, event: dict[str, object]) -> None:
        event_type = str(event.get("type", ""))
        event_profile_directory = event.get("profile_directory")
        if isinstance(event_profile_directory, str):
            if (
                event_type == "automation_run_started"
                and event_profile_directory == self._raid_now_pending_profile_directory
            ):
                self._raid_now_started_profile_directory = event_profile_directory
                card = self.raid_profile_cards.get(event_profile_directory)
                if card is not None:
                    card.set_raid_now_busy("Raiding...")
                    card.clear_raid_now_feedback()
                self._raid_now_feedback_by_profile.pop(event_profile_directory, None)
            elif event_type in {"automation_run_succeeded", "automation_run_failed"} and (
                event_profile_directory == self._raid_now_pending_profile_directory
                or event_profile_directory == self._raid_now_started_profile_directory
            ):
                card = self.raid_profile_cards.get(event_profile_directory)
                if card is not None:
                    card.reset_raid_now_button()
                    if event_type == "automation_run_succeeded":
                        card.clear_raid_now_feedback()
                    else:
                        message = str(
                            event.get("message")
                            or event.get("reason")
                            or "Raid NOW failed"
                        )
                        card.show_raid_now_feedback(message)
                if event_type == "automation_run_succeeded":
                    self._raid_now_feedback_by_profile.pop(event_profile_directory, None)
                else:
                    self._raid_now_feedback_by_profile[event_profile_directory] = str(
                        event.get("message")
                        or event.get("reason")
                        or "Raid NOW failed"
                    )
                self._raid_now_pending_profile_directory = None
                self._raid_now_started_profile_directory = None
        if event_type in {"slot_test_started", "slot_test_succeeded", "slot_test_failed"}:
            if event_type == "slot_test_failed":
                display_name = self._slot_test_display_name(event.get("slot_index"))
                self._bot_actions_status_text = f"{display_name}: test failed"
                self._bot_actions_last_error_text = str(
                    event.get("message") or event.get("reason") or "Slot test failed"
                )
            else:
                self._bot_actions_status_text = str(event.get("message", "Idle"))
                self._bot_actions_last_error_text = None
            self._bot_actions_current_slot_text = None
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
        self._refresh_web_dashboard()

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

    def _slot_test_display_name(self, slot_index: object) -> str:
        if isinstance(slot_index, int) and 0 <= slot_index < len(
            self.controller.config.bot_action_slots
        ):
            slot = self.controller.config.bot_action_slots[slot_index]
            return self._format_bot_action_slot(slot_index, str(slot.label))
        return "Slot test"

    def _format_troubleshoot_name(self, group_key: str, item_index: int) -> str:
        display_group = str(group_key).replace("_", " ").upper()
        return f"Troubleshoot {display_group} {item_index + 1}"

    def _capture_base_dir(self) -> Path:
        return Path(
            getattr(
                self.slot_capture_service,
                "base_dir",
                getattr(self.storage, "base_dir", Path(".")),
            )
        )

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
    ) -> Path | None:
        template_path = (
            self._capture_base_dir()
            / self._troubleshoot_template_relative_path(group_key, item_index)
        )
        return template_path if template_path.exists() else None

    def _sync_troubleshoot_templates(self) -> None:
        for group_key, boxes in self.bot_actions_page.troubleshoot_groups.items():
            for item_index, _box in enumerate(boxes):
                self.bot_actions_page.set_troubleshoot_template_path(
                    group_key,
                    item_index,
                    self._troubleshoot_template_path(group_key, item_index),
                )

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
