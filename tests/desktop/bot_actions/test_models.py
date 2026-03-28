from __future__ import annotations

from raidbot.desktop.models import BotActionSlotConfig, default_bot_action_slots


def test_default_bot_action_slots_are_fixed_labels_and_disabled() -> None:
    slots = default_bot_action_slots()

    assert slots == (
        BotActionSlotConfig(key="slot_1_r", label="R"),
        BotActionSlotConfig(key="slot_2_l", label="L"),
        BotActionSlotConfig(key="slot_3_r", label="R"),
        BotActionSlotConfig(key="slot_4_b", label="B"),
    )
    assert all(slot.enabled is False for slot in slots)
    assert all(slot.template_path is None for slot in slots)
    assert all(slot.updated_at is None for slot in slots)


def test_bot_action_slot_config_defaults_are_disabled_and_empty() -> None:
    slot = BotActionSlotConfig(key="slot_1_r", label="R")

    assert slot == BotActionSlotConfig(
        key="slot_1_r",
        label="R",
        enabled=False,
        template_path=None,
        updated_at=None,
    )
    assert slot.enabled is False
    assert slot.template_path is None
    assert slot.updated_at is None
