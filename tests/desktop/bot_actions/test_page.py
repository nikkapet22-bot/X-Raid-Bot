from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QGroupBox, QLabel

from raidbot.desktop.models import DesktopAppConfig


def _write_solid_image(path: Path, color: str) -> None:
    image = QImage(120, 72, QImage.Format.Format_ARGB32)
    image.fill(QColor(color))
    assert image.save(str(path))


def _label_center_hex(label: QLabel) -> str:
    pixmap = label.pixmap()
    assert pixmap is not None
    image = pixmap.toImage()
    return image.pixelColor(image.width() // 2, image.height() // 2).name()


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

    assert [box.label_text() for box in page.slot_boxes] == [
        "Reply",
        "Like",
        "Repost",
        "Bookmark",
    ]
    assert not hasattr(page, "sequence_list")
    assert not hasattr(page, "dry_run_button")
    assert not hasattr(page, "settle_delay_input")
    assert page.slot_1_finish_delay_input.minimum() == 0
    assert page.slot_1_finish_delay_input.maximum() == 10
    assert page.slot_1_finish_delay_input.value() == 2
    assert "Timing" not in {group.title() for group in page.findChildren(QGroupBox)}


def test_bot_actions_page_renders_shared_page_ready_capture(qtbot) -> None:
    from raidbot.desktop.bot_actions.page import BotActionsPage

    page = BotActionsPage(config=build_config())
    qtbot.addWidget(page)

    assert page.page_ready_capture_button.text() == "Capture"
    assert page.page_ready_preview_label.text() == "No image"
    assert page.page_ready_status_label.text() == "No template captured."


def test_bot_actions_page_renders_shared_page_exit_capture(qtbot) -> None:
    from raidbot.desktop.bot_actions.page import BotActionsPage

    page = BotActionsPage(config=build_config())
    qtbot.addWidget(page)

    assert page.page_exit_capture_button.text() == "Capture"
    assert page.page_exit_preview_label.text() == "No image"
    assert page.page_exit_status_label.text() == "No template captured."


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
    assert page.status_label.text() == "Slot 3 (Repost): capturing"
    assert page.status_latest_value_label.text() == "Slot 3 (Repost): capturing"


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
    assert page.status_label.text() == "Slot 2 (Like): testing"
    assert page.status_latest_value_label.text() == "Slot 2 (Like): testing"


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


def test_bot_actions_page_page_exit_capture_emits_signal(qtbot) -> None:
    from raidbot.desktop.bot_actions.page import BotActionsPage

    page = BotActionsPage(config=build_config())
    qtbot.addWidget(page)
    page.show()
    captured = []
    page.pageExitCaptureRequested.connect(lambda: captured.append("capture"))

    qtbot.mouseClick(page.page_exit_capture_button, Qt.MouseButton.LeftButton)

    assert captured == ["capture"]
    assert page.status_label.text() == "Page Exit: capturing"
    assert page.status_latest_value_label.text() == "Page Exit: capturing"


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
    assert page.status_label.text() == "Slot 1 (Reply): presets"
    assert page.status_latest_value_label.text() == "Slot 1 (Reply): presets"


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
    assert box.header_layout.indexOf(box.finish_delay_widget) == 4
    assert box.enabled_checkbox.sizeHint().width() == 34
    assert box.enabled_checkbox.sizeHint().height() == 18


def test_bot_actions_page_removes_visible_slot_number_labels(qtbot) -> None:
    from raidbot.desktop.bot_actions.page import BotActionsPage

    page = BotActionsPage(config=build_config())
    qtbot.addWidget(page)

    visible_text = {
        label.text() for label in page.findChildren(QLabel) if label.text().strip()
    }

    assert "Slot 1" not in visible_text
    assert "Slot 2" not in visible_text
    assert "Slot 3" not in visible_text
    assert "Slot 4" not in visible_text


def test_bot_actions_page_shows_finish_delay_only_on_slot_1(qtbot) -> None:
    from raidbot.desktop.bot_actions.page import BotActionsPage

    page = BotActionsPage(config=build_config(slot_1_finish_delay_seconds=4))
    qtbot.addWidget(page)

    assert page.slot_boxes[0].finish_delay_widget is not None
    assert page.slot_boxes[0].finish_delay_label.text() == "Finish Delay"
    assert page.slot_boxes[0].finish_delay_input is page.slot_1_finish_delay_input
    assert page.slot_boxes[0].finish_delay_input.value() == 4
    assert page.slot_boxes[1].finish_delay_widget is None
    assert page.slot_boxes[2].finish_delay_widget is None
    assert page.slot_boxes[3].finish_delay_widget is None


def test_bot_actions_page_finish_delay_emits_updated_value(qtbot) -> None:
    from raidbot.desktop.bot_actions.page import BotActionsPage

    page = BotActionsPage(config=build_config())
    qtbot.addWidget(page)
    captured = []
    page.slot1FinishDelayChanged.connect(captured.append)

    page.slot_1_finish_delay_input.setValue(4)

    assert captured == [4]


def test_bot_actions_page_uses_inline_finish_delay_header_controls(qtbot) -> None:
    from raidbot.desktop.bot_actions.page import BotActionsPage

    page = BotActionsPage(config=build_config())
    qtbot.addWidget(page)

    box = page.slot_boxes[0]

    assert box.finish_delay_widget.objectName() == "finishDelayInline"
    assert box.finish_delay_input.objectName() == "finishDelayInput"
    assert box.finish_delay_input.minimumWidth() >= 48


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
    assert page.slot_boxes[0].layout().indexOf(page.slot_boxes[0].preview_row_widget) < page.slot_boxes[0].layout().indexOf(
        page.slot_boxes[0].button_row_widget
    )


def test_bot_actions_page_refreshes_slot_preview_when_same_path_is_overwritten(
    qtbot,
    tmp_path,
) -> None:
    from raidbot.desktop.bot_actions.page import BotActionsPage

    image_path = tmp_path / "slot_1_r.png"
    _write_solid_image(image_path, "#ff0000")
    default_slots = build_config().bot_action_slots
    page = BotActionsPage(
        config=build_config(
            bot_action_slots=(
                replace(default_slots[0], template_path=image_path),
                *default_slots[1:],
            )
        )
    )
    qtbot.addWidget(page)

    _write_solid_image(image_path, "#00ff00")
    page.set_slots((replace(default_slots[0], template_path=image_path), *default_slots[1:]))

    assert _label_center_hex(page.slot_boxes[0].template_preview_label) == "#00ff00"


def test_bot_actions_page_refreshes_page_ready_preview_when_same_path_is_overwritten(
    qtbot,
    tmp_path,
) -> None:
    from raidbot.desktop.bot_actions.page import BotActionsPage

    image_path = tmp_path / "page_ready.png"
    _write_solid_image(image_path, "#ff0000")
    page = BotActionsPage(config=build_config(page_ready_template_path=image_path))
    qtbot.addWidget(page)

    _write_solid_image(image_path, "#00ff00")
    page.set_page_ready_template_path(image_path)

    assert _label_center_hex(page.page_ready_preview_label) == "#00ff00"


def test_bot_actions_page_refreshes_page_exit_preview_when_same_path_is_overwritten(
    qtbot,
    tmp_path,
) -> None:
    from raidbot.desktop.bot_actions.page import BotActionsPage

    image_path = tmp_path / "page_exit.png"
    _write_solid_image(image_path, "#ff0000")
    page = BotActionsPage(config=build_config(page_exit_template_path=image_path))
    qtbot.addWidget(page)

    _write_solid_image(image_path, "#00ff00")
    page.set_page_exit_template_path(image_path)

    assert _label_center_hex(page.page_exit_preview_label) == "#00ff00"


def test_bot_actions_page_shows_slot_1_finish_preview_tile(qtbot, tmp_path) -> None:
    from raidbot.desktop.bot_actions.page import BotActionsPage

    image_path = tmp_path / "slot_1_r_finish.png"
    _write_solid_image(image_path, "#00ff00")
    default_slots = build_config().bot_action_slots
    page = BotActionsPage(
        config=build_config(
            bot_action_slots=(
                replace(default_slots[0], finish_template_path=image_path),
                *default_slots[1:],
            )
        )
    )
    qtbot.addWidget(page)

    finish_preview_label = page.slot_boxes[0].finish_preview_label

    assert finish_preview_label is not None
    assert finish_preview_label.pixmap() is not None
    assert _label_center_hex(finish_preview_label) == "#00ff00"


def test_bot_actions_page_shows_empty_slot_1_finish_preview_state(qtbot) -> None:
    from raidbot.desktop.bot_actions.page import BotActionsPage

    page = BotActionsPage(config=build_config())
    qtbot.addWidget(page)

    finish_preview_label = page.slot_boxes[0].finish_preview_label

    assert finish_preview_label is not None
    assert finish_preview_label.text() == "No finish image"


def test_bot_actions_page_renders_troubleshooting_cldf_section(qtbot) -> None:
    from raidbot.desktop.bot_actions.page import BotActionsPage

    page = BotActionsPage(config=build_config())
    qtbot.addWidget(page)

    titles = {group.title() for group in page.findChildren(QGroupBox)}

    assert "Troubleshooting" not in titles
    assert "CLDF Capture Path" in titles
    assert "Black Box Escape" in titles


def test_bot_actions_page_renders_three_cldf_troubleshoot_cards(qtbot) -> None:
    from raidbot.desktop.bot_actions.page import BotActionsPage

    page = BotActionsPage(config=build_config())
    qtbot.addWidget(page)

    assert [box.label_text() for box in page.cldf_boxes] == ["1", "2", "3"]


def test_bot_actions_page_renders_one_black_box_troubleshoot_card(qtbot) -> None:
    from raidbot.desktop.bot_actions.page import BotActionsPage

    page = BotActionsPage(config=build_config())
    qtbot.addWidget(page)

    assert [box.label_text() for box in page.black_box_boxes] == ["Box"]
    assert page.troubleshoot_groups["black_box"] == page.black_box_boxes


def test_bot_actions_page_troubleshoot_cards_only_show_preview_capture_and_test(qtbot) -> None:
    from raidbot.desktop.bot_actions.page import BotActionsPage

    page = BotActionsPage(config=build_config())
    qtbot.addWidget(page)

    for box in page.cldf_boxes:
        assert box.template_preview_label is not None
        assert box.capture_button.text() == "Capture"
        assert box.test_button.text() == "Test"
        assert not hasattr(box, "enabled_checkbox")
        assert not hasattr(box, "presets_button")
        assert not hasattr(box, "finish_delay_input")


def test_bot_actions_page_troubleshoot_capture_emits_group_and_index(qtbot) -> None:
    from raidbot.desktop.bot_actions.page import BotActionsPage

    page = BotActionsPage(config=build_config())
    qtbot.addWidget(page)
    page.show()
    captured = []
    page.troubleshootCaptureRequested.connect(
        lambda group_key, item_index: captured.append((group_key, item_index))
    )

    qtbot.mouseClick(page.cldf_boxes[1].capture_button, Qt.MouseButton.LeftButton)

    assert captured == [("cldf", 1)]
    assert page.status_label.text() == "Troubleshoot CLDF 2: capturing"
    assert page.status_latest_value_label.text() == "Troubleshoot CLDF 2: capturing"


def test_bot_actions_page_troubleshoot_test_emits_group_and_index(qtbot) -> None:
    from raidbot.desktop.bot_actions.page import BotActionsPage

    page = BotActionsPage(config=build_config())
    qtbot.addWidget(page)
    page.show()
    captured = []
    page.troubleshootTestRequested.connect(
        lambda group_key, item_index: captured.append((group_key, item_index))
    )

    qtbot.mouseClick(page.cldf_boxes[2].test_button, Qt.MouseButton.LeftButton)

    assert captured == [("cldf", 2)]
    assert page.status_label.text() == "Troubleshoot CLDF 3: testing"
    assert page.status_latest_value_label.text() == "Troubleshoot CLDF 3: testing"


def test_bot_actions_page_black_box_capture_emits_group_and_index(qtbot) -> None:
    from raidbot.desktop.bot_actions.page import BotActionsPage

    page = BotActionsPage(config=build_config())
    qtbot.addWidget(page)
    page.show()
    captured = []
    page.troubleshootCaptureRequested.connect(
        lambda group_key, item_index: captured.append((group_key, item_index))
    )

    qtbot.mouseClick(page.black_box_boxes[0].capture_button, Qt.MouseButton.LeftButton)

    assert captured == [("black_box", 0)]
    assert page.status_label.text() == "Troubleshoot BLACK BOX 1: capturing"
    assert page.status_latest_value_label.text() == "Troubleshoot BLACK BOX 1: capturing"
