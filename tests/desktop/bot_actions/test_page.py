from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QGroupBox

from raidbot.desktop.models import DesktopAppConfig


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


def test_bot_actions_page_renders_four_fixed_slots(qtbot) -> None:
    from raidbot.desktop.bot_actions.page import BotActionsPage

    page = BotActionsPage(config=build_config())
    qtbot.addWidget(page)

    assert [box.label_text() for box in page.slot_boxes] == ["R", "L", "R", "B"]
    assert not hasattr(page, "sequence_list")
    assert not hasattr(page, "dry_run_button")
    assert page.settle_delay_input.minimum() == 0
    assert page.settle_delay_input.maximum() == 10000
    assert page.settle_delay_input.value() == 1500
    assert "Timing" not in {group.title() for group in page.findChildren(QGroupBox)}


def test_bot_actions_page_renders_shared_page_ready_capture(qtbot) -> None:
    from raidbot.desktop.bot_actions.page import BotActionsPage

    page = BotActionsPage(config=build_config())
    qtbot.addWidget(page)

    assert page.page_ready_capture_button.text() == "Capture"
    assert page.page_ready_preview_label.text() == "No image"
    assert page.page_ready_status_label.text() == "No template captured."


def test_bot_actions_page_show_error_updates_status_label(qtbot) -> None:
    from raidbot.desktop.bot_actions.page import BotActionsPage

    page = BotActionsPage(config=build_config())
    qtbot.addWidget(page)

    page.show_error("capture failed")

    assert page.status_label.text() == "capture failed"
    assert page.status_latest_value_label.text() == "Error"
    assert page.status_last_error_value_label.text() == "capture failed"


def test_bot_actions_page_checkbox_emits_slot_enabled_signal_with_index_and_state(
    qtbot,
) -> None:
    from raidbot.desktop.bot_actions.page import BotActionsPage

    page = BotActionsPage(config=build_config())
    qtbot.addWidget(page)
    page.show()
    captured = []
    page.slotEnabledChanged.connect(
        lambda slot_index, enabled: captured.append((slot_index, enabled))
    )

    qtbot.mouseClick(page.slot_boxes[1].enabled_checkbox, Qt.MouseButton.LeftButton)
    qtbot.mouseClick(page.slot_boxes[1].enabled_checkbox, Qt.MouseButton.LeftButton)

    assert captured == [(1, True), (1, False)]


def test_bot_actions_page_capture_button_emits_slot_capture_signal_with_index(
    qtbot,
) -> None:
    from raidbot.desktop.bot_actions.page import BotActionsPage

    page = BotActionsPage(config=build_config())
    qtbot.addWidget(page)
    page.show()
    captured = []
    page.slotCaptureRequested.connect(captured.append)

    qtbot.mouseClick(page.slot_boxes[2].capture_button, Qt.MouseButton.LeftButton)

    assert captured == [2]
    assert page.status_label.text() == "Slot 3 (R): capturing"
    assert page.status_latest_value_label.text() == "Slot 3 (R): capturing"


def test_bot_actions_page_test_button_emits_slot_test_signal_with_index(
    qtbot,
) -> None:
    from raidbot.desktop.bot_actions.page import BotActionsPage

    page = BotActionsPage(config=build_config())
    qtbot.addWidget(page)
    page.show()
    captured = []
    page.slotTestRequested.connect(captured.append)

    qtbot.mouseClick(page.slot_boxes[1].test_button, Qt.MouseButton.LeftButton)

    assert captured == [1]
    assert page.status_label.text() == "Slot 2 (L): testing"
    assert page.status_latest_value_label.text() == "Slot 2 (L): testing"


def test_bot_actions_page_page_ready_capture_emits_signal(qtbot) -> None:
    from raidbot.desktop.bot_actions.page import BotActionsPage

    page = BotActionsPage(config=build_config())
    qtbot.addWidget(page)
    page.show()
    captured = []
    page.pageReadyCaptureRequested.connect(lambda: captured.append("capture"))

    qtbot.mouseClick(page.page_ready_capture_button, Qt.MouseButton.LeftButton)

    assert captured == ["capture"]
    assert page.status_label.text() == "Page Ready: capturing"
    assert page.status_latest_value_label.text() == "Page Ready: capturing"


def test_bot_actions_page_shows_presets_button_only_for_slot_1(qtbot) -> None:
    from raidbot.desktop.bot_actions.page import BotActionsPage

    page = BotActionsPage(config=build_config())
    qtbot.addWidget(page)

    assert page.slot_boxes[0].presets_button is not None
    assert page.slot_boxes[1].presets_button is None
    assert page.slot_boxes[2].presets_button is None
    assert page.slot_boxes[3].presets_button is None


def test_bot_actions_page_presets_button_emits_slot_presets_signal_with_index(
    qtbot,
) -> None:
    from raidbot.desktop.bot_actions.page import BotActionsPage

    page = BotActionsPage(config=build_config())
    qtbot.addWidget(page)
    page.show()
    captured = []
    page.slotPresetsRequested.connect(captured.append)

    qtbot.mouseClick(page.slot_boxes[0].presets_button, Qt.MouseButton.LeftButton)

    assert captured == [0]
    assert page.status_label.text() == "Slot 1 (R): presets"
    assert page.status_latest_value_label.text() == "Slot 1 (R): presets"


def test_bot_actions_page_places_capture_and_test_buttons_in_compact_row(qtbot) -> None:
    from raidbot.desktop.bot_actions.page import BotActionsPage

    page = BotActionsPage(config=build_config())
    qtbot.addWidget(page)

    box = page.slot_boxes[0]

    assert box.button_row_layout.indexOf(box.capture_button) == 0
    assert box.button_row_layout.indexOf(box.test_button) == 1
    assert box.button_row_layout.indexOf(box.presets_button) == 2


def test_bot_actions_page_places_toggle_next_to_slot_glyph(qtbot) -> None:
    from raidbot.desktop.bot_actions.page import BotActionsPage

    page = BotActionsPage(config=build_config())
    qtbot.addWidget(page)

    box = page.slot_boxes[0]

    assert box.header_layout.indexOf(box._dot) == 0
    assert box.header_layout.indexOf(box.slot_label) == 1
    assert box.header_layout.indexOf(box.enabled_checkbox) == 2
    assert box.header_layout.itemAt(3).spacerItem() is not None
    assert box.header_layout.indexOf(box.slot_number_label) == 4
    assert box.enabled_checkbox.sizeHint().width() == 34
    assert box.enabled_checkbox.sizeHint().height() == 18


def test_bot_actions_page_uses_compact_action_button_style(qtbot) -> None:
    from raidbot.desktop.bot_actions.page import BotActionsPage

    page = BotActionsPage(config=build_config())
    qtbot.addWidget(page)

    box = page.slot_boxes[0]

    assert page.page_ready_capture_button.property("botActionButton") == "true"
    assert box.capture_button.property("botActionButton") == "true"
    assert box.test_button.property("botActionButton") == "true"
    assert box.presets_button.property("botActionButton") == "true"
    assert box.presets_button.property("variant") == "secondary"
    assert page.page_ready_card.objectName() == "card"


def test_bot_actions_page_shows_thumbnail_preview_above_capture_button(
    qtbot,
    tmp_path,
) -> None:
    from raidbot.desktop.bot_actions.page import BotActionsPage

    image_path = tmp_path / "slot_1_r.png"
    image = QImage(12, 10, QImage.Format.Format_ARGB32)
    image.fill(QColor("red"))
    assert image.save(str(image_path))

    default_slots = build_config().bot_action_slots
    page = BotActionsPage(
        config=build_config(
            bot_action_slots=(
                default_slots[0].__class__(
                    key=default_slots[0].key,
                    label=default_slots[0].label,
                    enabled=default_slots[0].enabled,
                    template_path=image_path,
                    updated_at=default_slots[0].updated_at,
                ),
                *default_slots[1:],
            )
        )
    )
    qtbot.addWidget(page)

    preview_label = page.slot_boxes[0].template_preview_label

    assert preview_label.pixmap() is not None
    assert not preview_label.pixmap().isNull()
    assert page.slot_boxes[0].layout().indexOf(preview_label) < page.slot_boxes[0].layout().indexOf(
        page.slot_boxes[0].button_row_widget
    )
