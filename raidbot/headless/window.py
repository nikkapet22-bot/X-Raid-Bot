from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from raidbot.headless.models import HeadlessActionToggles, HeadlessAuthState, HeadlessRunResult


class HeadlessWindow(QWidget):
    bootstrapRequested = Signal()
    startRequested = Signal()
    stopRequested = Signal()
    actionTogglesChanged = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("L8N Headless Raid Bot")

        root_layout = QVBoxLayout(self)
        controls_layout = QHBoxLayout()
        actions_layout = QHBoxLayout()

        self.bootstrap_button = QPushButton("Bootstrap Login")
        self.start_button = QPushButton("Start")
        self.stop_button = QPushButton("Stop")
        controls_layout.addWidget(self.bootstrap_button)
        controls_layout.addWidget(self.start_button)
        controls_layout.addWidget(self.stop_button)

        self.reply_checkbox = QCheckBox("Reply")
        self.like_checkbox = QCheckBox("Like")
        self.repost_checkbox = QCheckBox("Repost")
        self.bookmark_checkbox = QCheckBox("Bookmark")
        for checkbox in (
            self.reply_checkbox,
            self.like_checkbox,
            self.repost_checkbox,
            self.bookmark_checkbox,
        ):
            checkbox.setChecked(True)
            checkbox.toggled.connect(self._emit_action_toggles)
            actions_layout.addWidget(checkbox)

        self.auth_status_label = QLabel("X Auth: Needs Login")
        self.last_detected_label = QLabel("Last detected raid: —")
        self.last_result_label = QLabel("Last result: —")
        self.log_output = QPlainTextEdit()
        self.log_output.setReadOnly(True)

        root_layout.addLayout(controls_layout)
        root_layout.addLayout(actions_layout)
        root_layout.addWidget(self.auth_status_label)
        root_layout.addWidget(self.last_detected_label)
        root_layout.addWidget(self.last_result_label)
        root_layout.addWidget(self.log_output)

        self.bootstrap_button.clicked.connect(self.bootstrapRequested.emit)
        self.start_button.clicked.connect(self.startRequested.emit)
        self.stop_button.clicked.connect(self.stopRequested.emit)

    def action_toggles(self) -> HeadlessActionToggles:
        return HeadlessActionToggles(
            reply=self.reply_checkbox.isChecked(),
            like=self.like_checkbox.isChecked(),
            repost=self.repost_checkbox.isChecked(),
            bookmark=self.bookmark_checkbox.isChecked(),
        )

    def set_auth_state(self, auth_state: HeadlessAuthState) -> None:
        text = "Authenticated" if auth_state.status == "authenticated" else "Needs Login"
        self.auth_status_label.setText(f"X Auth: {text}")

    def set_last_detected_raid(self, url: str | None) -> None:
        self.last_detected_label.setText(f"Last detected raid: {url or '—'}")

    def set_last_result(self, result: HeadlessRunResult | None) -> None:
        if result is None:
            self.last_result_label.setText("Last result: —")
            return
        self.last_result_label.setText(
            f"Last result: {result.reason} ({'ok' if result.success else 'fail'})"
        )

    def append_log(self, line: str) -> None:
        self.log_output.appendPlainText(line)

    def _emit_action_toggles(self) -> None:
        self.actionTogglesChanged.emit(self.action_toggles())
