from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from PySide6.QtCore import QSignalBlocker, QSize, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from raidbot.desktop.models import BotActionSlotConfig, DesktopAppConfig

_SLOT_DISPLAY_LABELS = {
    "slot_1_r": "Reply",
    "slot_2_l": "Like",
    "slot_3_r": "Repost",
    "slot_4_b": "Bookmark",
}


def _set_preview_label(
    preview_label: QLabel,
    template_path: Path | None,
    *,
    empty_text: str = "No image",
) -> None:
    if template_path is None:
        preview_label.clear()
        preview_label.setText(empty_text)
        return

    try:
        image_bytes = Path(template_path).read_bytes()
    except OSError:
        preview_label.clear()
        preview_label.setText("Preview unavailable")
        return

    image = QImage()
    if not image.loadFromData(image_bytes):
        preview_label.clear()
        preview_label.setText("Preview unavailable")
        return

    pixmap = QPixmap.fromImage(image)
    preview_label.setText("")
    preview_label.setPixmap(
        pixmap.scaled(
            preview_label.minimumSize(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    )


class ToggleSwitch(QCheckBox):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setText("")
        self.setAccessibleName("Enabled")
        self.setFixedSize(34, 18)

    def sizeHint(self) -> QSize:
        return QSize(34, 18)

    def hitButton(self, pos) -> bool:
        return self.rect().contains(pos)

    def paintEvent(self, _event) -> None:
        track_margin = 1
        knob_margin = 2
        knob_size = self.height() - (knob_margin * 2)
        track_rect = self.rect().adjusted(0, track_margin, 0, -track_margin)
        checked = self.isChecked()
        enabled = self.isEnabled()

        track_color = QColor("#2dd4bf" if checked else "#142035")
        border_color = QColor("#2dd4bf" if checked else "#1e3252")
        knob_color = QColor("#ffffff" if checked else "#4e6a94")
        if not enabled:
            track_color = QColor("#0a1628")
            border_color = QColor("#142035")
            knob_color = QColor("#253550")

        knob_x = self.width() - knob_size - knob_margin if checked else knob_margin

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(border_color, 1.0))
        painter.setBrush(track_color)
        painter.drawRoundedRect(track_rect, track_rect.height() / 2, track_rect.height() / 2)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(knob_color)
        painter.drawEllipse(knob_x, knob_margin, knob_size, knob_size)
        painter.end()


class SlotBox(QFrame):
    def __init__(
        self,
        *,
        index: int,
        slot: BotActionSlotConfig,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._index = index
        self.setObjectName("card")
        self.setMinimumWidth(180)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(14, 14, 14, 14)

        # Header: dot + slot label
        self.header_layout = QHBoxLayout()
        self.header_layout.setSpacing(8)
        self._dot = QLabel()
        self._dot.setObjectName("statusDot")
        self._dot.setFixedSize(9, 9)
        self._dot.setProperty("stateVariant", "neutral")
        self.slot_label = QLabel(_SLOT_DISPLAY_LABELS.get(slot.key, slot.label))
        self.slot_label.setObjectName("botActionGlyph")
        self.enabled_checkbox = ToggleSwitch()
        self.finish_delay_widget: QWidget | None = None
        self.finish_delay_label: QLabel | None = None
        self.finish_delay_input: QSpinBox | None = None
        self.finish_preview_label: QLabel | None = None
        self.header_layout.addWidget(self._dot, 0, Qt.AlignmentFlag.AlignVCenter)
        self.header_layout.addWidget(self.slot_label, 0, Qt.AlignmentFlag.AlignVCenter)
        self.header_layout.addWidget(self.enabled_checkbox, 0, Qt.AlignmentFlag.AlignVCenter)
        self.header_layout.addStretch()
        if self._index == 0:
            self.finish_delay_widget = QWidget()
            self.finish_delay_widget.setObjectName("finishDelayInline")
            finish_delay_layout = QHBoxLayout(self.finish_delay_widget)
            finish_delay_layout.setContentsMargins(0, 0, 0, 0)
            finish_delay_layout.setSpacing(6)
            self.finish_delay_label = QLabel("Finish Delay")
            self.finish_delay_label.setObjectName("botActionSlotMeta")
            self.finish_delay_label.setProperty("muted", "true")
            self.finish_delay_input = QSpinBox()
            self.finish_delay_input.setObjectName("finishDelayInput")
            self.finish_delay_input.setRange(0, 10)
            self.finish_delay_input.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
            self.finish_delay_input.setMinimumWidth(48)
            self.finish_delay_input.setMaximumWidth(48)
            self.finish_delay_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
            finish_delay_layout.addWidget(
                self.finish_delay_label,
                0,
                Qt.AlignmentFlag.AlignVCenter,
            )
            finish_delay_layout.addWidget(
                self.finish_delay_input,
                0,
                Qt.AlignmentFlag.AlignVCenter,
            )
            self.header_layout.addWidget(
                self.finish_delay_widget,
                0,
                Qt.AlignmentFlag.AlignVCenter,
            )
        layout.addLayout(self.header_layout)

        # Divider
        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setStyleSheet("background: #1e3252; max-height: 1px; border: none;")
        layout.addWidget(div)

        self.preview_row_widget = QWidget()
        self.preview_row_layout = QHBoxLayout(self.preview_row_widget)
        self.preview_row_layout.setContentsMargins(0, 0, 0, 0)
        self.preview_row_layout.setSpacing(8)

        self.template_preview_label = QLabel("No image")
        self.template_preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.template_preview_label.setMinimumSize(120, 72)
        self.template_preview_label.setProperty("muted", "true")
        self.template_preview_label.setStyleSheet(
            "border: 1px dashed #1e3252; border-radius: 6px;"
        )
        self.preview_row_layout.addWidget(self.template_preview_label)

        if self._index == 0:
            self.finish_preview_label = QLabel("No finish image")
            self.finish_preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.finish_preview_label.setMinimumSize(120, 72)
            self.finish_preview_label.setProperty("muted", "true")
            self.finish_preview_label.setStyleSheet(
                "border: 1px dashed #1e3252; border-radius: 6px;"
            )
            self.preview_row_layout.addWidget(self.finish_preview_label)

        layout.addWidget(self.preview_row_widget)

        self.button_row_widget = QWidget()
        self.button_row_widget.setObjectName("botActionButtonRow")
        self.button_row_layout = QHBoxLayout(self.button_row_widget)
        self.button_row_layout.setSpacing(8)
        self.button_row_layout.setContentsMargins(0, 0, 0, 0)

        self.capture_button = QPushButton("Capture")
        self.capture_button.setProperty("variant", "secondary")
        self.capture_button.setProperty("botActionButton", "true")
        self.button_row_layout.addWidget(self.capture_button)

        self.test_button = QPushButton("Test")
        self.test_button.setProperty("variant", "secondary")
        self.test_button.setProperty("botActionButton", "true")
        self.button_row_layout.addWidget(self.test_button)

        self.presets_button: QPushButton | None = None
        if self._index == 0:
            self.presets_button = QPushButton("Presets")
            self.presets_button.setProperty("variant", "secondary")
            self.presets_button.setProperty("botActionButton", "true")
            self.button_row_layout.addWidget(self.presets_button)

        layout.addWidget(self.button_row_widget)

        self.template_status_label = QLabel("")
        self.template_status_label.setWordWrap(True)
        self.template_status_label.setProperty("muted", "true")
        layout.addWidget(self.template_status_label)

        layout.addStretch()
        self.set_slot(slot)

    def set_slot(self, slot: BotActionSlotConfig) -> None:
        self.slot_label.setText(_SLOT_DISPLAY_LABELS.get(slot.key, slot.label))
        with QSignalBlocker(self.enabled_checkbox):
            self.enabled_checkbox.setChecked(bool(slot.enabled))
        _set_preview_label(self.template_preview_label, slot.template_path)
        if self.finish_preview_label is not None:
            _set_preview_label(
                self.finish_preview_label,
                slot.finish_template_path,
                empty_text="No finish image",
            )

        has_template = slot.template_path is not None
        variant = "running" if has_template and slot.enabled else (
            "active" if has_template else "neutral"
        )
        self._dot.setProperty("stateVariant", variant)
        self._dot.style().unpolish(self._dot)
        self._dot.style().polish(self._dot)

        self.template_status_label.setText(
            str(slot.template_path) if has_template else "No template captured."
        )

    def label_text(self) -> str:
        return self.slot_label.text()

class BotActionsPage(QWidget):
    pageReadyCaptureRequested = Signal()
    slotCaptureRequested = Signal(int)
    slotTestRequested = Signal(int)
    slotPresetsRequested = Signal(int)
    slotEnabledChanged = Signal(int, bool)
    slot1FinishDelayChanged = Signal(int)

    def __init__(
        self,
        *,
        config: DesktopAppConfig,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.slot_boxes: list[SlotBox] = []
        self.slot_1_finish_delay_input: QSpinBox | None = None

        self.page_ready_preview_label = QLabel("No image")
        self.page_ready_preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_ready_preview_label.setMinimumSize(120, 72)
        self.page_ready_preview_label.setProperty("muted", "true")

        self.page_ready_capture_button = QPushButton("Capture")
        self.page_ready_capture_button.setProperty("variant", "secondary")
        self.page_ready_capture_button.setProperty("botActionButton", "true")
        self.page_ready_capture_button.clicked.connect(
            self._emit_page_ready_capture_request
        )

        self.page_ready_status_label = QLabel("No template captured.")
        self.page_ready_status_label.setWordWrap(True)
        self.page_ready_status_label.setProperty("muted", "true")

        self.status_label = QLabel("Configure fixed bot action slots.")
        self.status_label.setWordWrap(True)
        self.status_label.setProperty("muted", "true")
        self.status_label.hide()

        self.status_latest_value_label = QLabel("Idle")
        self.status_latest_value_label.setObjectName("botActionsStatusValue")
        self.status_current_slot_value_label = QLabel("Waiting")
        self.status_current_slot_value_label.setObjectName("botActionsStatusMetaValue")
        self.status_current_slot_value_label.setWordWrap(True)
        self.status_last_error_value_label = QLabel("No errors")
        self.status_last_error_value_label.setObjectName("botActionsStatusErrorValue")
        self.status_last_error_value_label.setWordWrap(True)

        self._build_layout()
        self.set_page_ready_template_path(config.page_ready_template_path)
        self.set_slots(config.bot_action_slots)
        self.set_slot_1_finish_delay_seconds(config.slot_1_finish_delay_seconds)
        self.set_status_fields(latest_status="Configure fixed bot action slots.")

    def set_slots(self, slots: Sequence[BotActionSlotConfig]) -> None:
        for box, slot in zip(self.slot_boxes, slots):
            box.set_slot(slot)

    def set_slot_1_finish_delay_seconds(self, finish_delay_seconds: int) -> None:
        if self.slot_1_finish_delay_input is None:
            return
        with QSignalBlocker(self.slot_1_finish_delay_input):
            self.slot_1_finish_delay_input.setValue(int(finish_delay_seconds))

    def set_page_ready_template_path(self, template_path: Path | None) -> None:
        normalized_template_path = (
            Path(template_path) if template_path is not None else None
        )
        _set_preview_label(self.page_ready_preview_label, normalized_template_path)
        if normalized_template_path is not None:
            self.page_ready_status_label.setText(str(normalized_template_path))
        else:
            self.page_ready_status_label.setText("No template captured.")

    def show_error(self, message: str) -> None:
        self.status_label.setText(message)
        self.set_status_fields(latest_status="Error", current_slot=None, last_error=message)

    def show_status(self, message: str) -> None:
        self.status_label.setText(message)
        self.set_status_fields(latest_status=message)

    def set_status_fields(
        self,
        *,
        latest_status: str,
        current_slot: str | None = None,
        last_error: str | None = None,
    ) -> None:
        self.status_latest_value_label.setText(latest_status)
        self.status_current_slot_value_label.setText(current_slot or "Waiting")
        self.status_last_error_value_label.setText(last_error or "No errors")

    def _build_layout(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(12, 24, 12, 24)

        page_title = QLabel("Bot Actions")
        page_title.setObjectName("pageTitle")
        layout.addWidget(page_title)

        helper_label = QLabel(
            "Configure the four fixed bot action slots used by the desktop bot."
        )
        helper_label.setWordWrap(True)
        helper_label.setProperty("muted", "true")
        layout.addWidget(helper_label)

        # Page ready section
        page_ready_group = QGroupBox("Page Ready")
        page_ready_layout = QVBoxLayout(page_ready_group)
        page_ready_layout.setSpacing(0)
        page_ready_layout.setContentsMargins(0, 8, 0, 0)
        self.page_ready_card = QFrame()
        self.page_ready_card.setObjectName("card")
        page_ready_card_layout = QHBoxLayout(self.page_ready_card)
        page_ready_card_layout.setSpacing(12)
        page_ready_card_layout.setContentsMargins(14, 14, 14, 14)
        self.page_ready_preview_label.setStyleSheet(
            "border: 1px dashed #1e3252; border-radius: 6px;"
        )
        page_ready_card_layout.addWidget(self.page_ready_preview_label)
        pr_info = QVBoxLayout()
        pr_info.addWidget(self.page_ready_capture_button)
        pr_info.addWidget(self.page_ready_status_label)
        pr_info.addStretch()
        page_ready_card_layout.addLayout(pr_info)
        page_ready_layout.addWidget(self.page_ready_card)
        layout.addWidget(page_ready_group)

        # Slot cards in a 2×2 grid
        slots_group = QGroupBox("Action Slots")
        slots_layout = QGridLayout(slots_group)
        slots_layout.setSpacing(12)
        for index in range(4):
            box = SlotBox(
                index=index,
                slot=BotActionSlotConfig(key=f"slot_{index}", label="?"),
            )
            box.enabled_checkbox.toggled.connect(
                lambda checked, slot_index=index: self.slotEnabledChanged.emit(
                    slot_index, checked
                )
            )
            box.capture_button.clicked.connect(
                lambda _checked=False, slot_index=index: self._emit_slot_capture_request(
                    slot_index
                )
            )
            box.test_button.clicked.connect(
                lambda _checked=False, slot_index=index: self._emit_slot_test_request(
                    slot_index
                )
            )
            if box.presets_button is not None:
                box.presets_button.clicked.connect(
                    lambda _checked=False, slot_index=index: self._emit_slot_presets_request(
                        slot_index
                    )
                )
            if index == 0 and box.finish_delay_input is not None:
                self.slot_1_finish_delay_input = box.finish_delay_input
                box.finish_delay_input.valueChanged.connect(
                    self.slot1FinishDelayChanged.emit
                )
            self.slot_boxes.append(box)
            slots_layout.addWidget(box, index // 2, index % 2)
        layout.addWidget(slots_group)

        # Status
        status_group = QGroupBox("Status")
        status_layout = QVBoxLayout(status_group)
        status_layout.setSpacing(10)
        status_layout.addWidget(self._build_status_row("Latest status", self.status_latest_value_label))
        status_layout.addWidget(
            self._build_status_row("Current slot", self.status_current_slot_value_label)
        )
        status_layout.addWidget(
            self._build_status_row("Last error", self.status_last_error_value_label)
        )
        status_layout.addWidget(self.status_label)
        layout.addWidget(status_group)
        layout.addStretch()

    def _build_status_row(self, title: str, value_label: QLabel) -> QWidget:
        row = QWidget()
        row_layout = QVBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(2)
        title_label = QLabel(title)
        title_label.setProperty("muted", "true")
        row_layout.addWidget(title_label)
        row_layout.addWidget(value_label)
        return row

    def _emit_slot_capture_request(self, slot_index: int) -> None:
        self.show_status(f"{self._format_slot_name(slot_index)}: capturing")
        self.slotCaptureRequested.emit(slot_index)

    def _emit_page_ready_capture_request(self) -> None:
        self.show_status("Page Ready: capturing")
        self.pageReadyCaptureRequested.emit()

    def _emit_slot_test_request(self, slot_index: int) -> None:
        self.show_status(f"{self._format_slot_name(slot_index)}: testing")
        self.slotTestRequested.emit(slot_index)

    def _emit_slot_presets_request(self, slot_index: int) -> None:
        self.show_status(f"{self._format_slot_name(slot_index)}: presets")
        self.slotPresetsRequested.emit(slot_index)

    def _format_slot_name(self, slot_index: int) -> str:
        if 0 <= slot_index < len(self.slot_boxes):
            return f"Slot {slot_index + 1} ({self.slot_boxes[slot_index].label_text()})"
        return f"Slot {slot_index + 1}"
