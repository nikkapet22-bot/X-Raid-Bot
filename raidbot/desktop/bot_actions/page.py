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
        self._set_preview(slot.template_path)
        if slot.template_path is not None:
            self.template_status_label.setText(str(slot.template_path))
        else:
            self.template_status_label.setText("No template captured.")

    def label_text(self) -> str:
        return self.slot_label.text()

    def _set_preview(self, template_path: Path | None) -> None:
        if template_path is None:
            self.template_preview_label.clear()
            self.template_preview_label.setText("No image")
            return

        pixmap = QPixmap(str(template_path))
        if pixmap.isNull():
            self.template_preview_label.clear()
            self.template_preview_label.setText("Preview unavailable")
            return

        self.template_preview_label.setText("")
        self.template_preview_label.setPixmap(
            pixmap.scaled(
                self.template_preview_label.minimumSize(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )


class BotActionsPage(QWidget):
    slotCaptureRequested = Signal(int)
    slotTestRequested = Signal(int)
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

        self.status_label = QLabel("Configure fixed bot action slots.")
        self.status_label.setWordWrap(True)
        self.status_label.setProperty("muted", "true")

        self._build_layout()
        self.set_slots(config.bot_action_slots)
        self.set_settle_delay(config.auto_run_settle_ms)

    def set_slots(self, slots: Sequence[BotActionSlotConfig]) -> None:
        for box, slot in zip(self.slot_boxes, slots):
            box.set_slot(slot)

    def set_settle_delay(self, settle_delay_ms: int) -> None:
        with QSignalBlocker(self.settle_delay_input):
            self.settle_delay_input.setValue(int(settle_delay_ms))

    def show_error(self, message: str) -> None:
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
                lambda _checked=False, slot_index=index: self.slotCaptureRequested.emit(
                    slot_index
                )
            )
            box.test_button.clicked.connect(
                lambda _checked=False, slot_index=index: self.slotTestRequested.emit(
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
