from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt

from raidbot.desktop.models import DesktopAppConfig


def build_config(**overrides) -> DesktopAppConfig:
    values = {
        "telegram_api_id": 123456,
        "telegram_api_hash": "hash-value",
        "telegram_session_path": Path("raidbot.session"),
        "telegram_phone_number": "+40123456789",
        "whitelisted_chat_ids": [-1001],
        "allowed_sender_ids": [42],
        "chrome_profile_directory": "Profile 3",
        "browser_mode": "launch-only",
        "executor_name": "noop",
        "preset_replies": ("gm",),
        "default_action_like": True,
        "default_action_repost": True,
        "default_action_bookmark": False,
        "default_action_reply": True,
    }
    values.update(overrides)
    return DesktopAppConfig(**values)


def test_settings_save_emits_allowlist_and_preset_replies(qtbot) -> None:
    from raidbot.desktop.settings_page import SettingsPage

    page = SettingsPage(
        config=build_config(),
        available_profiles=["Default", "Profile 3", "Profile 9"],
        session_status="authorized",
    )
    qtbot.addWidget(page)

    applied = []
    page.applyRequested.connect(applied.append)

    page.api_hash_input.setText("new-hash")
    page.whitelist_input.setText("-1001, -2002")
    page.allowed_senders_input.setText("99, 101")
    page.reply_pool_input.setPlainText("gm\nlfggg")
    page.like_toggle.setChecked(False)
    page.repost_toggle.setChecked(False)
    page.bookmark_toggle.setChecked(True)
    page.reply_toggle.setChecked(False)
    page.profile_combo.setCurrentText("Profile 9")
    qtbot.mouseClick(page.save_button, Qt.MouseButton.LeftButton)

    assert applied == [
        build_config(
            telegram_api_hash="new-hash",
            whitelisted_chat_ids=[-1001, -2002],
            allowed_sender_ids=[99, 101],
            chrome_profile_directory="Profile 9",
            preset_replies=("gm", "lfggg"),
            default_action_like=False,
            default_action_repost=False,
            default_action_bookmark=True,
            default_action_reply=False,
        )
    ]


def test_settings_save_rejects_invalid_numeric_input_without_crashing(qtbot) -> None:
    from raidbot.desktop.settings_page import SettingsPage

    page = SettingsPage(
        config=build_config(),
        available_profiles=["Default", "Profile 3", "Profile 9"],
        session_status="authorized",
    )
    qtbot.addWidget(page)

    applied = []
    page.applyRequested.connect(applied.append)

    page.api_id_input.setText("not-a-number")
    page.whitelist_input.setText("-1001, -2002")
    page.allowed_senders_input.setText("99")
    qtbot.mouseClick(page.save_button, Qt.MouseButton.LeftButton)

    assert applied == []
    assert page.status_label.text() == "Telegram API ID must be a valid integer."


def test_settings_save_rejects_blank_telegram_api_hash(qtbot) -> None:
    from raidbot.desktop.settings_page import SettingsPage

    page = SettingsPage(
        config=build_config(),
        available_profiles=["Default", "Profile 3", "Profile 9"],
        session_status="authorized",
    )
    qtbot.addWidget(page)

    applied = []
    page.applyRequested.connect(applied.append)

    page.api_hash_input.setText("   ")
    page.whitelist_input.setText("-1001, -2002")
    page.allowed_senders_input.setText("99")
    qtbot.mouseClick(page.save_button, Qt.MouseButton.LeftButton)

    assert applied == []
    assert page.status_label.text() == "Telegram API Hash is required."


def test_settings_save_clears_previous_error_on_success(qtbot) -> None:
    from raidbot.desktop.settings_page import SettingsPage

    page = SettingsPage(
        config=build_config(),
        available_profiles=["Default", "Profile 3", "Profile 9"],
        session_status="authorized",
    )
    qtbot.addWidget(page)

    applied = []
    page.applyRequested.connect(applied.append)

    page.api_id_input.setText("not-a-number")
    qtbot.mouseClick(page.save_button, Qt.MouseButton.LeftButton)
    assert page.status_label.text() == "Telegram API ID must be a valid integer."

    page.api_id_input.setText("123456")
    page.whitelist_input.setText("-1001, -2002")
    page.allowed_senders_input.setText("99")
    qtbot.mouseClick(page.save_button, Qt.MouseButton.LeftButton)

    assert len(applied) == 1
    assert page.status_label.text() == ""


def test_settings_save_rejects_blank_sender_allowlist(qtbot) -> None:
    from raidbot.desktop.settings_page import SettingsPage

    page = SettingsPage(
        config=build_config(),
        available_profiles=["Default", "Profile 3", "Profile 9"],
        session_status="authorized",
    )
    qtbot.addWidget(page)

    applied = []
    page.applyRequested.connect(applied.append)

    page.api_id_input.setText("123456")
    page.api_hash_input.setText("new-hash")
    page.whitelist_input.setText("-1001, -2002")
    page.allowed_senders_input.setText("   ")
    qtbot.mouseClick(page.save_button, Qt.MouseButton.LeftButton)

    assert applied == []
    assert page.status_label.text() == "Allowed sender IDs is required."


def test_settings_save_rejects_missing_persisted_sender_allowlist(qtbot) -> None:
    from raidbot.desktop.settings_page import SettingsPage

    page = SettingsPage(
        config=build_config(allowed_sender_ids=[]),
        available_profiles=["Default", "Profile 3", "Profile 9"],
        session_status="authorized",
    )
    qtbot.addWidget(page)

    applied = []
    page.applyRequested.connect(applied.append)

    qtbot.mouseClick(page.save_button, Qt.MouseButton.LeftButton)

    assert applied == []
    assert page.status_label.text() == "Allowed sender IDs is required."


def test_settings_save_rejects_invalid_whitelist_without_crashing(qtbot) -> None:
    from raidbot.desktop.settings_page import SettingsPage

    page = SettingsPage(
        config=build_config(),
        available_profiles=["Default", "Profile 3", "Profile 9"],
        session_status="authorized",
    )
    qtbot.addWidget(page)

    applied = []
    page.applyRequested.connect(applied.append)

    page.api_id_input.setText("123456")
    page.whitelist_input.setText("-1001, nope")
    page.allowed_senders_input.setText("99")
    qtbot.mouseClick(page.save_button, Qt.MouseButton.LeftButton)

    assert applied == []
    assert page.status_label.text() == "Chat whitelist must contain valid integers."


def test_settings_save_rejects_invalid_sender_allowlist_without_crashing(qtbot) -> None:
    from raidbot.desktop.settings_page import SettingsPage

    page = SettingsPage(
        config=build_config(),
        available_profiles=["Default", "Profile 3", "Profile 9"],
        session_status="authorized",
    )
    qtbot.addWidget(page)

    applied = []
    page.applyRequested.connect(applied.append)

    page.api_id_input.setText("123456")
    page.whitelist_input.setText("-1001, -2002")
    page.allowed_senders_input.setText("42, oops")
    qtbot.mouseClick(page.save_button, Qt.MouseButton.LeftButton)

    assert applied == []
    assert page.status_label.text() == "Allowed sender IDs must contain valid integers."


def test_settings_page_marks_sender_allowlist_as_required(qtbot) -> None:
    from raidbot.desktop.settings_page import SettingsPage

    page = SettingsPage(
        config=build_config(),
        available_profiles=["Default", "Profile 3"],
        session_status="authorized",
    )
    qtbot.addWidget(page)

    assert page.allowed_senders_input.placeholderText() == "Comma-separated sender IDs"
    assert page.allowed_senders_hint_label.text() == "Required to start the bot."


def test_settings_page_exposes_session_status_and_reauthorize(qtbot) -> None:
    from raidbot.desktop.settings_page import SettingsPage

    page = SettingsPage(
        config=build_config(),
        available_profiles=["Default", "Profile 3"],
        session_status="authorized",
    )
    qtbot.addWidget(page)

    reauthorize_calls = []
    page.reauthorizeRequested.connect(lambda: reauthorize_calls.append("reauthorize"))

    assert page.session_status_label.text() == "authorized"
    qtbot.mouseClick(page.reauthorize_button, Qt.MouseButton.LeftButton)

    assert reauthorize_calls == ["reauthorize"]


def test_settings_page_disables_reauthorize_when_unavailable(qtbot) -> None:
    from raidbot.desktop.settings_page import SettingsPage

    page = SettingsPage(
        config=build_config(),
        available_profiles=["Default", "Profile 3"],
        session_status="authorized",
        reauthorize_available=False,
    )
    qtbot.addWidget(page)

    assert page.reauthorize_button.isEnabled() is False
    assert "delete the saved desktop config file" in page.reauthorize_hint_label.text().lower()
    assert "restart the app" in page.reauthorize_hint_label.text().lower()


def test_settings_page_can_refresh_session_status_and_profiles(qtbot) -> None:
    from raidbot.desktop.settings_page import SettingsPage

    page = SettingsPage(
        config=build_config(),
        available_profiles=["Profile 3"],
        session_status="unknown",
    )
    qtbot.addWidget(page)

    page.set_session_status("authorized")
    page.set_available_profiles(["Default", "Profile 3", "Profile 9"])

    assert page.session_status_label.text() == "authorized"
    assert [page.profile_combo.itemText(index) for index in range(page.profile_combo.count())] == [
        "Default",
        "Profile 3",
        "Profile 9",
    ]
    assert page.profile_combo.currentText() == "Profile 3"


def test_settings_page_uses_grouped_sections_and_primary_save(qtbot) -> None:
    from raidbot.desktop.settings_page import SettingsPage
    from raidbot.desktop.theme import SECTION_OBJECT_NAME

    page = SettingsPage(
        config=build_config(),
        available_profiles=["Default", "Profile 3"],
        session_status="authorized",
    )
    qtbot.addWidget(page)

    assert page.session_section.objectName() == "settingsSection"
    assert page.telegram_section.objectName() == "settingsSection"
    assert page.routing_section.objectName() == "settingsSection"
    assert page.session_surface.objectName() == SECTION_OBJECT_NAME
    assert page.telegram_surface.objectName() == SECTION_OBJECT_NAME
    assert page.routing_surface.objectName() == SECTION_OBJECT_NAME
    assert page.save_button.property("variant") == "primary"
    assert page.reauthorize_button.property("variant") == "secondary"


def test_settings_page_exposes_browser_pipeline_controls(qtbot) -> None:
    from raidbot.desktop.settings_page import SettingsPage

    page = SettingsPage(
        config=build_config(),
        available_profiles=["Default", "Profile 3"],
        session_status="authorized",
    )
    qtbot.addWidget(page)

    assert page.browser_mode_combo.currentText() == "launch-only"
    assert page.executor_name_label.text() == "noop"
    assert page.reply_pool_input.toPlainText() == "gm"
    assert page.like_toggle.isChecked() is True
    assert page.repost_toggle.isChecked() is True
    assert page.bookmark_toggle.isChecked() is False
    assert page.reply_toggle.isChecked() is True


def test_settings_page_preserves_apply_and_reauthorize_signals(qtbot) -> None:
    from raidbot.desktop.settings_page import SettingsPage

    apply_events = []
    reauthorize_events = []
    page = SettingsPage(
        config=build_config(),
        available_profiles=["Default", "Profile 3"],
        session_status="authorized",
    )
    qtbot.addWidget(page)
    page.applyRequested.connect(apply_events.append)
    page.reauthorizeRequested.connect(lambda: reauthorize_events.append(True))

    page.save_button.click()
    page.reauthorize_button.click()

    assert len(apply_events) == 1
    assert reauthorize_events == [True]
