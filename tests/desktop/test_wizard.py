from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt

from raidbot.desktop.chrome_profiles import ChromeEnvironment, ChromeProfile
from raidbot.desktop.models import DesktopAppConfig
from raidbot.desktop.telegram_setup import AccessibleChat, RaidarCandidate, SessionStatus


class FakeStorage:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.saved_configs: list[DesktopAppConfig] = []

    def save_config(self, config: DesktopAppConfig) -> None:
        self.saved_configs.append(config)


class FakeTelegramSetupService:
    def __init__(
        self,
        *,
        chats: list[AccessibleChat] | None = None,
        candidates: list[RaidarCandidate] | None = None,
        candidate_map: dict[tuple[int, ...], list[RaidarCandidate]] | None = None,
        authorize_error: Exception | None = None,
        chat_error: Exception | None = None,
        candidate_error: Exception | None = None,
        existing_session: bool = False,
        parent_exists: bool = True,
    ) -> None:
        self.chats = chats or []
        self.candidates = candidates or []
        self.authorize_error = authorize_error
        self.chat_error = chat_error
        self.candidate_error = candidate_error
        self.existing_session = existing_session
        self.parent_exists = parent_exists
        self.candidate_map = candidate_map or {}
        self.phone_calls = 0
        self.code_calls = 0
        self.password_calls = 0
        self.candidate_requests: list[tuple[int, ...]] = []

    async def authorize(
        self,
        *,
        phone_number_callback,
        code_callback,
        password_callback=None,
    ) -> SessionStatus:
        if not self.parent_exists:
            raise RuntimeError("session parent missing")
        if self.authorize_error is not None:
            raise self.authorize_error
        if self.existing_session:
            return SessionStatus.authorized
        self.phone_calls += 1
        await phone_number_callback()
        self.code_calls += 1
        await code_callback()
        if password_callback is not None:
            self.password_calls += 1
            await password_callback()
        return SessionStatus.authorized

    async def list_accessible_chats(self) -> list[AccessibleChat]:
        if self.chat_error is not None:
            raise self.chat_error
        return self.chats

    async def infer_recent_sender_candidates(self, chat_ids) -> list[RaidarCandidate]:
        if self.candidate_error is not None:
            raise self.candidate_error
        requested_chat_ids = tuple(chat_ids)
        self.candidate_requests.append(requested_chat_ids)
        if requested_chat_ids in self.candidate_map:
            return self.candidate_map[requested_chat_ids]
        return self.candidates


def build_chrome_environment() -> ChromeEnvironment:
    return ChromeEnvironment(
        chrome_path=Path(r"C:\Chrome\chrome.exe"),
        user_data_dir=Path(r"C:\Chrome\User Data"),
        profiles=[
            ChromeProfile(directory_name="Default", label="Main"),
            ChromeProfile(directory_name="Profile 3", label="Raid"),
        ],
    )


def test_chat_selection_page_filters_search_results(qtbot, tmp_path: Path) -> None:
    from raidbot.desktop.wizard import SetupWizard

    wizard = SetupWizard(
        storage=FakeStorage(tmp_path),
        telegram_service_factory=lambda *_args: FakeTelegramSetupService(
            chats=[
                AccessibleChat(chat_id=1, title="Alpha Room"),
                AccessibleChat(chat_id=2, title="Beta Base"),
            ]
        ),
        chrome_environment=build_chrome_environment(),
    )
    qtbot.addWidget(wizard)

    wizard.chat_page.set_chats(
        [
            AccessibleChat(chat_id=1, title="Alpha Room"),
            AccessibleChat(chat_id=2, title="Beta Base"),
        ]
    )
    wizard.chat_page.search_input.setText("beta")

    assert wizard.chat_page.chat_list.item(0).isHidden() is True
    assert wizard.chat_page.chat_list.item(1).isHidden() is False


def test_welcome_page_contains_structured_intro_content(qtbot, tmp_path: Path) -> None:
    from raidbot.desktop.wizard import SetupWizard

    wizard = SetupWizard(
        storage=FakeStorage(tmp_path),
        telegram_service_factory=lambda *_args: None,
        chrome_environment=build_chrome_environment(),
    )
    qtbot.addWidget(wizard)

    assert "Telegram access" in wizard.welcome_page.description_label.text()
    assert "Chrome profile" in wizard.welcome_page.description_label.text()
    assert "already be logged into X" in wizard.welcome_page.note_label.text()
    assert wizard.welcome_page.checklist_label.text()


def test_wizard_buttons_have_visual_variants(qtbot, tmp_path: Path) -> None:
    from raidbot.desktop.wizard import SetupWizard

    wizard = SetupWizard(
        storage=FakeStorage(tmp_path),
        telegram_service_factory=lambda *_args: None,
        chrome_environment=build_chrome_environment(),
    )
    qtbot.addWidget(wizard)
    wizard.show()

    assert wizard.button(wizard.NextButton).property("variant") == "primary"
    assert wizard.button(wizard.CancelButton).property("variant") == "quiet"


def test_telegram_page_uses_named_surface_container(qtbot, tmp_path: Path) -> None:
    from raidbot.desktop.wizard import SetupWizard

    wizard = SetupWizard(
        storage=FakeStorage(tmp_path),
        telegram_service_factory=lambda *_args: None,
        chrome_environment=build_chrome_environment(),
    )
    qtbot.addWidget(wizard)

    assert wizard.telegram_page.surface.objectName() == "wizardSurface"


def test_chat_and_review_pages_expose_guidance_copy(qtbot, tmp_path: Path) -> None:
    from raidbot.desktop.wizard import SetupWizard

    wizard = SetupWizard(
        storage=FakeStorage(tmp_path),
        telegram_service_factory=lambda *_args: None,
        chrome_environment=build_chrome_environment(),
    )
    qtbot.addWidget(wizard)

    assert "Select the chats" in wizard.chat_page.helper_label.text()
    wizard.telegram_page.api_id_input.setText("123456")
    wizard.telegram_page.api_hash_input.setText("hash-value")
    wizard.telegram_page.phone_input.setText("+40123456789")
    wizard.chat_page.set_chats([AccessibleChat(chat_id=1, title="Alpha Room")])
    wizard.chat_page.chat_list.item(0).setCheckState(Qt.CheckState.Checked)
    wizard.raidar_page.set_candidates([RaidarCandidate(entity_id=10, label="@raidar")])
    wizard.raidar_page.candidate_list.item(0).setCheckState(Qt.CheckState.Checked)
    wizard.raidar_page.confirm_checkbox.setChecked(True)
    wizard.chrome_page.set_profiles(build_chrome_environment().profiles)
    wizard.chrome_page.profile_combo.setCurrentIndex(1)
    wizard.review_page.initializePage()

    assert "Review your setup" in wizard.review_page.helper_label.text()
    assert "Review details will appear once the setup data is ready." in wizard.review_page.empty_label.text()
    assert "Setup summary ready for final review." in wizard.review_page.status_label.text()
    assert "Allowed sender IDs: 10" in wizard.review_page.summary.toPlainText()
    assert "Dedicated raid browser profile: Profile 3" in wizard.review_page.summary.toPlainText()


def test_telegram_page_allows_existing_session_without_phone_or_code(qtbot, tmp_path: Path) -> None:
    from raidbot.desktop.wizard import SetupWizard

    service = FakeTelegramSetupService(existing_session=True)
    wizard = SetupWizard(
        storage=FakeStorage(tmp_path),
        telegram_service_factory=lambda *_args: service,
        chrome_environment=build_chrome_environment(),
    )
    qtbot.addWidget(wizard)

    wizard.telegram_page.api_id_input.setText("123456")
    wizard.telegram_page.api_hash_input.setText("hash-value")

    assert wizard.telegram_page.isComplete() is True
    assert wizard.telegram_page.validatePage() is True
    assert service.phone_calls == 0
    assert service.code_calls == 0


def test_telegram_page_invalidates_authorized_state_when_auth_inputs_change(
    qtbot,
    tmp_path: Path,
) -> None:
    from raidbot.desktop.wizard import SetupWizard

    wizard = SetupWizard(
        storage=FakeStorage(tmp_path),
        telegram_service_factory=lambda *_args: FakeTelegramSetupService(),
        chrome_environment=build_chrome_environment(),
    )
    qtbot.addWidget(wizard)

    wizard.telegram_page.api_id_input.setText("123456")
    wizard.telegram_page.api_hash_input.setText("hash-value")
    wizard.telegram_page.authorized = True

    wizard.telegram_page.api_id_input.setText("not-a-number")

    assert wizard.telegram_page.authorized is False
    assert wizard.telegram_page.validatePage() is False
    assert wizard.telegram_page.status_label.text() == "Telegram API ID must be a valid integer."


def test_telegram_page_change_clears_cached_service_and_downstream_state(
    qtbot,
    tmp_path: Path,
) -> None:
    from raidbot.desktop.wizard import SetupWizard

    service = FakeTelegramSetupService(
        chats=[AccessibleChat(chat_id=1, title="Alpha Room")],
        candidates=[RaidarCandidate(entity_id=10, label="@raidar")],
    )
    wizard = SetupWizard(
        storage=FakeStorage(tmp_path),
        telegram_service_factory=lambda *_args: service,
        chrome_environment=build_chrome_environment(),
    )
    qtbot.addWidget(wizard)

    wizard.telegram_page.api_id_input.setText("123456")
    wizard.telegram_page.api_hash_input.setText("hash-value")
    wizard.telegram_page.authorized = True
    wizard.telegram_service = service
    wizard.chat_page.set_chats([AccessibleChat(chat_id=1, title="Alpha Room")])
    wizard.chat_page.chat_list.item(0).setCheckState(Qt.CheckState.Checked)
    wizard.chat_page._loaded = True
    wizard.raidar_page.set_candidates([RaidarCandidate(entity_id=10, label="@raidar")])
    wizard.raidar_page.candidate_list.item(0).setCheckState(Qt.CheckState.Checked)
    wizard.raidar_page.confirm_checkbox.setChecked(True)
    wizard.raidar_page.manual_sender_ids_input.setText("77, 88")
    wizard.raidar_page._loaded = True

    wizard.telegram_page.phone_input.setText("+40123456789")

    assert wizard.telegram_page.authorized is False
    assert wizard.telegram_service is None
    assert wizard.chat_page._loaded is False
    assert wizard.chat_page.chat_list.count() == 0
    assert wizard.chat_page.status_label.text() == "No chats are loaded yet. Authorize Telegram first, then return here to discover accessible chats."
    assert wizard.raidar_page._loaded is False
    assert wizard.raidar_page.candidate_list.count() == 0
    assert wizard.raidar_page.manual_sender_ids_input.text() == ""
    assert wizard.raidar_page.confirm_checkbox.isChecked() is False
    assert wizard.raidar_page.status_label.text() == ""


def test_chat_selection_change_invalidates_cached_raidar_selection_and_recomputes(
    qtbot,
    tmp_path: Path,
) -> None:
    from raidbot.desktop.wizard import SetupWizard

    service = FakeTelegramSetupService(
        chats=[
            AccessibleChat(chat_id=1, title="Alpha Room"),
            AccessibleChat(chat_id=2, title="Beta Base"),
        ],
        candidate_map={
            (1,): [RaidarCandidate(entity_id=10, label="@alpha")],
            (2,): [RaidarCandidate(entity_id=20, label="@beta")],
        },
    )
    wizard = SetupWizard(
        storage=FakeStorage(tmp_path),
        telegram_service_factory=lambda *_args: service,
        chrome_environment=build_chrome_environment(),
    )
    qtbot.addWidget(wizard)

    wizard.telegram_service = service
    wizard.chat_page.set_chats(service.chats)
    wizard.chat_page.chat_list.item(0).setCheckState(Qt.CheckState.Checked)
    wizard.raidar_page.initializePage()
    wizard.raidar_page.candidate_list.item(0).setCheckState(Qt.CheckState.Checked)
    wizard.raidar_page.manual_sender_ids_input.setText("77")
    wizard.raidar_page.confirm_checkbox.setChecked(True)

    wizard.chat_page.chat_list.item(0).setCheckState(Qt.CheckState.Unchecked)
    wizard.chat_page.chat_list.item(1).setCheckState(Qt.CheckState.Checked)

    assert wizard.raidar_page._loaded is False
    assert wizard.raidar_page.candidate_list.count() == 0
    assert wizard.raidar_page.manual_sender_ids_input.text() == ""
    assert wizard.raidar_page.confirm_checkbox.isChecked() is False

    wizard.raidar_page.initializePage()

    assert service.candidate_requests == [(1,), (2,)]
    assert wizard.raidar_page.candidate_list.count() == 1
    assert wizard.raidar_page.candidate_list.item(0).text() == "@beta"


def test_telegram_page_creates_session_directory_before_authorize(qtbot, tmp_path: Path) -> None:
    from raidbot.desktop.wizard import SetupWizard

    captured = {}

    def factory(_api_id, _api_hash, session_path):
        captured["session_path"] = session_path
        return FakeTelegramSetupService(parent_exists=session_path.parent.exists())

    wizard = SetupWizard(
        storage=FakeStorage(tmp_path),
        telegram_service_factory=factory,
        chrome_environment=build_chrome_environment(),
    )
    qtbot.addWidget(wizard)

    wizard.telegram_page.api_id_input.setText("123456")
    wizard.telegram_page.api_hash_input.setText("hash-value")
    wizard.telegram_page.phone_input.setText("+40123456789")
    wizard.telegram_page.code_input.setText("12345")

    assert wizard.telegram_page.validatePage() is True
    assert captured["session_path"].parent.exists() is True


def test_telegram_page_rejects_invalid_api_id_without_crashing(qtbot, tmp_path: Path) -> None:
    from raidbot.desktop.wizard import SetupWizard

    wizard = SetupWizard(
        storage=FakeStorage(tmp_path),
        telegram_service_factory=lambda *_args: FakeTelegramSetupService(),
        chrome_environment=build_chrome_environment(),
    )
    qtbot.addWidget(wizard)

    wizard.telegram_page.api_id_input.setText("not-a-number")
    wizard.telegram_page.api_hash_input.setText("hash-value")

    assert wizard.telegram_page.validatePage() is False
    assert wizard.telegram_page.status_label.text() == "Telegram API ID must be a valid integer."


def test_review_page_rejects_invalid_numeric_fields_without_crashing(
    qtbot,
    tmp_path: Path,
) -> None:
    from raidbot.desktop.wizard import SetupWizard

    storage = FakeStorage(tmp_path)
    wizard = SetupWizard(
        storage=storage,
        telegram_service_factory=lambda *_args: FakeTelegramSetupService(),
        chrome_environment=build_chrome_environment(),
    )
    qtbot.addWidget(wizard)

    wizard.telegram_page.api_id_input.setText("123456")
    wizard.telegram_page.api_hash_input.setText("hash-value")
    wizard.telegram_page.authorized = True
    wizard.chat_page.set_chats([AccessibleChat(chat_id=1, title="Alpha Room")])
    wizard.chat_page.chat_list.item(0).setCheckState(Qt.CheckState.Checked)
    wizard.raidar_page.manual_sender_ids_input.setText("bad-sender")
    wizard.raidar_page.confirm_checkbox.setChecked(True)
    wizard.chrome_page.set_profiles(build_chrome_environment().profiles)
    wizard.chrome_page.profile_combo.setCurrentIndex(1)
    wizard.review_page.initializePage()

    assert wizard.review_page.validatePage() is False
    assert storage.saved_configs == []
    assert wizard.review_page.status_label.text() == "Allowed sender IDs must be valid integers."


def test_raidar_page_requires_confirmation_and_supports_multiple_selected_senders(
    qtbot,
    tmp_path: Path,
) -> None:
    from raidbot.desktop.wizard import SetupWizard

    wizard = SetupWizard(
        storage=FakeStorage(tmp_path),
        telegram_service_factory=lambda *_args: FakeTelegramSetupService(
            candidates=[
                RaidarCandidate(entity_id=10, label="@raidar"),
                RaidarCandidate(entity_id=20, label="@raidar_alt"),
            ]
        ),
        chrome_environment=build_chrome_environment(),
    )
    qtbot.addWidget(wizard)

    wizard.raidar_page.set_candidates(
        [
            RaidarCandidate(entity_id=10, label="@raidar"),
            RaidarCandidate(entity_id=20, label="@raidar_alt"),
        ]
    )

    assert wizard.raidar_page.isComplete() is False

    wizard.raidar_page.candidate_list.item(0).setCheckState(Qt.CheckState.Checked)
    wizard.raidar_page.candidate_list.item(1).setCheckState(Qt.CheckState.Checked)
    wizard.raidar_page.manual_sender_ids_input.setText("77")
    wizard.raidar_page.confirm_checkbox.setChecked(True)

    assert wizard.raidar_page.isComplete() is True
    assert wizard.raidar_page.selected_sender_ids() == [10, 20, 77]


def test_chat_raidar_and_chrome_page_loading_errors_stay_visible_and_retryable(
    qtbot,
    tmp_path: Path,
) -> None:
    from raidbot.desktop.wizard import SetupWizard

    service = FakeTelegramSetupService(
        chat_error=RuntimeError("chat boom"),
        candidate_error=RuntimeError("raidar boom"),
    )
    wizard = SetupWizard(
        storage=FakeStorage(tmp_path),
        telegram_service_factory=lambda *_args: service,
        chrome_environment_factory=lambda: (_ for _ in ()).throw(RuntimeError("chrome boom")),
    )
    qtbot.addWidget(wizard)
    wizard.telegram_service = service
    wizard.chat_page.initializePage()
    wizard.raidar_page.initializePage()
    wizard.chrome_page.initializePage()

    assert wizard.chat_page.status_label.text() == "Unable to load chats for review. Details: chat boom"
    assert wizard.raidar_page.status_label.text() == "Unable to infer Raidar candidates. Details: raidar boom"
    assert wizard.chrome_page.status_label.text() == "Unable to detect Chrome profiles. Details: chrome boom"

    service.chat_error = None
    service.candidate_error = None
    service.chats = [AccessibleChat(chat_id=1, title="Alpha Room")]
    service.candidates = [RaidarCandidate(entity_id=10, label="@raidar")]
    wizard.chrome_environment_factory = build_chrome_environment
    wizard.chat_page.initializePage()
    wizard.chat_page.chat_list.item(0).setCheckState(Qt.CheckState.Checked)
    wizard.raidar_page.initializePage()
    wizard.chrome_page.initializePage()

    assert wizard.chat_page.status_label.text() == ""
    assert wizard.raidar_page.status_label.text() == ""
    assert wizard.chrome_page.status_label.text() == ""
    assert wizard.chrome_page.profile_combo.count() == 2


def test_review_page_saves_multi_sender_config_and_start_now_flag(qtbot, tmp_path: Path) -> None:
    from raidbot.desktop.wizard import SetupWizard

    storage = FakeStorage(tmp_path)
    wizard = SetupWizard(
        storage=storage,
        telegram_service_factory=lambda *_args: FakeTelegramSetupService(),
        chrome_environment=build_chrome_environment(),
    )
    qtbot.addWidget(wizard)

    wizard.telegram_page.api_id_input.setText("123456")
    wizard.telegram_page.api_hash_input.setText("hash-value")
    wizard.telegram_page.phone_input.setText("+40123456789")
    wizard.telegram_page.code_input.setText("12345")
    wizard.telegram_page.password_input.setText("")
    wizard.telegram_page.authorized = True
    wizard.chat_page.set_chats([AccessibleChat(chat_id=1, title="Alpha Room")])
    wizard.chat_page.chat_list.item(0).setCheckState(Qt.CheckState.Checked)
    wizard.raidar_page.set_candidates(
        [
            RaidarCandidate(entity_id=10, label="@raidar"),
            RaidarCandidate(entity_id=20, label="@delugeraidbot"),
        ]
    )
    wizard.raidar_page.candidate_list.item(0).setCheckState(Qt.CheckState.Checked)
    wizard.raidar_page.candidate_list.item(1).setCheckState(Qt.CheckState.Checked)
    wizard.raidar_page.manual_sender_ids_input.setText("77")
    wizard.raidar_page.confirm_checkbox.setChecked(True)
    wizard.chrome_page.set_profiles(build_chrome_environment().profiles)
    wizard.chrome_page.profile_combo.setCurrentIndex(1)
    wizard.review_page.start_now_checkbox.setChecked(True)
    wizard.review_page.initializePage()

    assert "Allowed sender IDs: 10, 20, 77" in wizard.review_page.summary.toPlainText()
    assert "Dedicated raid browser profile: Profile 3" in wizard.review_page.summary.toPlainText()
    assert wizard.review_page.validatePage() is True
    assert len(storage.saved_configs) == 1
    assert storage.saved_configs[0] == DesktopAppConfig(
        telegram_api_id=123456,
        telegram_api_hash="hash-value",
        telegram_session_path=tmp_path / "telegram" / "raidbot.session",
        telegram_phone_number="+40123456789",
        whitelisted_chat_ids=[1],
        allowed_sender_ids=[10, 20, 77],
        chrome_profile_directory="Profile 3",
    )
    assert wizard.start_now_requested is True
