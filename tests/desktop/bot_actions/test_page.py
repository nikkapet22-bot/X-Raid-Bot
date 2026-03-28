from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage

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


def test_bot_actions_page_show_error_updates_status_label(qtbot) -> None:
    from raidbot.desktop.bot_actions.page import BotActionsPage

    page = BotActionsPage(config=build_config())
    qtbot.addWidget(page)

    page.show_error("capture failed")

    assert page.status_label.text() == "capture failed"


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
        page.slot_boxes[0].capture_button
    )
