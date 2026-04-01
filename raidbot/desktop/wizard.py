from __future__ import annotations

import asyncio
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTextEdit,
    QWidget,
    QVBoxLayout,
    QWizard,
    QWizardPage,
)

from raidbot.desktop.branding import APP_NAME, SETUP_WINDOW_TITLE
from raidbot.desktop.chrome_profiles import ChromeEnvironment, ChromeProfile, detect_chrome_environment
from raidbot.desktop.models import DesktopAppConfig
from raidbot.desktop.telegram_setup import SUPPORTED_RAID_BOT_IDENTIFIERS, SessionStatus


def _create_page_shell(page: QWizardPage, *, title: str, subtitle: str) -> tuple[QVBoxLayout, QWidget]:
    root = QVBoxLayout(page)
    root.setContentsMargins(24, 24, 24, 24)
    root.setSpacing(16)

    header = QFrame()
    header.setObjectName("wizardHeader")
    header_layout = QVBoxLayout(header)
    header_layout.setContentsMargins(0, 0, 0, 0)
    header_layout.setSpacing(6)

    headline = QLabel(title)
    headline.setObjectName("wizardHeadline")
    subtitle_label = QLabel(subtitle)
    subtitle_label.setObjectName("wizardSubtitle")
    subtitle_label.setProperty("muted", True)
    subtitle_label.setWordWrap(True)

    page.page_headline_label = headline
    page.page_subtitle_label = subtitle_label

    header_layout.addWidget(headline)
    header_layout.addWidget(subtitle_label)
    root.addWidget(header)

    surface = QWidget()
    surface.setObjectName("wizardSurface")
    root.addWidget(surface)

    return root, surface


def _create_surface_layout(surface: QWidget) -> QVBoxLayout:
    layout = QVBoxLayout(surface)
    layout.setContentsMargins(20, 20, 20, 20)
    layout.setSpacing(12)
    return layout


def _parse_int_field(text: str, *, field_name: str) -> int:
    value = text.strip()
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a valid integer.") from exc


def _parse_int_list_field(text: str, *, field_name: str) -> list[int]:
    values = [chunk.strip() for chunk in text.replace("\n", ",").split(",")]
    parsed_values: list[int] = []
    for value in values:
        if not value:
            continue
        try:
            parsed_values.append(int(value))
        except ValueError as exc:
            raise ValueError(f"{field_name} must be valid integers.") from exc
    return parsed_values


def _is_supported_raid_candidate_label(label: str) -> bool:
    normalized = label.strip().lower().lstrip("@")
    return normalized in SUPPORTED_RAID_BOT_IDENTIFIERS


class SetupWizard(QWizard):
    NextButton = QWizard.WizardButton.NextButton
    BackButton = QWizard.WizardButton.BackButton
    CancelButton = QWizard.WizardButton.CancelButton
    FinishButton = QWizard.WizardButton.FinishButton

    def __init__(
        self,
        *,
        storage,
        telegram_service_factory,
        chrome_environment: ChromeEnvironment | None = None,
        chrome_environment_factory=detect_chrome_environment,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.storage = storage
        self.telegram_service_factory = telegram_service_factory
        self.chrome_environment = chrome_environment
        self.chrome_environment_factory = chrome_environment_factory
        self.telegram_service = None
        self.start_now_requested = False

        self.setWindowTitle(SETUP_WINDOW_TITLE)
        self.setWizardStyle(QWizard.WizardStyle.ModernStyle)
        self.setMinimumSize(920, 700)

        self.welcome_page = WelcomePage()
        self.telegram_page = TelegramAuthorizationPage()
        self.chat_page = ChatDiscoveryPage()
        self.raidar_page = RaidarSelectionPage()
        self.chrome_page = ChromeProfilePage()
        self.review_page = ReviewPage()

        self.chat_page.completeChanged.connect(
            self.raidar_page.reset_for_chat_selection_change
        )

        for page in (
            self.welcome_page,
            self.telegram_page,
            self.chat_page,
            self.raidar_page,
            self.chrome_page,
            self.review_page,
        ):
            self.addPage(page)

        self.button(self.NextButton).setProperty("variant", "primary")
        self.button(self.FinishButton).setProperty("variant", "primary")
        self.button(self.BackButton).setProperty("variant", "secondary")
        self.button(self.CancelButton).setProperty("variant", "quiet")

    def session_path(self) -> Path:
        return self.storage.base_dir / "telegram" / "raidbot.session"

    def build_telegram_service(self):
        if self.telegram_service is not None:
            return self.telegram_service
        self.session_path().parent.mkdir(parents=True, exist_ok=True)
        self.telegram_service = self.telegram_service_factory(
            _parse_int_field(self.telegram_page.api_id_input.text(), field_name="Telegram API ID"),
            self.telegram_page.api_hash_input.text().strip(),
            self.session_path(),
        )
        return self.telegram_service

    def ensure_chrome_environment(self) -> ChromeEnvironment:
        if self.chrome_environment is None:
            self.chrome_environment = self.chrome_environment_factory()
        return self.chrome_environment

    def build_config(self) -> DesktopAppConfig:
        return DesktopAppConfig(
            telegram_api_id=_parse_int_field(
                self.telegram_page.api_id_input.text(), field_name="Telegram API ID"
            ),
            telegram_api_hash=self.telegram_page.api_hash_input.text().strip(),
            telegram_session_path=self.session_path(),
            telegram_phone_number=self.telegram_page.phone_input.text().strip() or None,
            whitelisted_chat_ids=self.chat_page.selected_chat_ids(),
            allowed_sender_ids=self.raidar_page.selected_sender_ids(),
            allowed_sender_entries=self.raidar_page.selected_sender_entries(),
            chrome_profile_directory=self.chrome_page.selected_profile_directory(),
        )


class WelcomePage(QWizardPage):
    def __init__(self) -> None:
        super().__init__()
        _root, self.surface = _create_page_shell(
            self,
            title=f"Set Up {APP_NAME}",
            subtitle="A guided onboarding flow for Telegram access, supported raid senders, and a dedicated raid browser profile.",
        )
        layout = _create_surface_layout(self.surface)

        self.description_label = QLabel(
            "Configure Telegram access, supported raid senders, and the dedicated raid browser profile used for raids."
        )
        self.note_label = QLabel(
            "Chrome should already be logged into X in the profile you select."
        )
        self.checklist_label = QLabel(
            "What you'll configure:\n"
            "• Telegram session\n"
            "• Whitelisted chats\n"
            "• Allowed raid senders\n"
            "• Raid browser profile"
        )
        for label in (self.description_label, self.note_label, self.checklist_label):
            label.setWordWrap(True)
        self.note_label.setProperty("muted", True)
        self.checklist_label.setObjectName("wizardChecklist")

        layout.addWidget(self.description_label)
        layout.addWidget(self.note_label)
        layout.addWidget(self.checklist_label)
        layout.addStretch(1)


class TelegramAuthorizationPage(QWizardPage):
    def __init__(self) -> None:
        super().__init__()
        self.authorized = False
        self.code_requested = False
        self.status_label = QLabel("")
        self.api_id_input = QLineEdit()
        self.api_hash_input = QLineEdit()
        self.phone_input = QLineEdit()
        self.code_input = QLineEdit()
        self.password_input = QLineEdit()
        self.send_code_button = QPushButton("Send Code")
        self.password_help_label = QLabel(
            "If you have 2FA enabled, enter your Telegram password. Otherwise skip this step."
        )
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.send_code_button.setProperty("variant", "secondary")
        self.send_code_button.clicked.connect(self._handle_send_code)

        _root, self.surface = _create_page_shell(
            self,
            title="Telegram Access",
            subtitle="Connect the Telegram session used to discover chats and confirm allowed raid senders.",
        )
        surface_layout = _create_surface_layout(self.surface)
        self.helper_label = QLabel(
            "Enter your Telegram API credentials. If a session already exists, you can continue without re-entering the login code. This session is used to discover chats and confirm allowed raid senders."
        )
        self.helper_label.setWordWrap(True)
        self.helper_label.setProperty("muted", True)
        surface_layout.addWidget(self.helper_label)

        code_row = QWidget()
        code_row_layout = QHBoxLayout(code_row)
        code_row_layout.setContentsMargins(0, 0, 0, 0)
        code_row_layout.setSpacing(8)
        code_row_layout.addWidget(self.code_input, 1)
        code_row_layout.addWidget(self.send_code_button, 0)

        layout = QFormLayout()
        layout.addRow("API ID", self.api_id_input)
        layout.addRow("API Hash", self.api_hash_input)
        layout.addRow("Phone", self.phone_input)
        layout.addRow("Telegram Code", code_row)
        layout.addRow("2FA Password (optional)", self.password_input)
        layout.addRow("", self.password_help_label)
        layout.addRow(self.status_label)
        surface_layout.addLayout(layout)
        self.status_label.setWordWrap(True)
        self.password_help_label.setWordWrap(True)
        self.password_help_label.setProperty("muted", True)

        for widget in (
            self.api_id_input,
            self.api_hash_input,
            self.phone_input,
        ):
            widget.textChanged.connect(self._reset_authorization_state)
        for widget in (self.code_input, self.password_input):
            widget.textChanged.connect(self._handle_auth_value_change)

    def _reset_authorization_state(self, *_args) -> None:
        wizard = self.wizard()
        self.authorized = False
        self.code_requested = False
        self.status_label.clear()
        self.send_code_button.setText("Send Code")
        self.send_code_button.setEnabled(True)
        if wizard is not None:
            wizard.telegram_service = None
            wizard.chat_page.reset_for_telegram_reauth()
            wizard.raidar_page.reset_for_telegram_reauth()
        self.completeChanged.emit()

    def _handle_auth_value_change(self, *_args) -> None:
        self.authorized = False
        if self.status_label.text() == "Authorized":
            self.status_label.clear()
        self.completeChanged.emit()

    def _handle_send_code(self) -> None:
        phone_number = self.phone_input.text().strip()
        if not phone_number:
            self.status_label.setText("Phone is required.")
            return
        self.send_code_button.setText("Sending...")
        self.send_code_button.setEnabled(False)
        QApplication.processEvents()
        wizard = self.wizard()
        try:
            service = wizard.build_telegram_service()
            status = asyncio.run(service.request_code(phone_number))
        except ValueError as exc:
            self.status_label.setText(str(exc))
            self.send_code_button.setText("Send Code")
            self.send_code_button.setEnabled(True)
            return
        except Exception as exc:
            self.status_label.setText(str(exc))
            self.send_code_button.setText("Send Code")
            self.send_code_button.setEnabled(True)
            return
        if status is SessionStatus.authorized:
            self.authorized = True
            self.code_requested = False
            self.status_label.setText("Authorized")
            self.send_code_button.setText("Authorized")
            self.send_code_button.setEnabled(False)
            return
        self.code_requested = True
        self.status_label.setText("Telegram code sent.")
        self.send_code_button.setText("Code Sent")
        self.send_code_button.setEnabled(True)

    def isComplete(self) -> bool:
        return bool(
            self.api_id_input.text().strip() and self.api_hash_input.text().strip()
        )

    def validatePage(self) -> bool:
        if self.authorized:
            return True

        wizard = self.wizard()
        try:
            service = wizard.build_telegram_service()
        except ValueError as exc:
            self.status_label.setText(str(exc))
            return False
        except Exception as exc:
            self.status_label.setText(str(exc))
            return False

        try:
            session_status = asyncio.run(service.get_session_status())
        except Exception as exc:
            self.status_label.setText(str(exc))
            return False
        if session_status is not SessionStatus.authorized and not self.code_requested:
            self.status_label.setText("Press Send Code first.")
            return False

        async def phone_callback() -> str:
            return self.phone_input.text().strip()

        async def code_callback() -> str:
            return self.code_input.text().strip()

        async def password_callback() -> str:
            return self.password_input.text().strip()

        try:
            asyncio.run(
                service.authorize(
                    phone_number_callback=phone_callback,
                    code_callback=code_callback,
                    password_callback=password_callback,
                )
            )
        except ValueError as exc:
            self.status_label.setText(str(exc))
            return False
        except Exception as exc:
            self.status_label.setText(str(exc))
            return False

        self.authorized = True
        self.code_requested = False
        self.status_label.setText("Authorized")
        return True


class ChatDiscoveryPage(QWizardPage):
    def __init__(self) -> None:
        super().__init__()
        self._loaded = False
        self.search_input = QLineEdit()
        self.chat_list = QListWidget()
        self.helper_label = QLabel(
            f"Select the chats {APP_NAME} is allowed to monitor. Use search to narrow the list once discovery completes."
        )
        self.empty_label = QLabel(
            "No chats are loaded yet. Authorize Telegram first, then return here to discover accessible chats."
        )
        self.status_label = QLabel("")
        self.chat_list.itemChanged.connect(lambda _item: self.completeChanged.emit())
        self.search_input.textChanged.connect(self._apply_filter)

        _root, self.surface = _create_page_shell(
            self,
            title="Whitelisted Chats",
            subtitle="Load the Telegram chats available to this session and choose which ones are eligible for raid detection.",
        )
        layout = _create_surface_layout(self.surface)
        self.helper_label.setWordWrap(True)
        self.helper_label.setProperty("muted", True)
        self.empty_label.setWordWrap(True)
        self.empty_label.setProperty("muted", True)
        self.search_input.setPlaceholderText("Search chats")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.helper_label)
        layout.addWidget(self.search_input)
        layout.addWidget(self.empty_label)
        layout.addWidget(self.chat_list)
        layout.addWidget(self.status_label)

    def initializePage(self) -> None:
        if self._loaded:
            return
        wizard = self.wizard()
        if wizard.telegram_service is None:
            self.status_label.setText("Authorize Telegram to load chats.")
            return
        self.status_label.setText("Loading available chats...")
        try:
            chats = asyncio.run(wizard.telegram_service.list_accessible_chats())
        except Exception as exc:
            self.status_label.setText(f"Unable to load chats for review. Details: {exc}")
            return
        self.set_chats(chats)
        self._loaded = True

    def set_chats(self, chats) -> None:
        self.chat_list.clear()
        for chat in chats:
            item = QListWidgetItem(chat.title)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            item.setData(Qt.ItemDataRole.UserRole, chat.chat_id)
            self.chat_list.addItem(item)
        self.empty_label.setVisible(not chats)
        if chats:
            self.status_label.setText("")
        else:
            self.status_label.setText("No accessible chats were found for this Telegram session.")
        self.completeChanged.emit()

    def selected_chat_ids(self) -> list[int]:
        chat_ids = []
        for index in range(self.chat_list.count()):
            item = self.chat_list.item(index)
            if item.checkState() == Qt.CheckState.Checked:
                chat_ids.append(int(item.data(Qt.ItemDataRole.UserRole)))
        return chat_ids

    def reset_for_telegram_reauth(self) -> None:
        self._loaded = False
        self.search_input.clear()
        self.chat_list.clear()
        self.empty_label.setVisible(True)
        self.status_label.setText(
            "No chats are loaded yet. Authorize Telegram first, then return here to discover accessible chats."
        )
        self.completeChanged.emit()

    def isComplete(self) -> bool:
        return bool(self.selected_chat_ids())

    def _apply_filter(self, text: str) -> None:
        needle = text.strip().lower()
        for index in range(self.chat_list.count()):
            item = self.chat_list.item(index)
            item.setHidden(bool(needle) and needle not in item.text().lower())


class RaidarSelectionPage(QWizardPage):
    def __init__(self) -> None:
        super().__init__()
        self._loaded = False
        self._default_help_text = (
            "Confirm one or more detected senders when possible. "
            "If discovery misses an edge case, add sender IDs manually."
        )
        self.candidate_list = QListWidget()
        self.manual_sender_ids_input = QLineEdit()
        self.confirm_checkbox = QCheckBox("I confirm the selected Allowed raid sender IDs")
        self.help_label = QLabel("")
        self.status_label = QLabel("")

        _root, self.surface = _create_page_shell(
            self,
            title="Allowed Raid Senders",
            subtitle="Review the supported raid bot candidates inferred from recent chat history and confirm the senders that should be allowed.",
        )
        surface_layout = _create_surface_layout(self.surface)
        self.helper_label = QLabel(self._default_help_text)
        self.helper_label.setWordWrap(True)
        self.helper_label.setProperty("muted", True)
        surface_layout.addWidget(self.helper_label)

        layout = QFormLayout()
        self.candidate_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.manual_sender_ids_input.setPlaceholderText("Example: 12345, 67890")
        layout.addRow("Detected candidates", self.candidate_list)
        layout.addRow("Manual sender IDs", self.manual_sender_ids_input)
        layout.addRow(self.confirm_checkbox)
        layout.addRow(self.help_label)
        layout.addRow(self.status_label)
        surface_layout.addLayout(layout)
        self.help_label.setWordWrap(True)
        self.status_label.setWordWrap(True)

        self.candidate_list.itemChanged.connect(lambda _item: self.completeChanged.emit())
        self.manual_sender_ids_input.textChanged.connect(
            lambda _text: self.completeChanged.emit()
        )
        self.confirm_checkbox.toggled.connect(lambda _checked: self.completeChanged.emit())

    def initializePage(self) -> None:
        if self._loaded:
            return
        wizard = self.wizard()
        if wizard.telegram_service is None:
            self.status_label.setText("Authorize Telegram and choose at least one chat before inferring allowed raid senders.")
            return
        self.status_label.setText("Loading recent sender candidates...")
        try:
            candidates = asyncio.run(
                wizard.telegram_service.infer_recent_sender_candidates(
                    wizard.chat_page.selected_chat_ids()
                )
            )
        except Exception as exc:
            self.status_label.setText(f"Unable to infer supported raid sender candidates. Details: {exc}")
            return
        self.set_candidates(candidates)
        self._loaded = True

    def set_candidates(self, candidates) -> None:
        self.candidate_list.clear()
        preselected_supported_matches = 0
        for candidate in candidates:
            item = QListWidgetItem(candidate.label)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            item.setData(Qt.ItemDataRole.UserRole, candidate.entity_id)
            if _is_supported_raid_candidate_label(candidate.label):
                item.setCheckState(Qt.CheckState.Checked)
                preselected_supported_matches += 1
            self.candidate_list.addItem(item)
        self.status_label.setText("")
        if preselected_supported_matches == 1 and len(candidates) == 1:
            self.help_label.setText("One detected sender was preselected. Confirmation is still required.")
        elif preselected_supported_matches >= 1:
            self.help_label.setText("Supported raid bot senders were preselected. Confirm any additional allowed senders if needed.")
        elif len(candidates) > 1:
            self.help_label.setText("Multiple sender candidates were found. Confirm any that should be allowed.")
        else:
            self.help_label.setText("No exact supported bot match found. Use the manual sender ID fallback.")
        self.completeChanged.emit()

    def reset_for_telegram_reauth(self) -> None:
        self._clear_selection_state()

    def reset_for_chat_selection_change(self) -> None:
        self._clear_selection_state()

    def _clear_selection_state(self) -> None:
        self._loaded = False
        self.candidate_list.clear()
        self.manual_sender_ids_input.clear()
        self.confirm_checkbox.setChecked(False)
        self.help_label.setText(self._default_help_text)
        self.status_label.clear()
        self.completeChanged.emit()

    def selected_sender_ids(self) -> list[int]:
        selected_sender_ids = []
        for index in range(self.candidate_list.count()):
            item = self.candidate_list.item(index)
            if item.checkState() == Qt.CheckState.Checked:
                selected_sender_ids.append(
                    _parse_int_field(str(item.data(Qt.ItemDataRole.UserRole)), field_name="Allowed sender IDs")
                )
        manual_sender_ids = _parse_int_list_field(
            self.manual_sender_ids_input.text(),
            field_name="Allowed sender IDs",
        )
        ordered_sender_ids: list[int] = []
        for sender_id in [*selected_sender_ids, *manual_sender_ids]:
            if sender_id not in ordered_sender_ids:
                ordered_sender_ids.append(sender_id)
        return ordered_sender_ids

    def selected_sender_entries(self) -> list[str]:
        selected_entries: list[str] = []
        for index in range(self.candidate_list.count()):
            item = self.candidate_list.item(index)
            if item.checkState() == Qt.CheckState.Checked:
                entry = item.text().strip()
                if entry and entry not in selected_entries:
                    selected_entries.append(entry)
        manual_sender_ids = _parse_int_list_field(
            self.manual_sender_ids_input.text(),
            field_name="Allowed sender IDs",
        )
        for sender_id in manual_sender_ids:
            entry = str(sender_id)
            if entry not in selected_entries:
                selected_entries.append(entry)
        return selected_entries

    def selected_sender_id(self) -> int | None:
        selected_sender_ids = self.selected_sender_ids()
        if not selected_sender_ids:
            return None
        return selected_sender_ids[0]

    def isComplete(self) -> bool:
        if not self.confirm_checkbox.isChecked():
            return False
        try:
            return bool(self.selected_sender_ids())
        except ValueError:
            return False


class ChromeProfilePage(QWizardPage):
    def __init__(self) -> None:
        super().__init__()
        self._loaded = False
        self.profile_combo = QComboBox()
        self.helper_label = QLabel(
            f"Choose the dedicated Chrome profile {APP_NAME} should use for raids. That profile must already be logged into X."
        )
        self.status_label = QLabel("")
        self.profile_combo.currentIndexChanged.connect(
            lambda _index: self.completeChanged.emit()
        )

        _root, self.surface = _create_page_shell(
            self,
            title="Raid Browser Profile",
            subtitle="Pick the dedicated local Chrome profile the bot will reuse when it opens raid tabs.",
        )
        surface_layout = _create_surface_layout(self.surface)
        self.helper_label.setWordWrap(True)
        self.helper_label.setProperty("muted", True)
        surface_layout.addWidget(self.helper_label)

        layout = QFormLayout()
        layout.addRow("Profile", self.profile_combo)
        layout.addRow(self.status_label)
        surface_layout.addLayout(layout)
        self.status_label.setWordWrap(True)

    def initializePage(self) -> None:
        if self._loaded:
            return
        self.status_label.setText("Detecting Chrome profiles...")
        try:
            environment = self.wizard().ensure_chrome_environment()
        except Exception as exc:
            self.status_label.setText(f"Unable to detect Chrome profiles. Details: {exc}")
            return
        self.set_profiles(environment.profiles)
        self._loaded = True

    def set_profiles(self, profiles: list[ChromeProfile]) -> None:
        self.profile_combo.clear()
        for profile in profiles:
            self.profile_combo.addItem(profile.label, profile.directory_name)
        if profiles:
            self.status_label.setText("")
        else:
            self.status_label.setText("No Chrome profiles were detected on this machine.")
        self.completeChanged.emit()

    def selected_profile_directory(self) -> str:
        return str(self.profile_combo.currentData())

    def isComplete(self) -> bool:
        return self.profile_combo.currentData() is not None


class ReviewPage(QWizardPage):
    def __init__(self) -> None:
        super().__init__()
        self.helper_label = QLabel("Review your setup before saving.")
        self.empty_label = QLabel("Review details will appear once the setup data is ready.")
        self.status_label = QLabel("Waiting for setup details...")
        self.summary = QTextEdit()
        self.summary.setReadOnly(True)
        self.start_now_checkbox = QCheckBox("Start bot now")

        _root, self.surface = _create_page_shell(
            self,
            title="Review and Save",
            subtitle="Confirm the final setup details before the configuration is written to disk.",
        )
        layout = _create_surface_layout(self.surface)
        self.helper_label.setWordWrap(True)
        self.helper_label.setProperty("muted", True)
        self.empty_label.setWordWrap(True)
        self.empty_label.setProperty("muted", True)
        self.status_label.setWordWrap(True)
        layout.addWidget(self.helper_label)
        layout.addWidget(self.empty_label)
        layout.addWidget(self.status_label)

        summary_surface = QFrame()
        summary_surface.setObjectName("wizardSummarySurface")
        summary_layout = QVBoxLayout(summary_surface)
        summary_layout.setContentsMargins(0, 0, 0, 0)
        summary_layout.addWidget(self.summary)
        layout.addWidget(summary_surface)
        layout.addWidget(self.start_now_checkbox)

    def initializePage(self) -> None:
        self.status_label.setText("Preparing your setup summary...")
        try:
            config = self.wizard().build_config()
        except ValueError as exc:
            self.status_label.setText(str(exc))
            self.summary.clear()
            return
        self.summary.setPlainText(
            "\n".join(
                [
                    f"API ID: {config.telegram_api_id}",
                    f"Chats: {', '.join(str(chat_id) for chat_id in config.whitelisted_chat_ids)}",
                    f"Allowed senders: {', '.join(config.allowed_sender_entries)}",
                    f"Dedicated raid browser profile: {config.chrome_profile_directory}",
                ]
            )
        )
        self.empty_label.setText("Review details will appear once the setup data is ready.")
        self.status_label.setText("Setup summary ready for final review.")

    def validatePage(self) -> bool:
        wizard = self.wizard()
        try:
            config = wizard.build_config()
        except ValueError as exc:
            self.status_label.setText(str(exc))
            return False
        wizard.storage.save_config(config)
        wizard.start_now_requested = self.start_now_checkbox.isChecked()
        return True
