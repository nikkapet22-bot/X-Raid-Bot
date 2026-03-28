from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .models import AutomationSequence, AutomationStep


def _default_step() -> AutomationStep:
    return AutomationStep(
        name="New step",
        template_path=Path("templates/step.png"),
        match_threshold=0.9,
        max_search_seconds=1.0,
        max_scroll_attempts=0,
        scroll_amount=-120,
        max_click_attempts=1,
        post_click_settle_ms=250,
    )


class AutomationPage(QWidget):
    sequenceSaveRequested = Signal(object)
    sequenceDeleteRequested = Signal(str)
    runRequested = Signal(str, object)
    dryRunRequested = Signal(str, int, object)
    stopRequested = Signal()
    windowsRefreshRequested = Signal()

    def __init__(
        self,
        *,
        sequences: list[AutomationSequence] | None = None,
        windows: list[object] | None = None,
        run_state: str = "idle",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._sequences: list[AutomationSequence] = []
        self._steps: list[AutomationStep] = []

        self.sequence_list = QListWidget()
        self.sequence_list.currentRowChanged.connect(self._load_selected_sequence)

        self.sequence_name_input = QLineEdit()
        self.window_rule_input = QLineEdit()

        self.step_list = QListWidget()
        self.step_list.currentRowChanged.connect(self._load_selected_step)

        self.step_name_input = QLineEdit()
        self.template_path_input = QLineEdit()

        self.threshold_input = QDoubleSpinBox()
        self.threshold_input.setRange(-1.0, 1.0)
        self.threshold_input.setSingleStep(0.01)
        self.threshold_input.setDecimals(2)

        self.search_seconds_input = QDoubleSpinBox()
        self.search_seconds_input.setRange(0.05, 120.0)
        self.search_seconds_input.setSingleStep(0.5)
        self.search_seconds_input.setDecimals(2)

        self.scroll_attempts_input = QSpinBox()
        self.scroll_attempts_input.setRange(0, 100)

        self.scroll_amount_input = QSpinBox()
        self.scroll_amount_input.setRange(-5000, 5000)

        self.click_attempts_input = QSpinBox()
        self.click_attempts_input.setRange(1, 25)

        self.settle_ms_input = QSpinBox()
        self.settle_ms_input.setRange(0, 10000)

        self.click_offset_x_input = QSpinBox()
        self.click_offset_x_input.setRange(-5000, 5000)

        self.click_offset_y_input = QSpinBox()
        self.click_offset_y_input.setRange(-5000, 5000)

        self.window_combo = QComboBox()
        self.status_label = QLabel("Automation idle")
        self.status_label.setWordWrap(True)
        self.status_label.setProperty("muted", "true")
        self.activity_log = QListWidget()

        self.save_button = QPushButton("Save sequence")
        self.save_button.setProperty("variant", "primary")
        self.save_button.clicked.connect(self._emit_save_request)

        self.delete_button = QPushButton("Delete sequence")
        self.delete_button.setProperty("variant", "danger")
        self.delete_button.clicked.connect(self._emit_delete_request)

        self.add_step_button = QPushButton("Add step")
        self.add_step_button.setProperty("variant", "secondary")
        self.add_step_button.clicked.connect(self._add_step)

        self.remove_step_button = QPushButton("Remove step")
        self.remove_step_button.setProperty("variant", "secondary")
        self.remove_step_button.clicked.connect(self._remove_step)

        self.refresh_windows_button = QPushButton("Refresh windows")
        self.refresh_windows_button.setProperty("variant", "secondary")
        self.refresh_windows_button.clicked.connect(self.windowsRefreshRequested.emit)

        self.start_button = QPushButton("Start run")
        self.start_button.setProperty("variant", "primary")
        self.start_button.clicked.connect(self._emit_run_request)

        self.dry_run_button = QPushButton("Dry run step")
        self.dry_run_button.setProperty("variant", "secondary")
        self.dry_run_button.clicked.connect(self._emit_dry_run_request)

        self.stop_button = QPushButton("Stop")
        self.stop_button.setProperty("variant", "danger")
        self.stop_button.clicked.connect(self.stopRequested.emit)

        self._build_layout()
        self.set_sequences(sequences or [])
        self.refresh_windows(windows or [])
        self.set_run_state(run_state)

    def set_sequences(self, sequences: list[AutomationSequence]) -> None:
        selected_id = self._selected_sequence_id()
        self._sequences = [self._clone_sequence(sequence) for sequence in sequences]
        self.sequence_list.clear()
        selected_row = -1
        for index, sequence in enumerate(self._sequences):
            item = QListWidgetItem(sequence.name)
            item.setData(1, sequence.id)
            self.sequence_list.addItem(item)
            if sequence.id == selected_id:
                selected_row = index
        if self._sequences:
            self.sequence_list.setCurrentRow(selected_row if selected_row >= 0 else 0)
        else:
            self._load_blank_sequence()

    def refresh_windows(self, windows: list[object]) -> None:
        previous_handle = self.window_combo.currentData()
        self.window_combo.clear()
        self.window_combo.addItem("Auto select from rule", None)
        for window in windows:
            handle = getattr(window, "handle", None)
            title = getattr(window, "title", str(window))
            self.window_combo.addItem(f"{title} [{handle}]", handle)
        index = self.window_combo.findData(previous_handle)
        self.window_combo.setCurrentIndex(index if index >= 0 else 0)

    def set_run_state(self, state: str) -> None:
        is_running = state == "running"
        self.start_button.setEnabled(not is_running)
        self.dry_run_button.setEnabled(not is_running)
        self.stop_button.setEnabled(is_running)
        if not is_running and self.status_label.text().strip() in {"Running sequence", "Automation idle"}:
            self.status_label.setText("Automation idle")

    def handle_run_event(self, event: dict[str, object]) -> None:
        event_type = str(event.get("type", "event"))
        if event_type == "dry_run_match_found":
            step_index = event.get("step_index")
            score = event.get("score")
            self.status_label.setText(
                f"Dry run matched step {step_index} with score {score:.2f}"
                if isinstance(score, float)
                else f"Dry run matched step {step_index}"
            )
        elif event_type == "run_started":
            self.status_label.setText("Running sequence")
        elif event_type == "run_completed":
            self.status_label.setText("Run completed")
        elif event_type == "step_failed":
            self.status_label.setText(f"Step failed: {event.get('reason')}")
        elif event_type == "target_window_lost":
            self.status_label.setText(f"Window lost: {event.get('reason')}")
        elif event_type == "run_stopped":
            self.status_label.setText("Run stopped")
        self.activity_log.addItem(self._format_event(event))

    def show_error(self, message: str) -> None:
        self.status_label.setText(message)

    def _build_layout(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setSpacing(16)

        top_layout = QHBoxLayout()
        top_layout.setSpacing(16)

        sequence_group = QGroupBox("Sequences")
        sequence_layout = QVBoxLayout(sequence_group)
        sequence_layout.addWidget(self.sequence_list)

        sequence_form = QFormLayout()
        sequence_form.addRow("Name", self.sequence_name_input)
        sequence_form.addRow("Window rule", self.window_rule_input)
        sequence_layout.addLayout(sequence_form)

        sequence_button_row = QHBoxLayout()
        sequence_button_row.addWidget(self.save_button)
        sequence_button_row.addWidget(self.delete_button)
        sequence_layout.addLayout(sequence_button_row)

        editor_group = QGroupBox("Step Editor")
        editor_layout = QVBoxLayout(editor_group)
        editor_layout.addWidget(self.step_list)

        step_button_row = QHBoxLayout()
        step_button_row.addWidget(self.add_step_button)
        step_button_row.addWidget(self.remove_step_button)
        editor_layout.addLayout(step_button_row)

        step_form = QGridLayout()
        step_form.addWidget(QLabel("Step name"), 0, 0)
        step_form.addWidget(self.step_name_input, 0, 1)
        step_form.addWidget(QLabel("Template path"), 1, 0)
        step_form.addWidget(self.template_path_input, 1, 1)
        step_form.addWidget(QLabel("Threshold"), 2, 0)
        step_form.addWidget(self.threshold_input, 2, 1)
        step_form.addWidget(QLabel("Search seconds"), 3, 0)
        step_form.addWidget(self.search_seconds_input, 3, 1)
        step_form.addWidget(QLabel("Scroll attempts"), 4, 0)
        step_form.addWidget(self.scroll_attempts_input, 4, 1)
        step_form.addWidget(QLabel("Scroll amount"), 5, 0)
        step_form.addWidget(self.scroll_amount_input, 5, 1)
        step_form.addWidget(QLabel("Click attempts"), 6, 0)
        step_form.addWidget(self.click_attempts_input, 6, 1)
        step_form.addWidget(QLabel("Settle delay ms"), 7, 0)
        step_form.addWidget(self.settle_ms_input, 7, 1)
        step_form.addWidget(QLabel("Offset X"), 8, 0)
        step_form.addWidget(self.click_offset_x_input, 8, 1)
        step_form.addWidget(QLabel("Offset Y"), 9, 0)
        step_form.addWidget(self.click_offset_y_input, 9, 1)
        editor_layout.addLayout(step_form)

        top_layout.addWidget(sequence_group, 1)
        top_layout.addWidget(editor_group, 2)
        root_layout.addLayout(top_layout)

        runner_group = QGroupBox("Runner")
        runner_layout = QVBoxLayout(runner_group)
        runner_form = QFormLayout()
        runner_form.addRow("Target window", self.window_combo)
        runner_layout.addLayout(runner_form)
        runner_buttons = QHBoxLayout()
        runner_buttons.addWidget(self.refresh_windows_button)
        runner_buttons.addWidget(self.start_button)
        runner_buttons.addWidget(self.dry_run_button)
        runner_buttons.addWidget(self.stop_button)
        runner_layout.addLayout(runner_buttons)
        runner_layout.addWidget(self.status_label)
        root_layout.addWidget(runner_group)

        activity_group = QGroupBox("Activity")
        activity_layout = QVBoxLayout(activity_group)
        activity_layout.addWidget(self.activity_log)
        root_layout.addWidget(activity_group)

    def _load_selected_sequence(self, row: int) -> None:
        self._store_current_step()
        if row < 0 or row >= len(self._sequences):
            self._load_blank_sequence()
            return
        sequence = self._clone_sequence(self._sequences[row])
        self.sequence_name_input.setText(sequence.name)
        self.window_rule_input.setText(sequence.target_window_rule or "")
        self._steps = sequence.steps or [_default_step()]
        self._refresh_step_list(select_row=0)

    def _load_blank_sequence(self) -> None:
        self.sequence_name_input.clear()
        self.window_rule_input.clear()
        self._steps = [_default_step()]
        self._refresh_step_list(select_row=0)

    def _refresh_step_list(self, *, select_row: int | None = None) -> None:
        current_row = self.step_list.currentRow()
        self.step_list.clear()
        for step in self._steps:
            self.step_list.addItem(step.name)
        if not self._steps:
            self._load_blank_step()
            return
        row = select_row if select_row is not None else current_row
        if row is None or row < 0 or row >= len(self._steps):
            row = 0
        self.step_list.setCurrentRow(row)

    def _load_selected_step(self, row: int) -> None:
        if row < 0 or row >= len(self._steps):
            self._load_blank_step()
            return
        step = self._steps[row]
        self.step_name_input.setText(step.name)
        self.template_path_input.setText(str(step.template_path))
        self.threshold_input.setValue(step.match_threshold)
        self.search_seconds_input.setValue(step.max_search_seconds)
        self.scroll_attempts_input.setValue(step.max_scroll_attempts)
        self.scroll_amount_input.setValue(step.scroll_amount)
        self.click_attempts_input.setValue(step.max_click_attempts)
        self.settle_ms_input.setValue(step.post_click_settle_ms)
        self.click_offset_x_input.setValue(step.click_offset_x)
        self.click_offset_y_input.setValue(step.click_offset_y)

    def _load_blank_step(self) -> None:
        blank = _default_step()
        self.step_name_input.setText(blank.name)
        self.template_path_input.setText(str(blank.template_path))
        self.threshold_input.setValue(blank.match_threshold)
        self.search_seconds_input.setValue(blank.max_search_seconds)
        self.scroll_attempts_input.setValue(blank.max_scroll_attempts)
        self.scroll_amount_input.setValue(blank.scroll_amount)
        self.click_attempts_input.setValue(blank.max_click_attempts)
        self.settle_ms_input.setValue(blank.post_click_settle_ms)
        self.click_offset_x_input.setValue(blank.click_offset_x)
        self.click_offset_y_input.setValue(blank.click_offset_y)

    def _store_current_step(self) -> None:
        row = self.step_list.currentRow()
        if row < 0 or row >= len(self._steps):
            return
        self._steps[row] = AutomationStep(
            name=self.step_name_input.text().strip() or f"Step {row + 1}",
            template_path=Path(self.template_path_input.text().strip() or "templates/step.png"),
            match_threshold=float(self.threshold_input.value()),
            max_search_seconds=float(self.search_seconds_input.value()),
            max_scroll_attempts=int(self.scroll_attempts_input.value()),
            scroll_amount=int(self.scroll_amount_input.value()),
            max_click_attempts=int(self.click_attempts_input.value()),
            post_click_settle_ms=int(self.settle_ms_input.value()),
            click_offset_x=int(self.click_offset_x_input.value()),
            click_offset_y=int(self.click_offset_y_input.value()),
            template_missing=self._steps[row].template_missing,
        )
        item = self.step_list.item(row)
        if item is not None:
            item.setText(self._steps[row].name)

    def _emit_save_request(self) -> None:
        self._store_current_step()
        sequence_id = self._selected_sequence_id() or uuid4().hex
        sequence = AutomationSequence(
            id=sequence_id,
            name=self.sequence_name_input.text().strip() or "New sequence",
            target_window_rule=self.window_rule_input.text().strip() or None,
            steps=[replace(step) for step in self._steps],
        )
        self.sequenceSaveRequested.emit(sequence)

    def _emit_delete_request(self) -> None:
        sequence_id = self._selected_sequence_id()
        if sequence_id is not None:
            self.sequenceDeleteRequested.emit(sequence_id)

    def _emit_run_request(self) -> None:
        sequence_id = self._selected_sequence_id()
        if sequence_id is None:
            return
        self.runRequested.emit(sequence_id, self.window_combo.currentData())

    def _emit_dry_run_request(self) -> None:
        sequence_id = self._selected_sequence_id()
        if sequence_id is None:
            return
        step_index = self.step_list.currentRow()
        if step_index < 0:
            return
        self.dryRunRequested.emit(sequence_id, step_index, self.window_combo.currentData())

    def _add_step(self) -> None:
        self._store_current_step()
        self._steps.append(_default_step())
        self._refresh_step_list(select_row=len(self._steps) - 1)

    def _remove_step(self) -> None:
        row = self.step_list.currentRow()
        if row < 0 or row >= len(self._steps):
            return
        del self._steps[row]
        if not self._steps:
            self._steps = [_default_step()]
        self._refresh_step_list(select_row=min(row, len(self._steps) - 1))

    def _selected_sequence_id(self) -> str | None:
        row = self.sequence_list.currentRow()
        if row < 0 or row >= len(self._sequences):
            return None
        return self._sequences[row].id

    def _clone_sequence(self, sequence: AutomationSequence) -> AutomationSequence:
        return AutomationSequence(
            id=sequence.id,
            name=sequence.name,
            target_window_rule=sequence.target_window_rule,
            steps=[replace(step) for step in sequence.steps],
        )

    def _format_event(self, event: dict[str, object]) -> str:
        parts = [str(event.get("type", "event"))]
        if "step_index" in event:
            parts.append(f"step={event['step_index']}")
        if "reason" in event:
            parts.append(f"reason={event['reason']}")
        if "score" in event and isinstance(event.get("score"), (int, float)):
            parts.append(f"score={float(event['score']):.2f}")
        if "window_handle" in event:
            parts.append(f"window={event['window_handle']}")
        return " | ".join(parts)
