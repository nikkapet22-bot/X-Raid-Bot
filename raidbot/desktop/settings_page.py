from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from raidbot.desktop.models import DesktopAppConfig
from raidbot.desktop.theme import SECTION_OBJECT_NAME


def _parse_int_field(text: str, *, field_name: str) -> int:
    value = text.strip()
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a valid integer.") from exc


def _parse_int_list(text: str, *, field_name: str) -> list[int]:
    values = []
    for part in text.split(","):
        stripped = part.strip()
        if not stripped:
            continue
        try:
            values.append(int(stripped))
        except ValueError as exc:
            raise ValueError(f"{field_name} must contain valid integers.") from exc
    return values


def _require_text(text: str, *, field_name: str) -> str:
    value = text.strip()
    if not value:
        raise ValueError(f"{field_name} is required.")
    return value


class SettingsPage(QWidget):
    applyRequested = Signal(object)
    reauthorizeRequested = Signal()

    def __init__(
        self,
        *,
        config: DesktopAppConfig,
        available_profiles: list[str],
        session_status: str,
        reauthorize_available: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._session_path = config.telegram_session_path
        self._phone_number = config.telegram_phone_number
        self._reauthorize_available = reauthorize_available

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        self.session_status_label = QLabel(session_status)
        self.reauthorize_button = QPushButton("Reauthorize")
        self.reauthorize_button.setProperty("variant", "secondary")
        self.reauthorize_button.clicked.connect(self.reauthorizeRequested.emit)
        self.reauthorize_button.setEnabled(reauthorize_available)
        self.reauthorize_hint_label = QLabel(
            "No in-app reauthorize flow is available. To re-enter setup, delete the saved desktop config file (`config.json` in the RaidBot app data folder) and restart the app."
            if not reauthorize_available
            else "Use this action to reauthorize the Telegram session when supported."
        )
        self.reauthorize_hint_label.setWordWrap(True)
        self.reauthorize_hint_label.setProperty("muted", True)
        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)

        session_layout = QFormLayout()
        session_layout.setContentsMargins(0, 0, 0, 0)
        session_layout.addRow("Status", self.session_status_label)
        session_action_row = QHBoxLayout()
        session_action_row.setContentsMargins(0, 0, 0, 0)
        session_action_row.addWidget(self.reauthorize_button, 0)
        session_action_row.addStretch(1)
        session_layout.addRow("Action", session_action_row)
        session_layout.addRow("", self.reauthorize_hint_label)
        self.session_section, self.session_surface = self._build_section(
            title="Session",
            description=(
                "Review current Telegram session state and reauthorize if needed."
                if reauthorize_available
                else "Review current Telegram session state. No in-app reauthorize flow is available."
            ),
            content_layout=session_layout,
        )
        layout.addWidget(self.session_section)

        telegram_layout = QFormLayout()
        telegram_layout.setContentsMargins(0, 0, 0, 0)
        self.api_id_input = QLineEdit(str(config.telegram_api_id))
        self.api_hash_input = QLineEdit(config.telegram_api_hash)
        self.api_id_input.setPlaceholderText("Telegram API ID")
        self.api_hash_input.setPlaceholderText("Telegram API Hash")
        advanced_api_hint = QLabel("Used only for the desktop Telegram session.")
        advanced_api_hint.setProperty("muted", True)
        advanced_api_hint.setWordWrap(True)
        telegram_layout.addRow("API ID", self.api_id_input)
        telegram_layout.addRow("", advanced_api_hint)
        telegram_layout.addRow("API Hash", self.api_hash_input)
        self.telegram_section, self.telegram_surface = self._build_section(
            title="Telegram",
            description="Advanced API credentials used by the desktop app session.",
            content_layout=telegram_layout,
        )
        layout.addWidget(self.telegram_section)

        routing_layout = QFormLayout()
        routing_layout.setContentsMargins(0, 0, 0, 0)
        whitelist_text = ", ".join(str(chat_id) for chat_id in config.whitelisted_chat_ids)
        self.whitelist_input = QLineEdit(whitelist_text)
        self.raidar_sender_input = QLineEdit(
            "" if config.raidar_sender_id is None else str(config.raidar_sender_id)
        )
        self.whitelist_input.setPlaceholderText("Comma-separated chat IDs")
        self.raidar_sender_input.setPlaceholderText("Raidar sender ID")
        self.profile_combo = QComboBox()
        for profile in available_profiles:
            self.profile_combo.addItem(profile)
        current_index = self.profile_combo.findText(config.chrome_profile_directory)
        if current_index >= 0:
            self.profile_combo.setCurrentIndex(current_index)
        routing_layout.addRow("Chat whitelist", self.whitelist_input)
        routing_hint = QLabel("Separate multiple chat IDs with commas.")
        routing_hint.setProperty("muted", True)
        routing_hint.setWordWrap(True)
        routing_layout.addRow("", routing_hint)
        routing_layout.addRow("Raidar sender", self.raidar_sender_input)
        self.raidar_sender_hint_label = QLabel("Required to start the bot.")
        self.raidar_sender_hint_label.setProperty("muted", True)
        self.raidar_sender_hint_label.setWordWrap(True)
        routing_layout.addRow("", self.raidar_sender_hint_label)
        routing_layout.addRow("Chrome profile", self.profile_combo)
        routing_layout.addRow(self.status_label)
        self.routing_section, self.routing_surface = self._build_section(
            title="Routing",
            description="Configure the chat whitelist, Raidar sender, and Chrome profile.",
            content_layout=routing_layout,
        )
        layout.addWidget(self.routing_section)

        self.save_button = QPushButton("Save")
        self.save_button.setProperty("variant", "primary")
        self.save_button.clicked.connect(self._emit_apply_request)
        layout.addWidget(self.save_button)
        layout.addStretch()

    def set_session_status(self, status: str) -> None:
        self.session_status_label.setText(status)

    def set_available_profiles(self, profiles: list[str]) -> None:
        current_profile = self.profile_combo.currentText()
        self.profile_combo.clear()
        for profile in profiles:
            self.profile_combo.addItem(profile)
        if current_profile:
            current_index = self.profile_combo.findText(current_profile)
            if current_index >= 0:
                self.profile_combo.setCurrentIndex(current_index)

    def _emit_apply_request(self) -> None:
        try:
            config = self._build_config()
        except ValueError as exc:
            self.status_label.setText(str(exc))
            return
        self.status_label.clear()
        self.applyRequested.emit(config)

    def _build_section(
        self,
        *,
        title: str,
        description: str,
        content_layout: QFormLayout,
    ) -> tuple[QWidget, QWidget]:
        section = QFrame()
        section.setObjectName("settingsSection")

        section_layout = QVBoxLayout(section)
        section_layout.setContentsMargins(0, 0, 0, 0)
        section_layout.setSpacing(0)

        surface = QWidget()
        surface.setObjectName(SECTION_OBJECT_NAME)
        section_layout.addWidget(surface)

        surface_layout = QVBoxLayout(surface)
        surface_layout.setContentsMargins(18, 18, 18, 18)
        surface_layout.setSpacing(12)

        title_label = QLabel(title)
        description_label = QLabel(description)
        description_label.setWordWrap(True)
        description_label.setProperty("muted", True)

        surface_layout.addWidget(title_label)
        surface_layout.addWidget(description_label)
        surface_layout.addLayout(content_layout)
        return section, surface

    def _build_config(self) -> DesktopAppConfig:
        whitelist = _parse_int_list(self.whitelist_input.text(), field_name="Chat whitelist")
        raidar_sender = _require_text(self.raidar_sender_input.text(), field_name="Raidar sender ID")
        return DesktopAppConfig(
            telegram_api_id=_parse_int_field(self.api_id_input.text(), field_name="Telegram API ID"),
            telegram_api_hash=_require_text(
                self.api_hash_input.text(),
                field_name="Telegram API Hash",
            ),
            telegram_session_path=Path(self._session_path),
            telegram_phone_number=self._phone_number,
            whitelisted_chat_ids=whitelist,
            raidar_sender_id=_parse_int_field(raidar_sender, field_name="Raidar sender ID"),
            chrome_profile_directory=self.profile_combo.currentText(),
        )
