from __future__ import annotations

from pathlib import Path

from raidbot.desktop.chrome_profiles import ChromeEnvironment, ChromeProfile
from raidbot.desktop.models import DesktopAppConfig
from raidbot.desktop.storage import DesktopStorage


def _write_shared_config(base_dir) -> None:
    DesktopStorage(base_dir).save_config(
        DesktopAppConfig(
            telegram_api_id=123456,
            telegram_api_hash="api-hash",
            telegram_session_path=Path("sessions/raid.session"),
            telegram_phone_number="+15555550123",
            whitelisted_chat_ids=[1001],
            allowed_sender_ids=[424242],
            allowed_sender_entries=("@raidar",),
            chrome_profile_directory="Default",
        )
    )


def _fake_chrome_environment(tmp_path) -> ChromeEnvironment:
    return ChromeEnvironment(
        chrome_path=tmp_path / "Chrome" / "chrome.exe",
        user_data_dir=tmp_path / "ChromeUserData",
        profiles=[
            ChromeProfile(directory_name="Default", label="Main"),
            ChromeProfile(directory_name="Profile 3", label="Raid"),
        ],
    )


def test_headless_app_defaults_profile_picker_to_desktop_profile(
    qtbot, tmp_path, monkeypatch
) -> None:
    from raidbot.headless.config import HeadlessConfigStore
    from raidbot.headless.models import HeadlessAuthState

    _write_shared_config(tmp_path)

    class FakeSessionManager:
        def __init__(self, **kwargs):
            self.auth_state = HeadlessAuthState(status="needs_login", detail="x_auth_required")

        def get_auth_state(self):
            return self.auth_state

    monkeypatch.setattr("raidbot.headless.app.PlaywrightSessionManager", FakeSessionManager)
    monkeypatch.setattr(
        "raidbot.headless.app.detect_chrome_environment",
        lambda: _fake_chrome_environment(tmp_path),
    )

    from raidbot.headless.app import HeadlessApp

    headless_app = HeadlessApp(config_store=HeadlessConfigStore(tmp_path))
    qtbot.addWidget(headless_app.window)

    assert headless_app.window.selected_profile_directory() == "Default"


def test_headless_app_imports_x_auth_from_selected_headless_profile(
    qtbot, tmp_path, monkeypatch
) -> None:
    from raidbot.headless.config import HeadlessConfigStore
    from raidbot.headless.models import HeadlessAuthState

    _write_shared_config(tmp_path)
    imported_profiles: list[str] = []

    class FakeSessionManager:
        def __init__(self, **kwargs):
            self.auth_state = HeadlessAuthState(status="needs_login", detail="x_auth_required")

        def get_auth_state(self):
            return self.auth_state

        def import_auth_from_desktop_profile(self, profile_directory: str):
            imported_profiles.append(profile_directory)
            self.auth_state = HeadlessAuthState(status="authenticated")
            return self.auth_state

    monkeypatch.setattr("raidbot.headless.app.PlaywrightSessionManager", FakeSessionManager)
    monkeypatch.setattr(
        "raidbot.headless.app.detect_chrome_environment",
        lambda: _fake_chrome_environment(tmp_path),
    )

    from raidbot.headless.app import HeadlessApp

    headless_app = HeadlessApp(config_store=HeadlessConfigStore(tmp_path))
    qtbot.addWidget(headless_app.window)
    headless_app.window.set_selected_profile_directory("Profile 3")

    headless_app._bootstrap_login()

    assert imported_profiles == ["Profile 3"]
    assert "X auth imported" in headless_app.window.log_output.toPlainText()
    assert "Authenticated" in headless_app.window.auth_status_label.text()


def test_headless_app_logs_import_x_auth_failure(qtbot, tmp_path, monkeypatch) -> None:
    from raidbot.headless.config import HeadlessConfigStore
    from raidbot.headless.models import HeadlessAuthState

    _write_shared_config(tmp_path)

    class FakeSessionManager:
        def __init__(self, **kwargs):
            self.auth_state = HeadlessAuthState(status="needs_login", detail="x_auth_required")

        def get_auth_state(self):
            return self.auth_state

        def import_auth_from_desktop_profile(self, profile_directory: str):
            raise RuntimeError(f"import_failed:{profile_directory}")

    monkeypatch.setattr("raidbot.headless.app.PlaywrightSessionManager", FakeSessionManager)
    monkeypatch.setattr(
        "raidbot.headless.app.detect_chrome_environment",
        lambda: _fake_chrome_environment(tmp_path),
    )

    from raidbot.headless.app import HeadlessApp

    headless_app = HeadlessApp(config_store=HeadlessConfigStore(tmp_path))
    qtbot.addWidget(headless_app.window)

    headless_app._bootstrap_login()

    assert "import_failed:Default" in headless_app.window.log_output.toPlainText()


def test_headless_app_persists_selected_profile_override(qtbot, tmp_path, monkeypatch) -> None:
    from raidbot.headless.config import HeadlessConfigStore
    from raidbot.headless.models import HeadlessAuthState

    _write_shared_config(tmp_path)

    class FakeSessionManager:
        def __init__(self, **kwargs):
            self.auth_state = HeadlessAuthState(status="needs_login", detail="x_auth_required")

        def get_auth_state(self):
            return self.auth_state

    monkeypatch.setattr("raidbot.headless.app.PlaywrightSessionManager", FakeSessionManager)
    monkeypatch.setattr(
        "raidbot.headless.app.detect_chrome_environment",
        lambda: _fake_chrome_environment(tmp_path),
    )

    from raidbot.headless.app import HeadlessApp

    store = HeadlessConfigStore(tmp_path)
    headless_app = HeadlessApp(config_store=store)
    qtbot.addWidget(headless_app.window)

    headless_app.window.set_selected_profile_directory("Profile 3")
    headless_app._save_selected_profile_directory("Profile 3")

    assert store.load_settings().chrome_profile_directory == "Profile 3"
