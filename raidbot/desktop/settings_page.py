from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from raidbot.desktop.chrome_profiles import ChromeProfile
from raidbot.desktop.models import DesktopAppConfig, RaidProfileConfig
from raidbot.desktop.telegram_setup import AccessibleChat
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


def _parse_required_int_list(text: str, *, field_name: str) -> list[int]:
    value = text.strip()
    if not value:
        raise ValueError(f"{field_name} is required.")
    return _parse_int_list(value, field_name=field_name)


def _require_text(text: str, *, field_name: str) -> str:
    value = text.strip()
    if not value:
        raise ValueError(f"{field_name} is required.")
    return value
class SettingsPage(QWidget):
    applyRequested = Signal(object)
    senderScanRequested = Signal(object, object)
    reauthorizeRequested = Signal()
    raidProfileAddRequested = Signal(str, str)
    raidProfileRemoveRequested = Signal(str)
    raidProfileMoveRequested = Signal(str, str)

    def __init__(
        self,
        *,
        config: DesktopAppConfig,
        available_profiles: list[ChromeProfile] | list[str],
        available_chats: list[AccessibleChat] | None = None,
        session_status: str,
        reauthorize_available: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._session_path = config.telegram_session_path
        self._phone_number = config.telegram_phone_number
        self._reauthorize_available = reauthorize_available
        self._available_profiles: list[ChromeProfile] = []
        self._available_chats: list[AccessibleChat] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 24, 12, 24)
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
        self.chat_row_widgets: list[QWidget] = []
        self.chat_row_combos: list[QComboBox] = []
        self.chat_remove_buttons: list[QPushButton] = []
        self.chat_rows_container = QWidget()
        self.chat_rows_layout = QVBoxLayout(self.chat_rows_container)
        self.chat_rows_layout.setContentsMargins(0, 0, 0, 0)
        self.chat_rows_layout.setSpacing(8)
        self.add_chat_button = QPushButton("Add chat")
        self.add_chat_button.setProperty("variant", "secondary")
        self.add_chat_button.clicked.connect(self._handle_add_chat_row)
        self.sender_row_widgets: list[QWidget] = []
        self.sender_entry_inputs: list[QLineEdit] = []
        self.sender_scan_buttons: list[QPushButton] = []
        self.sender_remove_buttons: list[QPushButton] = []
        self.sender_rows_container = QWidget()
        self.sender_rows_layout = QVBoxLayout(self.sender_rows_container)
        self.sender_rows_layout.setContentsMargins(0, 0, 0, 0)
        self.sender_rows_layout.setSpacing(8)
        self.add_sender_button = QPushButton("Add sender")
        self.add_sender_button.setProperty("variant", "secondary")
        self.add_sender_button.clicked.connect(self._handle_add_sender_row)
        self.available_profile_combo = QComboBox()
        self.profile_combo = self.available_profile_combo
        self.add_profile_button = QPushButton("Add profile")
        self.add_profile_button.setProperty("variant", "secondary")
        self.add_profile_button.clicked.connect(self._emit_add_profile_request)
        self.raid_profiles_list = QListWidget()
        self.raid_profiles_list.currentRowChanged.connect(
            lambda _row: self._sync_raid_profile_action_buttons()
        )
        self.remove_profile_button = QPushButton("Remove")
        self.remove_profile_button.setProperty("variant", "secondary")
        self.remove_profile_button.clicked.connect(self._emit_remove_profile_request)
        self.move_profile_up_button = QPushButton("Move up")
        self.move_profile_up_button.setProperty("variant", "secondary")
        self.move_profile_up_button.clicked.connect(
            lambda: self._emit_move_profile_request("up")
        )
        self.move_profile_down_button = QPushButton("Move down")
        self.move_profile_down_button.setProperty("variant", "secondary")
        self.move_profile_down_button.clicked.connect(
            lambda: self._emit_move_profile_request("down")
        )
        self.set_available_profiles(available_profiles)
        self._refresh_raid_profiles_list()
        chat_actions = QHBoxLayout()
        chat_actions.setContentsMargins(0, 0, 0, 0)
        chat_actions.addWidget(self.add_chat_button, 0)
        chat_actions.addStretch(1)
        chat_editor = QWidget()
        chat_editor_layout = QVBoxLayout(chat_editor)
        chat_editor_layout.setContentsMargins(0, 0, 0, 0)
        chat_editor_layout.setSpacing(8)
        chat_editor_layout.addWidget(self.chat_rows_container)
        chat_editor_layout.addLayout(chat_actions)
        routing_layout.addRow("Allowed chats", chat_editor)
        self.allowed_chats_hint_label = QLabel("")
        self.allowed_chats_hint_label.setProperty("muted", True)
        self.allowed_chats_hint_label.setWordWrap(True)
        routing_layout.addRow("", self.allowed_chats_hint_label)
        default_available_chats = (
            available_chats
            if available_chats is not None
            else [
                AccessibleChat(chat_id=int(chat_id), title=str(chat_id))
                for chat_id in config.whitelisted_chat_ids
            ]
        )
        self.set_available_chats(default_available_chats)
        allowed_sender_entries = config.allowed_sender_entries or tuple(
            str(sender_id) for sender_id in config.allowed_sender_ids
        )
        self._rebuild_sender_rows(allowed_sender_entries)
        sender_actions = QHBoxLayout()
        sender_actions.setContentsMargins(0, 0, 0, 0)
        sender_actions.addWidget(self.add_sender_button, 0)
        sender_actions.addStretch(1)
        sender_editor = QWidget()
        sender_editor_layout = QVBoxLayout(sender_editor)
        sender_editor_layout.setContentsMargins(0, 0, 0, 0)
        sender_editor_layout.setSpacing(8)
        sender_editor_layout.addWidget(self.sender_rows_container)
        sender_editor_layout.addLayout(sender_actions)
        routing_layout.addRow("Allowed senders", sender_editor)
        self.allowed_senders_hint_label = QLabel("Required to start the bot.")
        self.allowed_senders_hint_label.setProperty("muted", True)
        self.allowed_senders_hint_label.setWordWrap(True)
        routing_layout.addRow("", self.allowed_senders_hint_label)
        raid_profiles_editor = QWidget()
        raid_profiles_layout = QVBoxLayout(raid_profiles_editor)
        raid_profiles_layout.setContentsMargins(0, 0, 0, 0)
        raid_profiles_layout.setSpacing(8)
        available_profile_row = QHBoxLayout()
        available_profile_row.setContentsMargins(0, 0, 0, 0)
        available_profile_row.addWidget(self.available_profile_combo, 1)
        available_profile_row.addWidget(self.add_profile_button, 0)
        raid_profiles_layout.addLayout(available_profile_row)
        raid_profiles_layout.addWidget(self.raid_profiles_list)
        raid_profile_actions = QHBoxLayout()
        raid_profile_actions.setContentsMargins(0, 0, 0, 0)
        raid_profile_actions.addWidget(self.remove_profile_button, 0)
        raid_profile_actions.addWidget(self.move_profile_up_button, 0)
        raid_profile_actions.addWidget(self.move_profile_down_button, 0)
        raid_profile_actions.addStretch(1)
        raid_profiles_layout.addLayout(raid_profile_actions)
        routing_layout.addRow("Raid profiles", raid_profiles_editor)
        self.routing_section, self.routing_surface = self._build_section(
            title="Routing",
            description="Configure the chat whitelist, sender allowlist, and ordered detected raid profiles.",
            content_layout=routing_layout,
        )
        layout.addWidget(self.routing_section)

        self.save_button = QPushButton("Save")
        self.save_button.setProperty("variant", "primary")
        self.save_button.clicked.connect(self._emit_apply_request)
        layout.addWidget(self.save_button)
        layout.addWidget(self.status_label)
        layout.addStretch()

    def set_session_status(self, status: str) -> None:
        self.session_status_label.setText(status)

    def set_config(self, config: DesktopAppConfig) -> None:
        self._config = config
        self._rebuild_chat_rows(config.whitelisted_chat_ids)
        allowed_sender_entries = config.allowed_sender_entries or tuple(
            str(sender_id) for sender_id in config.allowed_sender_ids
        )
        self._rebuild_sender_rows(allowed_sender_entries)
        self._refresh_raid_profiles_list()

    def set_available_chats(self, chats: list[AccessibleChat]) -> None:
        selected_chat_ids = self._selected_chat_row_ids()
        if not selected_chat_ids:
            selected_chat_ids = list(self._config.whitelisted_chat_ids)
        self._available_chats = self._normalize_available_chats(chats)
        self._rebuild_chat_rows(selected_chat_ids)
        self._update_allowed_chats_hint()

    def set_available_profiles(self, profiles: list[ChromeProfile] | list[str]) -> None:
        current_profile_directory = self.available_profile_combo.currentData()
        self._available_profiles = self._normalize_available_profiles(profiles)
        self.available_profile_combo.clear()
        for profile in self._available_profiles:
            self.available_profile_combo.addItem(
                self._format_available_profile(profile),
                profile.directory_name,
            )
        current_index = self.available_profile_combo.findData(current_profile_directory)
        if current_index >= 0:
            self.available_profile_combo.setCurrentIndex(current_index)
        self._sync_raid_profile_action_buttons()

    def _emit_apply_request(self) -> None:
        try:
            config = self._build_config()
        except ValueError as exc:
            self.show_error(str(exc))
            return
        self.status_label.clear()
        self.status_label.setStyleSheet("")
        self.applyRequested.emit(config)

    def show_error(self, message: str) -> None:
        self.status_label.setText(f"⚠  {message}")
        self.status_label.setStyleSheet("color: #f87171; font-weight: 500;")

    def show_success(self, message: str) -> None:
        self.status_label.setText(f"✓  {message}")
        self.status_label.setStyleSheet("color: #2dd4bf; font-weight: 500;")

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
        surface_layout.setContentsMargins(20, 20, 20, 20)
        surface_layout.setSpacing(14)

        title_label = QLabel(title)
        title_label.setObjectName("sectionTitle")

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet(
            "background: #1e3252; max-height: 1px; border: none;"
        )

        description_label = QLabel(description)
        description_label.setWordWrap(True)
        description_label.setProperty("muted", True)

        content_layout.setVerticalSpacing(10)
        content_layout.setHorizontalSpacing(20)

        surface_layout.addWidget(title_label)
        surface_layout.addWidget(divider)
        surface_layout.addWidget(description_label)
        surface_layout.addLayout(content_layout)
        return section, surface

    def _build_config(self) -> DesktopAppConfig:
        whitelist = self._parse_required_chat_ids()
        allowed_sender_entries = self._parse_required_sender_entries()
        allowed_sender_ids = [
            int(entry)
            for entry in allowed_sender_entries
            if entry.lstrip("-").isdigit()
        ]
        return replace(
            self._config,
            telegram_api_id=_parse_int_field(self.api_id_input.text(), field_name="Telegram API ID"),
            telegram_api_hash=_require_text(
                self.api_hash_input.text(),
                field_name="Telegram API Hash",
            ),
            telegram_session_path=Path(self._session_path),
            telegram_phone_number=self._phone_number,
            whitelisted_chat_ids=whitelist,
            allowed_sender_ids=allowed_sender_ids,
            allowed_sender_entries=allowed_sender_entries,
            chrome_profile_directory=(
                self._config.raid_profiles[0].profile_directory
                if self._config.raid_profiles
                else self._config.chrome_profile_directory
            ),
        )

    def _parse_required_sender_entries(self) -> tuple[str, ...]:
        entries = tuple(
            entry_input.text().strip()
            for entry_input in self.sender_entry_inputs
            if entry_input.text().strip()
        )
        if not entries:
            raise ValueError("At least one allowed sender is required.")
        return entries

    def _parse_required_chat_ids(self) -> list[int]:
        selected_chat_ids: list[int] = []
        seen_chat_ids: set[int] = set()
        available_chat_ids = {chat.chat_id for chat in self._available_chats}
        for combo in self.chat_row_combos:
            chat_id = combo.currentData()
            if chat_id is None:
                continue
            if combo.property("staleSelection") or int(chat_id) not in available_chat_ids:
                raise ValueError(
                    "Allowed chats contain chats that are no longer available."
                )
            normalized_chat_id = int(chat_id)
            if normalized_chat_id in seen_chat_ids:
                continue
            seen_chat_ids.add(normalized_chat_id)
            selected_chat_ids.append(normalized_chat_id)
        if not selected_chat_ids:
            raise ValueError("At least one allowed chat is required.")
        return selected_chat_ids

    def selected_chat_ids(self) -> list[int]:
        return self._selected_chat_row_ids()

    def _handle_add_chat_row(self) -> None:
        if not self._available_chats:
            return
        self._add_chat_row(None)

    def _add_chat_row(self, chat_id: int | None) -> None:
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)
        combo = QComboBox()
        self._populate_chat_combo(combo, chat_id)
        remove_button = QPushButton("Remove")
        remove_button.setProperty("variant", "secondary")
        remove_button.clicked.connect(lambda: self._remove_chat_row(row_widget))
        row_layout.addWidget(combo, 1)
        row_layout.addWidget(remove_button, 0)
        self.chat_rows_layout.addWidget(row_widget)
        self.chat_row_widgets.append(row_widget)
        self.chat_row_combos.append(combo)
        self.chat_remove_buttons.append(remove_button)
        self._sync_chat_remove_buttons()

    def _remove_chat_row(self, row_widget: QWidget) -> None:
        index = self.chat_row_widgets.index(row_widget)
        if len(self.chat_row_widgets) == 1:
            return
        removed_widget = self.chat_row_widgets.pop(index)
        self.chat_row_combos.pop(index)
        self.chat_remove_buttons.pop(index)
        self.chat_rows_layout.removeWidget(removed_widget)
        removed_widget.deleteLater()
        self._sync_chat_remove_buttons()

    def _sync_chat_remove_buttons(self) -> None:
        allow_remove = len(self.chat_remove_buttons) > 1
        for button in self.chat_remove_buttons:
            button.setEnabled(allow_remove)

    def _selected_chat_row_ids(self) -> list[int]:
        selected_chat_ids: list[int] = []
        for combo in self.chat_row_combos:
            chat_id = combo.currentData()
            if chat_id is not None:
                selected_chat_ids.append(int(chat_id))
        return selected_chat_ids

    def _rebuild_chat_rows(self, chat_ids: list[int] | tuple[int, ...]) -> None:
        while self.chat_rows_layout.count():
            item = self.chat_rows_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.chat_row_widgets = []
        self.chat_row_combos = []
        self.chat_remove_buttons = []
        desired_chat_ids = list(chat_ids)
        if not desired_chat_ids and self._available_chats:
            desired_chat_ids = [self._available_chats[0].chat_id]
        for chat_id in desired_chat_ids:
            self._add_chat_row(int(chat_id))
        self.add_chat_button.setEnabled(bool(self._available_chats))
        self._sync_chat_remove_buttons()

    def _populate_chat_combo(self, combo: QComboBox, selected_chat_id: int | None) -> None:
        combo.clear()
        combo.setProperty("staleSelection", False)
        available_chat_ids = {chat.chat_id for chat in self._available_chats}
        if selected_chat_id is not None and int(selected_chat_id) not in available_chat_ids:
            combo.addItem(f"Missing chat [{int(selected_chat_id)}]", int(selected_chat_id))
            combo.setProperty("staleSelection", True)
        for chat in self._available_chats:
            combo.addItem(self._format_available_chat(chat), chat.chat_id)
        if combo.count() == 0:
            combo.addItem("No detected chats", None)
            combo.setEnabled(False)
            return
        combo.setEnabled(True)
        if selected_chat_id is None:
            combo.setCurrentIndex(0)
            return
        selected_index = combo.findData(int(selected_chat_id))
        if selected_index >= 0:
            combo.setCurrentIndex(selected_index)

    def _normalize_available_chats(self, chats: list[AccessibleChat]) -> list[AccessibleChat]:
        unique_chats: dict[int, AccessibleChat] = {}
        for chat in chats:
            unique_chats[int(chat.chat_id)] = AccessibleChat(
                chat_id=int(chat.chat_id),
                title=str(chat.title),
            )
        return sorted(unique_chats.values(), key=lambda chat: chat.title.lower())

    def _format_available_chat(self, chat: AccessibleChat) -> str:
        return f"{chat.title} [{chat.chat_id}]"

    def _update_allowed_chats_hint(self) -> None:
        if self._available_chats:
            self.allowed_chats_hint_label.setText(
                "Detected from the saved Telegram session."
            )
            return
        self.allowed_chats_hint_label.setText(
            "No Telegram chats detected from the saved session."
        )

    def _handle_add_sender_row(self) -> None:
        self._add_sender_row("")

    def _add_sender_row(self, text: str) -> None:
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)
        entry_input = QLineEdit(text)
        entry_input.setPlaceholderText("Sender username or ID")
        scan_button = QPushButton("Scan")
        scan_button.setProperty("variant", "secondary")
        scan_button.clicked.connect(
            lambda: self._emit_sender_scan_request(scan_button)
        )
        remove_button = QPushButton("Remove")
        remove_button.setProperty("variant", "secondary")
        remove_button.clicked.connect(lambda: self._remove_sender_row(row_widget))
        row_layout.addWidget(entry_input, 1)
        row_layout.addWidget(scan_button, 0)
        row_layout.addWidget(remove_button, 0)
        self.sender_rows_layout.addWidget(row_widget)
        self.sender_row_widgets.append(row_widget)
        self.sender_entry_inputs.append(entry_input)
        self.sender_scan_buttons.append(scan_button)
        self.sender_remove_buttons.append(remove_button)
        self._sync_sender_remove_buttons()

    def _emit_sender_scan_request(self, button: QPushButton) -> None:
        self.set_sender_scan_button_busy(button, True)
        self.senderScanRequested.emit(button, self.selected_chat_ids())

    def set_sender_scan_button_busy(self, button: QPushButton, busy: bool) -> None:
        button.setText("Scanning..." if busy else "Scan")
        button.setEnabled(not busy)

    def _remove_sender_row(self, row_widget: QWidget) -> None:
        index = self.sender_row_widgets.index(row_widget)
        if len(self.sender_row_widgets) == 1:
            self.sender_entry_inputs[0].clear()
            return
        removed_widget = self.sender_row_widgets.pop(index)
        self.sender_entry_inputs.pop(index)
        self.sender_scan_buttons.pop(index)
        self.sender_remove_buttons.pop(index)
        self.sender_rows_layout.removeWidget(removed_widget)
        removed_widget.deleteLater()
        self._sync_sender_remove_buttons()

    def _sync_sender_remove_buttons(self) -> None:
        allow_remove = len(self.sender_remove_buttons) > 1
        for button in self.sender_remove_buttons:
            button.setEnabled(allow_remove)

    def _rebuild_sender_rows(self, entries: tuple[str, ...] | list[str]) -> None:
        while self.sender_rows_layout.count():
            item = self.sender_rows_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.sender_row_widgets = []
        self.sender_entry_inputs = []
        self.sender_scan_buttons = []
        self.sender_remove_buttons = []
        desired_entries = [str(entry).strip() for entry in entries if str(entry).strip()]
        if not desired_entries:
            desired_entries = [""]
        for entry in desired_entries:
            self._add_sender_row(entry)

    def append_allowed_sender_entries(self, entries: list[str] | tuple[str, ...]) -> None:
        normalized_entries = [
            str(entry).strip() for entry in entries if str(entry).strip()
        ]
        if not normalized_entries:
            return
        existing_entries = [
            entry_input.text().strip()
            for entry_input in self.sender_entry_inputs
            if entry_input.text().strip()
        ]
        if (
            len(self.sender_entry_inputs) == 1
            and not self.sender_entry_inputs[0].text().strip()
        ):
            self.sender_entry_inputs[0].setText(normalized_entries[0])
            existing_entries = [normalized_entries[0]]
            normalized_entries = normalized_entries[1:]
        seen_entries = set(existing_entries)
        for entry in normalized_entries:
            if entry in seen_entries:
                continue
            self._add_sender_row(entry)
            seen_entries.add(entry)

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

    def _format_available_profile(self, profile: ChromeProfile) -> str:
        if profile.label == profile.directory_name:
            return profile.label
        return f"{profile.label} [{profile.directory_name}]"

    def _format_raid_profile(self, profile: RaidProfileConfig) -> str:
        if profile.label == profile.profile_directory:
            return profile.label
        return f"{profile.label} [{profile.profile_directory}]"

    def _refresh_raid_profiles_list(self) -> None:
        selected_directory = self._selected_raid_profile_directory()
        self.raid_profiles_list.clear()
        for profile in self._config.raid_profiles:
            item = QListWidgetItem(self._format_raid_profile(profile))
            item.setData(1, profile.profile_directory)
            self.raid_profiles_list.addItem(item)
        if self.raid_profiles_list.count():
            if selected_directory is None:
                self.raid_profiles_list.setCurrentRow(0)
            else:
                for index in range(self.raid_profiles_list.count()):
                    item = self.raid_profiles_list.item(index)
                    if item is not None and item.data(1) == selected_directory:
                        self.raid_profiles_list.setCurrentRow(index)
                        break
                else:
                    self.raid_profiles_list.setCurrentRow(0)
        self._sync_raid_profile_action_buttons()

    def _selected_raid_profile_directory(self) -> str | None:
        item = self.raid_profiles_list.currentItem()
        if item is None:
            return None
        return item.data(1)

    def _emit_add_profile_request(self) -> None:
        current_index = self.available_profile_combo.currentIndex()
        if current_index < 0 or current_index >= len(self._available_profiles):
            return
        selected_profile = self._available_profiles[current_index]
        self.status_label.setText("Adding profile...")
        self.raidProfileAddRequested.emit(
            selected_profile.directory_name,
            selected_profile.label,
        )

    def _emit_remove_profile_request(self) -> None:
        profile_directory = self._selected_raid_profile_directory()
        if profile_directory is None:
            return
        self.status_label.setText("Removing profile...")
        self.raidProfileRemoveRequested.emit(profile_directory)

    def _emit_move_profile_request(self, direction: str) -> None:
        profile_directory = self._selected_raid_profile_directory()
        if profile_directory is None:
            return
        self.status_label.setText("Reordering profiles...")
        self.raidProfileMoveRequested.emit(profile_directory, direction)

    def _sync_raid_profile_action_buttons(self) -> None:
        has_selection = self._selected_raid_profile_directory() is not None
        current_row = self.raid_profiles_list.currentRow()
        profile_count = self.raid_profiles_list.count()
        self.remove_profile_button.setEnabled(has_selection and profile_count > 1)
        self.move_profile_up_button.setEnabled(has_selection and current_row > 0)
        self.move_profile_down_button.setEnabled(
            has_selection and current_row >= 0 and current_row < profile_count - 1
        )
