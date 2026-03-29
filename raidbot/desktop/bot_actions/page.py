from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
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


def _set_preview_label(preview_label: QLabel, template_path: Path | None) -> None:
    if template_path is None:
        preview_label.clear()
        preview_label.setText("No image")
        return

    pixmap = QPixmap(str(template_path))
    if pixmap.isNull():
        preview_label.clear()
        preview_label.setText("Preview unavailable")
        return

    preview_label.setText("")
    preview_label.setPixmap(
        pixmap.scaled(
            preview_label.minimumSize(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    )


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

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        self.slot_label = QLabel(slot.label)
        layout.addWidget(self.slot_label)

        self.enabled_checkbox = QCheckBox("Enabled")
        layout.addWidget(self.enabled_checkbox)

        self.template_preview_label = QLabel("No image")
        self.template_preview_label.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )
        self.template_preview_label.setMinimumSize(120, 72)
        self.template_preview_label.setProperty("muted", "true")
        layout.addWidget(self.template_preview_label)

        self.button_row_widget = QWidget()
        self.button_row_layout = QHBoxLayout(self.button_row_widget)
        self.button_row_layout.setSpacing(8)
        self.button_row_layout.setContentsMargins(0, 0, 0, 0)

        self.capture_button = QPushButton("Capture")
        self.capture_button.setProperty("variant", "secondary")
        self.button_row_layout.addWidget(self.capture_button)

        self.test_button = QPushButton("Test")
        self.test_button.setProperty("variant", "secondary")
        self.button_row_layout.addWidget(self.test_button)

        self.presets_button: QPushButton | None = None
        if self._index == 0:
            self.presets_button = QPushButton("Presets")
            self.presets_button.setProperty("variant", "secondary")
            self.button_row_layout.addWidget(self.presets_button)

        layout.addWidget(self.button_row_widget)

        self.template_status_label = QLabel("")
        self.template_status_label.setWordWrap(True)
        self.template_status_label.setProperty("muted", "true")
        layout.addWidget(self.template_status_label)

        layout.addStretch()
        self.set_slot(slot)

    def set_slot(self, slot: BotActionSlotConfig) -> None:
        self.slot_label.setText(slot.label)
        with QSignalBlocker(self.enabled_checkbox):
            self.enabled_checkbox.setChecked(bool(slot.enabled))
        _set_preview_label(self.template_preview_label, slot.template_path)
        if slot.template_path is not None:
            self.template_status_label.setText(str(slot.template_path))
        else:
            self.template_status_label.setText("No template captured.")

    def label_text(self) -> str:
        return self.slot_label.text()

class BotActionsPage(QWidget):
    pageReadyCaptureRequested = Signal()
    slotCaptureRequested = Signal(int)
    slotTestRequested = Signal(int)
    slotPresetsRequested = Signal(int)
    slotEnabledChanged = Signal(int, bool)
    settleDelayChanged = Signal(int)

    def __init__(
        self,
        *,
        config: DesktopAppConfig,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.slot_boxes: list[SlotBox] = []

        self.settle_delay_input = QSpinBox()
        self.settle_delay_input.setRange(0, 10000)
        self.settle_delay_input.valueChanged.connect(self.settleDelayChanged.emit)

        self.page_ready_preview_label = QLabel("No image")
        self.page_ready_preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_ready_preview_label.setMinimumSize(120, 72)
        self.page_ready_preview_label.setProperty("muted", "true")

        self.page_ready_capture_button = QPushButton("Capture")
        self.page_ready_capture_button.setProperty("variant", "secondary")
        self.page_ready_capture_button.clicked.connect(
            self._emit_page_ready_capture_request
        )

        self.page_ready_status_label = QLabel("No template captured.")
        self.page_ready_status_label.setWordWrap(True)
        self.page_ready_status_label.setProperty("muted", "true")

        self.status_label = QLabel("Configure fixed bot action slots.")
        self.status_label.setWordWrap(True)
        self.status_label.setProperty("muted", "true")

        self._build_layout()
        self.set_page_ready_template_path(config.page_ready_template_path)
        self.set_slots(config.bot_action_slots)
        self.set_settle_delay(config.auto_run_settle_ms)

    def set_slots(self, slots: Sequence[BotActionSlotConfig]) -> None:
        for box, slot in zip(self.slot_boxes, slots):
            box.set_slot(slot)

    def set_settle_delay(self, settle_delay_ms: int) -> None:
        with QSignalBlocker(self.settle_delay_input):
            self.settle_delay_input.setValue(int(settle_delay_ms))

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

    def show_status(self, message: str) -> None:
        self.status_label.setText(message)

    def _build_layout(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        title_label = QLabel("Bot Actions")
        layout.addWidget(title_label)

        helper_label = QLabel(
            "Configure the four fixed bot action slots used by the desktop bot."
        )
        helper_label.setWordWrap(True)
        helper_label.setProperty("muted", "true")
        layout.addWidget(helper_label)

        page_ready_group = QGroupBox("Page Ready")
        page_ready_layout = QVBoxLayout(page_ready_group)
        page_ready_layout.addWidget(self.page_ready_preview_label)
        page_ready_layout.addWidget(self.page_ready_capture_button)
        page_ready_layout.addWidget(self.page_ready_status_label)
        layout.addWidget(page_ready_group)

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
            self.slot_boxes.append(box)
            slots_layout.addWidget(box, index // 2, index % 2)
        layout.addWidget(slots_group)

        timing_group = QGroupBox("Timing")
        timing_layout = QFormLayout(timing_group)
        timing_layout.addRow("Settle delay ms", self.settle_delay_input)
        layout.addWidget(timing_group)

        status_group = QGroupBox("Status")
        status_layout = QVBoxLayout(status_group)
        status_layout.addWidget(self.status_label)
        layout.addWidget(status_group)
        layout.addStretch()

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
