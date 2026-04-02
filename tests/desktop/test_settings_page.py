from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt

from raidbot.desktop.models import DesktopAppConfig, RaidProfileConfig
from raidbot.desktop.telegram_setup import AccessibleChat


def build_config(**overrides) -> DesktopAppConfig:
    values = {
        "telegram_api_id": 123456,
        "telegram_api_hash": "hash-value",
        "telegram_session_path": Path("raidbot.session"),
        "telegram_phone_number": "+40123456789",
        "whitelisted_chat_ids": [-1001],
        "allowed_sender_ids": [42],
        "allowed_sender_entries": ("42",),
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


def build_available_chats() -> list[AccessibleChat]:
    return [
        AccessibleChat(chat_id=-1001, title="Raid Group"),
        AccessibleChat(chat_id=-2002, title="Launch Squad"),
        AccessibleChat(chat_id=-3003, title="Alpha Team"),
    ]


def set_selected_chat_rows(page, qtbot, chat_ids: list[int]) -> None:
    while len(page.chat_row_combos) < len(chat_ids):
        qtbot.mouseClick(page.add_chat_button, Qt.MouseButton.LeftButton)
    while len(page.chat_row_combos) > len(chat_ids):
        qtbot.mouseClick(page.chat_remove_buttons[-1], Qt.MouseButton.LeftButton)
    for combo, chat_id in zip(page.chat_row_combos, chat_ids):
        index = combo.findData(chat_id)
        assert index >= 0
        combo.setCurrentIndex(index)


def test_settings_save_emits_sender_entries_and_numeric_sender_ids(qtbot) -> None:
    from raidbot.desktop.settings_page import SettingsPage

    page = SettingsPage(
        config=build_config(),
        available_profiles=["Default", "Profile 3", "Profile 9"],
        available_chats=build_available_chats(),
        session_status="authorized",
    )
    qtbot.addWidget(page)

    applied = []
    page.applyRequested.connect(applied.append)

    page.api_hash_input.setText("new-hash")
    set_selected_chat_rows(page, qtbot, [-1001, -2002])
    page.sender_entry_inputs[0].setText("99")
    qtbot.mouseClick(page.add_sender_button, Qt.MouseButton.LeftButton)
    page.sender_entry_inputs[1].setText("@delugeraidbot")
    qtbot.mouseClick(page.save_button, Qt.MouseButton.LeftButton)

    assert applied == [
        build_config(
            telegram_api_hash="new-hash",
            whitelisted_chat_ids=[-1001, -2002],
            allowed_sender_ids=[99],
            allowed_sender_entries=("99", "@delugeraidbot"),
            chrome_profile_directory="Profile 3",
        )
    ]


def test_settings_save_preserves_hidden_bot_action_config(qtbot) -> None:
    from raidbot.desktop.settings_page import SettingsPage

    updated_config = build_config(
        auto_run_enabled=True,
        default_auto_sequence_id="seq-9",
        auto_run_settle_ms=2750,
        bot_action_slots=(
            replace(build_config().bot_action_slots[0], enabled=True, template_path=Path("slot-1.png")),
            replace(build_config().bot_action_slots[1], enabled=True, template_path=Path("slot-2.png")),
            *build_config().bot_action_slots[2:],
        ),
    )
    page = SettingsPage(
        config=build_config(),
        available_profiles=["Default", "Profile 3", "Profile 9"],
        available_chats=build_available_chats(),
        session_status="authorized",
    )
    qtbot.addWidget(page)
    page.set_config(updated_config)

    applied = []
    page.applyRequested.connect(applied.append)

    page.api_hash_input.setText("new-hash")
    set_selected_chat_rows(page, qtbot, [-1001, -2002])
    page.sender_entry_inputs[0].setText("99")
    qtbot.mouseClick(page.save_button, Qt.MouseButton.LeftButton)

    assert len(applied) == 1
    assert applied[0].auto_run_enabled is True
    assert applied[0].default_auto_sequence_id == "seq-9"
    assert applied[0].auto_run_settle_ms == 2750
    assert applied[0].bot_action_slots == updated_config.bot_action_slots


def test_settings_save_rejects_invalid_numeric_input_without_crashing(qtbot) -> None:
    from raidbot.desktop.settings_page import SettingsPage

    page = SettingsPage(
        config=build_config(),
        available_profiles=["Default", "Profile 3", "Profile 9"],
        available_chats=build_available_chats(),
        session_status="authorized",
    )
    qtbot.addWidget(page)

    applied = []
    page.applyRequested.connect(applied.append)

    page.api_id_input.setText("not-a-number")
    set_selected_chat_rows(page, qtbot, [-1001, -2002])
    page.sender_entry_inputs[0].setText("99")
    qtbot.mouseClick(page.save_button, Qt.MouseButton.LeftButton)

    assert applied == []
    assert "Telegram API ID must be a valid integer." in page.status_label.text()


def test_settings_save_rejects_blank_telegram_api_hash(qtbot) -> None:
    from raidbot.desktop.settings_page import SettingsPage

    page = SettingsPage(
        config=build_config(),
        available_profiles=["Default", "Profile 3", "Profile 9"],
        available_chats=build_available_chats(),
        session_status="authorized",
    )
    qtbot.addWidget(page)

    applied = []
    page.applyRequested.connect(applied.append)

    page.api_hash_input.setText("   ")
    set_selected_chat_rows(page, qtbot, [-1001, -2002])
    page.sender_entry_inputs[0].setText("99")
    qtbot.mouseClick(page.save_button, Qt.MouseButton.LeftButton)

    assert applied == []
    assert "Telegram API Hash is required." in page.status_label.text()


def test_settings_save_clears_previous_error_on_success(qtbot) -> None:
    from raidbot.desktop.settings_page import SettingsPage

    page = SettingsPage(
        config=build_config(),
        available_profiles=["Default", "Profile 3", "Profile 9"],
        available_chats=build_available_chats(),
        session_status="authorized",
    )
    qtbot.addWidget(page)

    applied = []
    page.applyRequested.connect(applied.append)

    page.api_id_input.setText("not-a-number")
    qtbot.mouseClick(page.save_button, Qt.MouseButton.LeftButton)
    assert "Telegram API ID must be a valid integer." in page.status_label.text()

    page.api_id_input.setText("123456")
    set_selected_chat_rows(page, qtbot, [-1001, -2002])
    page.sender_entry_inputs[0].setText("99")
    qtbot.mouseClick(page.save_button, Qt.MouseButton.LeftButton)

    assert len(applied) == 1
    assert page.status_label.text() == ""


def test_settings_save_rejects_when_all_sender_rows_are_blank(qtbot) -> None:
    from raidbot.desktop.settings_page import SettingsPage

    page = SettingsPage(
        config=build_config(),
        available_profiles=["Default", "Profile 3", "Profile 9"],
        available_chats=build_available_chats(),
        session_status="authorized",
    )
    qtbot.addWidget(page)

    applied = []
    page.applyRequested.connect(applied.append)

    page.api_id_input.setText("123456")
    page.api_hash_input.setText("new-hash")
    set_selected_chat_rows(page, qtbot, [-1001, -2002])
    page.sender_entry_inputs[0].setText("   ")
    qtbot.mouseClick(page.save_button, Qt.MouseButton.LeftButton)

    assert applied == []
    assert "At least one allowed sender is required." in page.status_label.text()


def test_settings_save_rejects_missing_persisted_sender_rows(qtbot) -> None:
    from raidbot.desktop.settings_page import SettingsPage

    page = SettingsPage(
        config=build_config(allowed_sender_ids=[], allowed_sender_entries=()),
        available_profiles=["Default", "Profile 3", "Profile 9"],
        available_chats=build_available_chats(),
        session_status="authorized",
    )
    qtbot.addWidget(page)

    applied = []
    page.applyRequested.connect(applied.append)

    qtbot.mouseClick(page.save_button, Qt.MouseButton.LeftButton)

    assert applied == []
    assert "At least one allowed sender is required." in page.status_label.text()


def test_settings_save_rejects_stale_allowed_chat_without_crashing(qtbot) -> None:
    from raidbot.desktop.settings_page import SettingsPage

    page = SettingsPage(
        config=build_config(whitelisted_chat_ids=[-9999]),
        available_profiles=["Default", "Profile 3", "Profile 9"],
        available_chats=build_available_chats(),
        session_status="authorized",
    )
    qtbot.addWidget(page)

    applied = []
    page.applyRequested.connect(applied.append)

    page.api_id_input.setText("123456")
    page.sender_entry_inputs[0].setText("99")
    qtbot.mouseClick(page.save_button, Qt.MouseButton.LeftButton)

    assert applied == []
    assert "Allowed chats contain chats that are no longer available." in page.status_label.text()


def test_settings_page_supports_adding_and_removing_chat_rows(qtbot) -> None:
    from raidbot.desktop.settings_page import SettingsPage

    page = SettingsPage(
        config=build_config(),
        available_profiles=["Default", "Profile 3", "Profile 9"],
        available_chats=build_available_chats(),
        session_status="authorized",
    )
    qtbot.addWidget(page)

    assert [combo.currentData() for combo in page.chat_row_combos] == [-1001]

    qtbot.mouseClick(page.add_chat_button, Qt.MouseButton.LeftButton)
    new_combo = page.chat_row_combos[1]
    new_combo.setCurrentIndex(new_combo.findData(-2002))
    qtbot.mouseClick(page.chat_remove_buttons[0], Qt.MouseButton.LeftButton)

    assert [combo.currentData() for combo in page.chat_row_combos] == [-2002]


def test_settings_page_supports_adding_and_removing_sender_rows(qtbot) -> None:
    from raidbot.desktop.settings_page import SettingsPage

    page = SettingsPage(
        config=build_config(),
        available_profiles=["Default", "Profile 3", "Profile 9"],
        available_chats=build_available_chats(),
        session_status="authorized",
    )
    qtbot.addWidget(page)

    assert [entry.text() for entry in page.sender_entry_inputs] == ["42"]

    qtbot.mouseClick(page.add_sender_button, Qt.MouseButton.LeftButton)
    page.sender_entry_inputs[1].setText("@delugeraidbot")
    qtbot.mouseClick(page.sender_remove_buttons[0], Qt.MouseButton.LeftButton)

    assert [entry.text() for entry in page.sender_entry_inputs] == ["@delugeraidbot"]


def test_settings_page_scan_button_emits_selected_chat_ids(qtbot) -> None:
    from raidbot.desktop.settings_page import SettingsPage

    page = SettingsPage(
        config=build_config(),
        available_profiles=["Default", "Profile 3", "Profile 9"],
        available_chats=build_available_chats(),
        session_status="authorized",
    )
    qtbot.addWidget(page)

    scan_requests = []
    page.senderScanRequested.connect(
        lambda button, chat_ids: scan_requests.append((button, chat_ids))
    )
    set_selected_chat_rows(page, qtbot, [-1001, -2002])

    qtbot.mouseClick(page.sender_scan_buttons[0], Qt.MouseButton.LeftButton)

    assert scan_requests == [(page.sender_scan_buttons[0], [-1001, -2002])]
    assert page.sender_scan_buttons[0].text() == "Scanning..."
    assert page.sender_scan_buttons[0].isEnabled() is False


def test_settings_page_appends_scanned_sender_entries_without_duplicates(qtbot) -> None:
    from raidbot.desktop.settings_page import SettingsPage

    page = SettingsPage(
        config=build_config(),
        available_profiles=["Default", "Profile 3", "Profile 9"],
        available_chats=build_available_chats(),
        session_status="authorized",
    )
    qtbot.addWidget(page)

    page.sender_entry_inputs[0].setText("@raidar")

    page.append_allowed_sender_entries(
        ["@raidar", "@RallyGuard_Raid_Bot", "@delugeraidbot"]
    )

    assert [entry.text() for entry in page.sender_entry_inputs] == [
        "@raidar",
        "@RallyGuard_Raid_Bot",
        "@delugeraidbot",
    ]


def test_settings_page_marks_sender_allowlist_as_required(qtbot) -> None:
    from raidbot.desktop.settings_page import SettingsPage

    page = SettingsPage(
        config=build_config(),
        available_profiles=["Default", "Profile 3"],
        available_chats=build_available_chats(),
        session_status="authorized",
    )
    qtbot.addWidget(page)

    assert page.sender_entry_inputs[0].placeholderText() == "Sender username or ID"
    assert page.allowed_senders_hint_label.text() == "Required to start the bot."
    assert page.add_sender_button.text() == "Add sender"
    assert page.sender_scan_buttons[0].text() == "Scan"


def test_settings_page_exposes_session_status_and_reauthorize(qtbot) -> None:
    from raidbot.desktop.settings_page import SettingsPage

    page = SettingsPage(
        config=build_config(),
        available_profiles=["Default", "Profile 3"],
        available_chats=build_available_chats(),
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
        available_chats=build_available_chats(),
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
        available_chats=build_available_chats(),
        session_status="unknown",
    )
    qtbot.addWidget(page)

    page.set_session_status("authorized")
    page.set_available_chats(build_available_chats()[1:])
    page.set_available_profiles(["Default", "Profile 3", "Profile 9"])

    assert page.session_status_label.text() == "authorized"
    assert [page.chat_row_combos[0].itemText(index) for index in range(page.chat_row_combos[0].count())] == [
        "Missing chat [-1001]",
        "Alpha Team [-3003]",
        "Launch Squad [-2002]",
    ]
    assert [page.profile_combo.itemText(index) for index in range(page.profile_combo.count())] == [
        "Default",
        "Profile 3",
        "Profile 9",
    ]
    assert page.profile_combo.currentText() == "Profile 3"


def test_settings_page_rejects_duplicate_profile_add_with_clear_status(qtbot) -> None:
    from raidbot.desktop.settings_page import SettingsPage

    page = SettingsPage(
        config=build_config(
            chrome_profile_directory="Default",
            raid_profiles=(
                RaidProfileConfig(profile_directory="Default", label="George", enabled=True),
                RaidProfileConfig(profile_directory="Profile 3", label="Maria", enabled=True),
            ),
        ),
        available_profiles=["Default", "Profile 3", "Profile 9"],
        available_chats=build_available_chats(),
        session_status="authorized",
    )
    qtbot.addWidget(page)
    added = []
    page.raidProfileAddRequested.connect(lambda directory, label: added.append((directory, label)))

    page.available_profile_combo.setCurrentText("Profile 3")
    qtbot.mouseClick(page.add_profile_button, Qt.MouseButton.LeftButton)

    assert added == []
    assert page.status_label.text() == "Profile already added"


def test_settings_page_uses_grouped_sections_and_primary_save(qtbot) -> None:
    from raidbot.desktop.settings_page import SettingsPage
    from raidbot.desktop.theme import SECTION_OBJECT_NAME

    page = SettingsPage(
        config=build_config(),
        available_profiles=["Default", "Profile 3"],
        available_chats=build_available_chats(),
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


def test_settings_page_hides_legacy_automation_controls(qtbot) -> None:
    from raidbot.desktop.settings_page import SettingsPage

    page = SettingsPage(
        config=build_config(),
        available_profiles=["Default", "Profile 3"],
        available_chats=build_available_chats(),
        session_status="authorized",
    )
    qtbot.addWidget(page)

    assert not hasattr(page, "automation_section")
    assert not hasattr(page, "browser_mode_combo")
    assert not hasattr(page, "executor_name_label")
    assert not hasattr(page, "reply_pool_input")
    assert not hasattr(page, "like_toggle")
    assert not hasattr(page, "repost_toggle")
    assert not hasattr(page, "bookmark_toggle")
    assert not hasattr(page, "reply_toggle")


def test_settings_page_preserves_apply_and_reauthorize_signals(qtbot) -> None:
    from raidbot.desktop.settings_page import SettingsPage

    apply_events = []
    reauthorize_events = []
    page = SettingsPage(
        config=build_config(),
        available_profiles=["Default", "Profile 3"],
        available_chats=build_available_chats(),
        session_status="authorized",
    )
    qtbot.addWidget(page)
    page.applyRequested.connect(apply_events.append)
    page.reauthorizeRequested.connect(lambda: reauthorize_events.append(True))

    page.save_button.click()
    page.reauthorize_button.click()

    assert len(apply_events) == 1
    assert reauthorize_events == [True]


def test_settings_page_exposes_status_feedback_helpers(qtbot) -> None:
    from raidbot.desktop.settings_page import SettingsPage

    page = SettingsPage(
        config=build_config(),
        available_profiles=["Default", "Profile 3"],
        session_status="authorized",
    )
    qtbot.addWidget(page)

    page.show_error("Resolve failed.")
    assert "Resolve failed." in page.status_label.text()

    page.show_success("Settings saved.")
    assert "Settings saved." in page.status_label.text()
