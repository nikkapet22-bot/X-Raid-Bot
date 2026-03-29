from __future__ import annotations

from pathlib import Path

from raidbot.desktop.models import (
    BotActionPreset,
    BotActionSlotConfig,
    DesktopAppConfig,
    default_bot_action_slots,
)


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


def test_default_bot_action_slots_include_empty_slot_1_preset_state() -> None:
    slot_1 = default_bot_action_slots()[0]

    assert slot_1.presets == ()
    assert slot_1.finish_template_path is None


def test_desktop_app_config_normalizes_partial_bot_action_slots_to_fixed_layout() -> None:
    config = DesktopAppConfig(
        telegram_api_id=123,
        telegram_api_hash="hash",
        telegram_session_path=Path("session.session"),
        telegram_phone_number=None,
        whitelisted_chat_ids=[111],
        allowed_sender_ids=[333],
        chrome_profile_directory="Default",
        bot_action_slots=(
            BotActionSlotConfig(
                key="unexpected-slot-1",
                label="X",
                enabled=True,
                template_path=Path("templates/custom-1.png"),
                updated_at="2026-03-28T12:00:00",
                presets=(
                    BotActionPreset(
                        id="preset-1",
                        text="gm",
                        image_path=Path("bot_actions/presets/gm.png"),
                    ),
                ),
                finish_template_path=Path("bot_actions/slot_1_r_finish.png"),
            ),
            BotActionSlotConfig(
                key="unexpected-slot-2",
                label="Y",
                enabled=False,
                template_path=Path("templates/custom-2.png"),
                updated_at="2026-03-28T12:01:00",
            ),
            BotActionSlotConfig(
                key="unexpected-slot-3",
                label="Z",
                enabled=True,
            ),
        ),
    )

    assert config.bot_action_slots == (
        BotActionSlotConfig(
            key="slot_1_r",
            label="R",
            enabled=True,
            template_path=Path("templates/custom-1.png"),
            updated_at="2026-03-28T12:00:00",
            presets=(
                BotActionPreset(
                    id="preset-1",
                    text="gm",
                    image_path=Path("bot_actions/presets/gm.png"),
                ),
            ),
            finish_template_path=Path("bot_actions/slot_1_r_finish.png"),
        ),
        BotActionSlotConfig(
            key="slot_2_l",
            label="L",
            enabled=False,
            template_path=Path("templates/custom-2.png"),
            updated_at="2026-03-28T12:01:00",
        ),
        BotActionSlotConfig(
            key="slot_3_r",
            label="R",
            enabled=True,
        ),
        BotActionSlotConfig(key="slot_4_b", label="B"),
    )
