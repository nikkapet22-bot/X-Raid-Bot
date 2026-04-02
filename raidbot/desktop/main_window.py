from __future__ import annotations

import asyncio
import os
from collections import defaultdict, deque
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

from PySide6.QtCore import QDateTime, QMargins, QPointF, QRect, QRectF, QSignalBlocker, QSize, Qt, Signal
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
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
    QStyle,
)

from raidbot.desktop.bot_actions import BotActionsPage
from raidbot.desktop.bot_actions.page import ToggleSwitch
from raidbot.desktop.bot_actions.capture import SlotCaptureService
from raidbot.desktop.bot_actions.presets_dialog import Slot1PresetsDialog
from raidbot.desktop.branding import APP_NAME, APP_VERSION_BADGE
from raidbot.desktop.chrome_profiles import ChromeProfile, detect_chrome_environment
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
    SUCCESS,
    WARNING,
    ERROR,
    MUTED,
    TEXT,
)
from raidbot.desktop.tray import TrayController


RAID_ACTIVITY_MODE_CUMULATIVE = "cumulative"
RAID_ACTIVITY_MODE_PER_HOUR = "per_hour"
RAID_ACTIVITY_MODE_ROLLING_60M = "rolling_60m"
RAID_ACTIVITY_MODE_SMOOTHED_RATE = "smoothed_rate"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_profile_action_icon(size: int = 12, *, color: str = TEXT) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.translate(size / 2, size / 2)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(color))

    tooth_width = max(1.2, size * 0.14)
    tooth_height = max(2.0, size * 0.24)
    tooth_radius = tooth_width / 2
    tooth_offset = size * 0.28
    for index in range(8):
        painter.save()
        painter.rotate(index * 45.0)
        painter.drawRoundedRect(
            QRectF(
                -tooth_width / 2,
                -(tooth_offset + tooth_height),
                tooth_width,
                tooth_height,
            ),
            tooth_radius,
            tooth_radius,
        )
        painter.restore()

    outer_radius = size * 0.24
    inner_radius = size * 0.10
    painter.drawEllipse(QPointF(0.0, 0.0), outer_radius, outer_radius)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
    painter.drawEllipse(QPointF(0.0, 0.0), inner_radius, inner_radius)
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
    restartRequested = Signal(str)
    raidOnRestartChanged = Signal(str, bool)
    actionOverridesRequested = Signal(str)

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
        self.action_config_button = QPushButton("")
        self.action_config_button.setObjectName("profileActionConfigButton")
        self.action_config_button.setProperty("variant", "secondary")
        self.action_config_button.setFixedSize(14, 14)
        self.action_config_button.setIcon(_build_profile_action_icon())
        self.action_config_button.setIconSize(QSize(10, 10))
        self.action_config_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.action_config_button.setToolTip("Configure profile actions")
        self.action_config_button.clicked.connect(
            lambda: self.actionOverridesRequested.emit(self.profile_directory)
        )
        header_row.addWidget(self.dot_label, 0, Qt.AlignmentFlag.AlignVCenter)
        header_row.addWidget(self.title_label, 1)
        header_row.addWidget(
            self.action_config_button,
            0,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        )
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
        footer_row = QHBoxLayout()
        footer_row.setSpacing(8)
        footer_row.setContentsMargins(0, 0, 0, 0)
        self.raid_on_restart_label = QLabel("Raid on Restart")
        self.raid_on_restart_label.setObjectName("raidOnRestartLabel")
        self.raid_on_restart_label.setProperty("muted", "true")
        self.raid_on_restart_toggle = ToggleSwitch(self)
        self.raid_on_restart_toggle.setAccessibleName("Raid on Restart")
        self.raid_on_restart_toggle.toggled.connect(
            lambda checked: self.raidOnRestartChanged.emit(
                self.profile_directory,
                bool(checked),
            )
        )
        footer_row.addWidget(self.raid_on_restart_label)
        footer_row.addStretch()
        footer_row.addWidget(self.raid_on_restart_toggle, 0, Qt.AlignmentFlag.AlignRight)

        layout.addWidget(self.status_label)
        layout.addWidget(self.reason_label)
        layout.addWidget(self.restart_button)
        layout.addLayout(footer_row)
        layout.addStretch()

    def apply_state(self, profile, state: RaidProfileState) -> None:
        self.profile_directory = state.profile_directory
        self.title_label.setText(state.label)
        is_paused = not raid_profile_has_any_actions_enabled(profile)
        is_error = state.status == "red" and not is_paused
        profile_status = "paused" if is_paused else "red" if is_error else "green"

        self.setProperty("profileStatus", profile_status)
        self.style().unpolish(self)
        self.style().polish(self)

        dot_variant = "active" if is_paused else "error" if is_error else "running"
        _apply_variant(self.dot_label, dot_variant)

        self.status_label.setText(
            "Paused" if is_paused else "Needs attention" if is_error else "Healthy"
        )
        self.reason_label.setText(state.last_error or "No details available")
        if not is_error:
            self._details_visible = False
        self.reason_label.setVisible(is_error and self._details_visible)
        self.restart_button.setVisible(is_error and not is_paused)
        blocker = QSignalBlocker(self.raid_on_restart_toggle)
        self.raid_on_restart_toggle.setChecked(bool(getattr(profile, "raid_on_restart", False)))
        del blocker

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
        self.setMinimumHeight(180)
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
        self._chart_view.setBackgroundBrush(QColor("#07111f"))

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
        return QSize(360, 180)

    def chart(self) -> QChart:
        return self._chart

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._chart_view.setRubberBand(QChartView.RubberBand.NoRubberBand)

    def _should_use_spline_series(self) -> bool:
        return self._mode == RAID_ACTIVITY_MODE_SMOOTHED_RATE

    def _recreate_chart_series(self) -> None:
        line_pen = QPen(QColor("#2dd4bf"), 2.0)
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
        area_series.setBrush(QColor(45, 212, 191, 22))

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
        ("Dashboard", 0),
        ("Settings", 1),
        ("Bot Actions", 2),
    ]

    def __init__(
        self,
        *,
        badge_text: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("topTabStrip")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 0)
        layout.setSpacing(4)

        self._buttons: list[QPushButton] = []
        for label, index in self._NAV_ITEMS:
            btn = QPushButton(label)
            btn.setObjectName("shellTabButton")
            btn.clicked.connect(lambda _, i=index: self._activate(i))
            layout.addWidget(btn)
            self._buttons.append(btn)

        layout.addStretch()
        self._session_stamp_label = QLabel(badge_text or "")
        self._session_stamp_label.setObjectName("shellSessionStamp")
        self._session_stamp_label.setProperty("muted", "true")
        layout.addWidget(self._session_stamp_label, 0, Qt.AlignmentFlag.AlignRight)

        self._activate(0)

    def _activate(self, index: int) -> None:
        self._set_active_page(index)
        self.pageRequested.emit(index)

    def _set_active_page(self, index: int) -> None:
        for i, btn in enumerate(self._buttons):
            btn.setProperty("active", "true" if i == index else "false")
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
        profile_action_picker=None,
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
        self.profile_action_picker = (
            profile_action_picker or self._pick_profile_action_overrides
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
        self._raid_profile_card_widgets: list[RaidProfileCard] = []
        self._profile_card_columns = 0
        self._restore_geometry: QRect | None = None
        self._restore_was_maximized = False
        self._bot_session_started_at: datetime | None = None
        self._available_chats_signature = self._chat_source_signature(
            self.controller.config
        )
        self._available_chats_cache = list(self.available_chats_loader())

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
        self.start_button = QPushButton("Start")
        self.stop_button = QPushButton("Stop")
        self.start_button.setProperty("dashboardActionButton", "true")
        self.stop_button.setProperty("dashboardActionButton", "true")
        self.start_button.setMinimumWidth(84)
        self.stop_button.setMinimumWidth(84)
        self.start_button.clicked.connect(self.controller.start_bot)
        self.stop_button.clicked.connect(self.controller.stop_bot)

        # ── Layout ─────────────────────────────────────────────────────────────
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.top_tabs = TopTabStrip(badge_text=APP_VERSION_BADGE)
        root.addWidget(self.top_tabs)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._wrap_page(self._build_dashboard_tab()))
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
        self.bot_actions_page.slotCaptureRequested.connect(self._capture_bot_action_slot)
        self.bot_actions_page.slotTestRequested.connect(self.controller.test_bot_action_slot)
        self.bot_actions_page.slotPresetsRequested.connect(self._open_bot_action_slot_presets)
        self.bot_actions_page.slotEnabledChanged.connect(
            self.controller.set_bot_action_slot_enabled
        )
        self.bot_actions_page.slot1FinishDelayChanged.connect(
            self.controller.set_slot_1_finish_delay_seconds
        )
        self.stack.addWidget(self._wrap_page(self.bot_actions_page))

        self.top_tabs.pageRequested.connect(self.stack.setCurrentIndex)
        self.stack.currentChanged.connect(self.top_tabs.set_active_page)
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
        layout.setContentsMargins(12, 12, 12, 24)

        self.status_panel = self._build_status_panel()
        layout.addWidget(self.status_panel)

        self.profiles_panel = self._build_profiles_panel()
        layout.addWidget(self.profiles_panel)

        self.metric_cards = [
            self._build_metric_card(
                "avg_raid_completion_time",
                "AVG RAID COMPLETION TIME",
                self.avg_raid_completion_time_label,
            ),
            self._build_metric_card(
                "avg_raids_per_hour",
                "AVG RAIDS PER HOUR",
                self.average_raids_per_hour_label,
            ),
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
        header_row = QWidget()
        header_row.setObjectName("statusHeaderRow")
        header_layout = QHBoxLayout(header_row)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(12)
        header_layout.addWidget(self._build_section_title("System Status"))
        header_layout.addStretch()
        header_buttons = QWidget()
        header_buttons.setObjectName("statusHeaderButtons")
        header_buttons_layout = QHBoxLayout(header_buttons)
        header_buttons_layout.setContentsMargins(0, 0, 0, 0)
        header_buttons_layout.setSpacing(8)
        header_buttons_layout.addWidget(self.start_button)
        header_buttons_layout.addWidget(self.stop_button)
        header_layout.addWidget(header_buttons, 0, Qt.AlignmentFlag.AlignRight)
        layout.addWidget(header_row)
        layout.addWidget(self._build_divider())
        content_row = QHBoxLayout()
        content_row.setSpacing(18)

        left_column = QWidget()
        left_column.setObjectName("statusSummaryColumn")
        left_layout = QVBoxLayout(left_column)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(12)
        left_layout.addWidget(
            self._build_helper_label("Monitor bot runtime and Telegram connectivity.")
        )
        left_layout.addWidget(self._build_status_summary_card())
        left_layout.addStretch()
        content_row.addWidget(left_column, 1)

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
        content_row.addWidget(chart_card, 1)
        layout.addLayout(content_row)
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
        self.profile_cards_container = QWidget()
        self.profile_cards_container.setObjectName("profileCardsContainer")
        self.profile_cards_layout = QGridLayout(self.profile_cards_container)
        self.profile_cards_layout.setContentsMargins(0, 0, 0, 0)
        self.profile_cards_layout.setHorizontalSpacing(12)
        self.profile_cards_layout.setVerticalSpacing(12)
        layout.addWidget(self.profile_cards_container)
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
        reset_button = QPushButton("R")
        reset_button.setObjectName("metricResetButton")
        reset_button.setFixedSize(12, 12)
        reset_button.setFlat(True)
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
        previous_state = self.bot_state
        self.bot_state = state
        if state in {"starting", "running"} and previous_state not in {"starting", "running"}:
            self._bot_session_started_at = datetime.now()
        variant = _bot_state_variant(state)
        display_state = _format_status_caption(state)
        for label in (self.bot_state_label,):
            label.setText(display_state)
            _apply_variant(label, variant)
        _apply_variant(self._bot_dot, variant)
        self._sync_dashboard_action_buttons()
        self._refresh_dashboard_metrics()

    def _update_connection_state(self, state: str) -> None:
        self.connection_state = state
        variant = _connection_state_variant(state)
        display_state = _format_status_caption(state)
        for label in (self.connection_state_label,):
            label.setText(display_state)
            _apply_variant(label, variant)
        _apply_variant(self._conn_dot, variant)

    def _set_button_variant(self, button: QPushButton, variant: str) -> None:
        if button.property("variant") == variant:
            return
        button.setProperty("variant", variant)
        button.style().unpolish(button)
        button.style().polish(button)

    def _sync_dashboard_action_buttons(self) -> None:
        if self.bot_state in {"starting", "running"}:
            self._set_button_variant(self.start_button, "primary")
            self._set_button_variant(self.stop_button, "secondary")
            return
        self._set_button_variant(self.start_button, "secondary")
        self._set_button_variant(self.stop_button, "danger")

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
        self.last_successful_label.setText(
            self._format_last_successful_raid(state.last_successful_raid_open_at)
        )
        self.last_error_label.setText(state.last_error or "")
        self._refresh_dashboard_metrics()
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
        if self.isVisible():
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
        return self._show_centered_close_confirmation()

    def _show_centered_close_confirmation(self) -> bool:
        message_box = QMessageBox(None)
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

    def _refresh_available_profiles_for_settings(self) -> None:
        self.settings_page.set_available_profiles(self.available_profiles_loader())

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
            globally_enabled = bool(slot.enabled) if slot is not None else False
            checkbox.setChecked(
                bool(getattr(profile, field_name, True)) if globally_enabled else False
            )
            checkbox.setEnabled(globally_enabled)
            if not globally_enabled:
                checkbox.setToolTip("Enable this action globally in Bot Actions first.")
            layout.addWidget(checkbox)
            checkbox_map[field_name] = (checkbox, globally_enabled)
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
        }

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
            refreshed_slots = list(self.controller.config.bot_action_slots)
            refreshed_slots[0] = replace(
                refreshed_slots[0],
                presets=updated_slot.presets,
                finish_template_path=updated_slot.finish_template_path,
            )
            self.bot_actions_page.set_slots(tuple(refreshed_slots))
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
        chat_source_signature = self._chat_source_signature(config)
        if chat_source_signature != self._available_chats_signature:
            self._available_chats_cache = list(self.available_chats_loader())
            self._available_chats_signature = chat_source_signature
        self.settings_page.set_available_chats(self._available_chats_cache)
        self.bot_actions_page.set_page_ready_template_path(config.page_ready_template_path)
        self.bot_actions_page.set_slots(config.bot_action_slots)
        self.bot_actions_page.set_slot_1_finish_delay_seconds(
            config.slot_1_finish_delay_seconds
        )
        self._sync_raid_profile_cards(config, self._latest_state)

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
            card.restartRequested.connect(self.controller.restart_raid_profile)
            card.raidOnRestartChanged.connect(
                self.controller.set_raid_profile_raid_on_restart
            )
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
            self.raid_profile_cards[profile.profile_directory] = card
            self._raid_profile_card_widgets.append(card)
        self._reflow_raid_profile_cards()

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
