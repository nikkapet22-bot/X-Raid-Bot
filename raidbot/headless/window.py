from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from raidbot.desktop.chrome_profiles import ChromeProfile
from raidbot.headless.models import (
    HeadlessActionToggles,
    HeadlessAuthState,
    HeadlessRunResult,
)


EM_DASH = "\u2014"


class HeadlessWindow(QWidget):
    bootstrapRequested = Signal()
    startRequested = Signal()
    stopRequested = Signal()
    actionTogglesChanged = Signal(object)
    profileSelectionChanged = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("L8N Headless Raid Bot")

        root_layout = QVBoxLayout(self)
        controls_layout = QHBoxLayout()
        profile_layout = QHBoxLayout()
        actions_layout = QHBoxLayout()

        self.bootstrap_button = QPushButton("Import X Auth")
        self.start_button = QPushButton("Start")
        self.stop_button = QPushButton("Stop")
        controls_layout.addWidget(self.bootstrap_button)
        controls_layout.addWidget(self.start_button)
        controls_layout.addWidget(self.stop_button)

        self.profile_label = QLabel("Chrome Profile")
        self.profile_combo = QComboBox()
        profile_layout.addWidget(self.profile_label)
        profile_layout.addWidget(self.profile_combo, 1)

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
        self.runtime_status_label = QLabel("Runtime: Stopped")
        self.last_detected_label = QLabel(f"Last detected raid: {EM_DASH}")
        self.last_result_label = QLabel(f"Last result: {EM_DASH}")
        self.log_output = QPlainTextEdit()
        self.log_output.setReadOnly(True)

        root_layout.addLayout(controls_layout)
        root_layout.addLayout(profile_layout)
        root_layout.addLayout(actions_layout)
        root_layout.addWidget(self.auth_status_label)
        root_layout.addWidget(self.runtime_status_label)
        root_layout.addWidget(self.last_detected_label)
        root_layout.addWidget(self.last_result_label)
        root_layout.addWidget(self.log_output)

        self.bootstrap_button.clicked.connect(self.bootstrapRequested.emit)
        self.start_button.clicked.connect(self.startRequested.emit)
        self.stop_button.clicked.connect(self.stopRequested.emit)
        self.profile_combo.currentIndexChanged.connect(self._emit_profile_selection)

    def set_available_profiles(self, profiles: list[ChromeProfile] | list[str]) -> None:
        normalized_profiles = self._normalize_available_profiles(profiles)
        current_directory = self.selected_profile_directory()
        self.profile_combo.clear()
        for profile in normalized_profiles:
            self.profile_combo.addItem(
                self._format_profile(profile),
                profile.directory_name,
            )
        if current_directory is not None:
            self.set_selected_profile_directory(current_directory)

    def set_selected_profile_directory(self, profile_directory: str | None) -> None:
        if profile_directory is None:
            return
        index = self.profile_combo.findData(profile_directory)
        if index >= 0:
            was_blocked = self.profile_combo.blockSignals(True)
            self.profile_combo.setCurrentIndex(index)
            self.profile_combo.blockSignals(was_blocked)

    def selected_profile_directory(self) -> str | None:
        current = self.profile_combo.currentData()
        return str(current) if current is not None else None

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

    def set_runtime_running(self, running: bool) -> None:
        self.runtime_status_label.setText(f"Runtime: {'Running' if running else 'Stopped'}")

    def set_last_detected_raid(self, url: str | None) -> None:
        self.last_detected_label.setText(f"Last detected raid: {url or EM_DASH}")

    def set_last_result(self, result: HeadlessRunResult | None) -> None:
        if result is None:
            self.last_result_label.setText(f"Last result: {EM_DASH}")
            return
        self.last_result_label.setText(
            f"Last result: {result.reason} ({'ok' if result.success else 'fail'})"
        )

    def append_log(self, line: str) -> None:
        self.log_output.appendPlainText(line)

    def _emit_action_toggles(self) -> None:
        self.actionTogglesChanged.emit(self.action_toggles())

    def _emit_profile_selection(self) -> None:
        selected = self.selected_profile_directory()
        if selected is not None:
            self.profileSelectionChanged.emit(selected)

    def _normalize_available_profiles(
        self,
        profiles: list[ChromeProfile] | list[str],
    ) -> list[ChromeProfile]:
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

    def _format_profile(self, profile: ChromeProfile) -> str:
        if profile.label == profile.directory_name:
            return profile.label
        return f"{profile.label} [{profile.directory_name}]"
