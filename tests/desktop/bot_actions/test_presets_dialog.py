from __future__ import annotations

from pathlib import Path

from raidbot.desktop.models import BotActionPreset, BotActionSlotConfig


def _slot_1_config() -> BotActionSlotConfig:
    return BotActionSlotConfig(
        key="slot_1_r",
        label="R",
        template_path=Path("bot_actions/slot_1_r.png"),
        finish_template_path=Path("bot_actions/slot_1_r_finish.png"),
        presets=(
            BotActionPreset(
                id="preset-1",
                text="gm",
                image_path=Path("bot_actions/presets/gm.png"),
            ),
        ),
    )


def test_slot_1_presets_dialog_adds_removes_and_builds_slot_state(qtbot) -> None:
    from raidbot.desktop.bot_actions.presets_dialog import Slot1PresetsDialog

    dialog = Slot1PresetsDialog(slot=_slot_1_config())
    qtbot.addWidget(dialog)

    assert dialog.preset_list.count() == 1

    dialog.add_preset()
    assert dialog.preset_list.count() == 2

    dialog.preset_list.setCurrentRow(1)
    dialog.preset_text_input.setPlainText("wagmi")
    dialog.remove_selected_preset()

    updated_slot = dialog.build_updated_slot()

    assert updated_slot.presets == (
        BotActionPreset(
            id="preset-1",
            text="gm",
            image_path=Path("bot_actions/presets/gm.png"),
        ),
    )
    assert updated_slot.finish_template_path == Path("bot_actions/slot_1_r_finish.png")
