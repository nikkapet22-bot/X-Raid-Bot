from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Callable
from uuid import uuid4

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from raidbot.desktop.models import BotActionPreset, BotActionSlotConfig


class Slot1PresetsDialog(QDialog):
    def __init__(
        self,
        *,
        slot: BotActionSlotConfig,
        choose_image_file: Callable[[], Path | None] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Slot 1 Presets")
        self._slot = slot
        self._choose_image_file = choose_image_file or self._default_choose_image_file
        self._presets: list[BotActionPreset] = [
            BotActionPreset(
                id=str(preset.id),
                text=str(preset.text),
                image_path=(
                    Path(preset.image_path)
                    if preset.image_path is not None
                    else None
                ),
            )
            for preset in slot.presets
        ]
        self.finish_template_path = (
            Path(slot.finish_template_path)
            if slot.finish_template_path is not None
            else None
        )
        self.finish_template_path_2 = (
            Path(slot.finish_template_path_2)
            if slot.finish_template_path_2 is not None
            else None
        )
        self._current_row = -1

        self.preset_list = QListWidget()
        self.preset_list.currentRowChanged.connect(self._handle_current_row_changed)

        self.add_preset_button = QPushButton("Add preset")
        self.add_preset_button.clicked.connect(self.add_preset)
        self.remove_preset_button = QPushButton("Remove preset")
        self.remove_preset_button.clicked.connect(self.remove_selected_preset)

        self.preset_text_input = QPlainTextEdit()
        self.preset_text_input.setPlaceholderText("Preset text")

        self.preset_image_status_label = QLabel("No preset image")
        self.preset_image_status_label.setWordWrap(True)
        self.preset_image_status_label.setProperty("muted", "true")
        self.upload_image_button = QPushButton("Upload image")
        self.upload_image_button.clicked.connect(self.upload_image_for_selected_preset)
        self.clear_image_button = QPushButton("Clear image")
        self.clear_image_button.clicked.connect(self.clear_image_for_selected_preset)

        self.finish_image_status_label = QLabel(
            str(self.finish_template_path) if self.finish_template_path is not None else "No finish image"
        )
        self.finish_image_status_label.setWordWrap(True)
        self.finish_image_status_label.setProperty("muted", "true")
        self.capture_finish_button = QPushButton("Capture finish image")
        self.finish_image_2_status_label = QLabel(
            str(self.finish_template_path_2)
            if self.finish_template_path_2 is not None
            else "No finish image 2"
        )
        self.finish_image_2_status_label.setWordWrap(True)
        self.finish_image_2_status_label.setProperty("muted", "true")
        self.capture_finish_button_2 = QPushButton("Capture finish image 2")

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

        self._build_layout()
        self._refresh_preset_list(select_row=0 if self._presets else None)

    def add_preset(self) -> None:
        self._store_current_preset()
        self._presets.append(BotActionPreset(id=uuid4().hex, text="", image_path=None))
        self._refresh_preset_list(select_row=len(self._presets) - 1)

    def remove_selected_preset(self) -> None:
        row = self.preset_list.currentRow()
        if row < 0 or row >= len(self._presets):
            return
        del self._presets[row]
        next_row = min(row, len(self._presets) - 1)
        self._refresh_preset_list(select_row=next_row if next_row >= 0 else None)

    def build_updated_slot(self) -> BotActionSlotConfig:
        self._store_current_preset()
        return replace(
            self._slot,
            presets=tuple(self._presets),
            finish_template_path=self.finish_template_path,
            finish_template_path_2=self.finish_template_path_2,
        )

    def _build_layout(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setSpacing(12)

        top_row = QHBoxLayout()
        top_row.setSpacing(12)

        list_column = QVBoxLayout()
        list_column.addWidget(self.preset_list)
        list_buttons = QHBoxLayout()
        list_buttons.addWidget(self.add_preset_button)
        list_buttons.addWidget(self.remove_preset_button)
        list_column.addLayout(list_buttons)

        editor_widget = QWidget()
        editor_form = QFormLayout(editor_widget)
        editor_form.addRow("Text", self.preset_text_input)
        image_buttons = QHBoxLayout()
        image_buttons.addWidget(self.upload_image_button)
        image_buttons.addWidget(self.clear_image_button)
        editor_form.addRow("Preset image", self.preset_image_status_label)
        editor_form.addRow("", image_buttons)
        editor_form.addRow("Finish image", self.finish_image_status_label)
        editor_form.addRow("", self.capture_finish_button)
        editor_form.addRow("Finish image 2", self.finish_image_2_status_label)
        editor_form.addRow("", self.capture_finish_button_2)

        top_row.addLayout(list_column, 1)
        top_row.addWidget(editor_widget, 2)
        root_layout.addLayout(top_row)
        root_layout.addWidget(self.button_box)

    def _refresh_preset_list(self, *, select_row: int | None) -> None:
        self.preset_list.clear()
        for index, preset in enumerate(self._presets):
            label = preset.text.strip().splitlines()[0] if preset.text.strip() else f"Preset {index + 1}"
            self.preset_list.addItem(QListWidgetItem(label))
        if not self._presets:
            self._current_row = -1
            self.preset_text_input.clear()
            self.preset_image_status_label.setText("No preset image")
            return
        row = 0 if select_row is None or select_row < 0 else min(select_row, len(self._presets) - 1)
        self.preset_list.setCurrentRow(row)

    def _handle_current_row_changed(self, row: int) -> None:
        self._store_current_preset()
        self._current_row = row
        if row < 0 or row >= len(self._presets):
            self.preset_text_input.clear()
            self.preset_image_status_label.setText("No preset image")
            return
        preset = self._presets[row]
        self.preset_text_input.setPlainText(preset.text)
        self.preset_image_status_label.setText(
            str(preset.image_path) if preset.image_path is not None else "No preset image"
        )

    def _store_current_preset(self) -> None:
        row = self._current_row
        if row < 0 or row >= len(self._presets):
            return
        current = self._presets[row]
        updated = replace(
            current,
            text=self.preset_text_input.toPlainText(),
        )
        self._presets[row] = updated
        item = self.preset_list.item(row)
        if item is not None:
            label = updated.text.strip().splitlines()[0] if updated.text.strip() else f"Preset {row + 1}"
            item.setText(label)

    def upload_image_for_selected_preset(self) -> None:
        row = self._current_row
        if row < 0 or row >= len(self._presets):
            return
        image_path = self._choose_image_file()
        if image_path is None:
            return
        current = self._presets[row]
        updated = replace(current, image_path=Path(image_path))
        self._presets[row] = updated
        self.preset_image_status_label.setText(str(updated.image_path))

    def clear_image_for_selected_preset(self) -> None:
        row = self._current_row
        if row < 0 or row >= len(self._presets):
            return
        current = self._presets[row]
        self._presets[row] = replace(current, image_path=None)
        self.preset_image_status_label.setText("No preset image")

    def _default_choose_image_file(self) -> Path | None:
        selected_path, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "Choose preset image",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp);;All files (*)",
        )
        if not selected_path:
            return None
        return Path(selected_path)
