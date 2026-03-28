from __future__ import annotations

from pathlib import Path

from raidbot.desktop.bot_actions.sequence import build_bot_action_sequence
from raidbot.desktop.models import BotActionSlotConfig


def test_build_bot_action_sequence_keeps_enabled_slots_in_left_to_right_order() -> None:
    sequence = build_bot_action_sequence(
        [
            BotActionSlotConfig(
                key="slot_1_r",
                label="R",
                enabled=True,
                template_path=Path("captures/r.png"),
            ),
            BotActionSlotConfig(
                key="slot_2_l",
                label="L",
                enabled=False,
                template_path=Path("captures/l.png"),
            ),
            BotActionSlotConfig(
                key="slot_3_r",
                label="R",
                enabled=True,
                template_path=Path("captures/r2.png"),
            ),
            BotActionSlotConfig(
                key="slot_4_b",
                label="B",
                enabled=True,
                template_path=None,
            ),
        ]
    )

    assert sequence.id == "bot-actions"
    assert sequence.name == "Bot Actions"
    assert [step.name for step in sequence.steps] == ["slot_1_r", "slot_3_r"]
    assert [step.template_path for step in sequence.steps] == [
        Path("captures/r.png"),
        Path("captures/r2.png"),
    ]
    assert all(step.match_threshold == 0.9 for step in sequence.steps)
    assert all(step.max_search_seconds == 1.0 for step in sequence.steps)
    assert all(step.max_scroll_attempts == 0 for step in sequence.steps)
    assert all(step.scroll_amount == -120 for step in sequence.steps)
    assert all(step.max_click_attempts == 1 for step in sequence.steps)
    assert all(step.post_click_settle_ms == 250 for step in sequence.steps)
