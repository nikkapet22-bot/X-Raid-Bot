from __future__ import annotations

from pathlib import Path

from raidbot.desktop.bot_actions.sequence import (
    build_slot_1_preset_chooser,
    build_bot_action_sequence,
    build_slot_test_sequence,
)
from raidbot.desktop.models import BotActionPreset, BotActionSlotConfig


def test_build_bot_action_sequence_places_slot_1_last() -> None:
    result = build_bot_action_sequence(
        [
            BotActionSlotConfig(
                key="slot_1_r",
                label="R",
                enabled=True,
                template_path=Path("captures/r.png"),
                presets=(
                    BotActionPreset(id="preset-1", text="gm"),
                ),
                finish_template_path=Path("captures/finish.png"),
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
    sequence = result.sequence

    assert sequence.id == "bot-actions"
    assert sequence.name == "Bot Actions"
    assert [step.name for step in sequence.steps] == ["slot_3_r", "slot_1_r"]
    assert [step.template_path for step in sequence.steps] == [
        Path("captures/r2.png"),
        Path("captures/r.png"),
    ]
    assert all(step.match_threshold == 0.9 for step in sequence.steps)
    assert all(step.max_search_seconds == 2.0 for step in sequence.steps)
    assert [step.max_scroll_attempts for step in sequence.steps] == [4, 4]
    assert all(step.scroll_amount == -360 for step in sequence.steps)
    assert [step.max_click_attempts for step in sequence.steps] == [2, 1]
    assert all(step.post_click_settle_ms == 250 for step in sequence.steps)
    assert [step.pre_confirm_clicks for step in sequence.steps] == [2, 1]
    assert [step.inter_click_delay_ms for step in sequence.steps] == [500, 500]
    assert result.warnings == ()


def test_build_slot_test_sequence_keeps_shorter_search_window() -> None:
    sequence = build_slot_test_sequence(
        BotActionSlotConfig(
            key="slot_2_l",
            label="L",
            enabled=True,
            template_path=Path("captures/l.png"),
        )
    )

    assert sequence.id == "slot-test-slot_2_l"
    assert sequence.name == "Test L"
    assert [step.name for step in sequence.steps] == ["slot_2_l"]
    assert [step.max_search_seconds for step in sequence.steps] == [1.0]


def test_build_bot_action_sequence_chooses_random_slot_1_preset() -> None:
    result = build_bot_action_sequence(
        (
            BotActionSlotConfig(
                key="slot_1_r",
                label="R",
                enabled=True,
                template_path=Path("captures/r.png"),
                finish_template_path=Path("captures/finish.png"),
                presets=(
                    BotActionPreset(id="preset-1", text="gm"),
                    BotActionPreset(
                        id="preset-2",
                        text="wagmi",
                        image_path=Path("captures/reply.png"),
                    ),
                ),
            ),
        ),
        choose_preset=lambda presets: presets[1],
    )

    step = result.sequence.steps[0]

    assert step.name == "slot_1_r"
    assert step.preset_text == "wagmi"
    assert step.preset_image_path == Path("captures/reply.png")
    assert step.finish_template_path == Path("captures/finish.png")
    assert result.warnings == ()


def test_build_bot_action_sequence_skips_slot_1_when_no_presets_exist() -> None:
    result = build_bot_action_sequence(
        (
            BotActionSlotConfig(
                key="slot_1_r",
                label="R",
                enabled=True,
                template_path=Path("captures/r.png"),
            ),
            BotActionSlotConfig(
                key="slot_2_l",
                label="L",
                enabled=True,
                template_path=Path("captures/l.png"),
            ),
        ),
    )

    assert [step.name for step in result.sequence.steps] == ["slot_2_l"]
    assert result.warnings[0].slot_index == 0
    assert result.warnings[0].reason == "no_presets_configured"


def test_build_bot_action_sequence_assigns_scroll_budget_to_all_enabled_slots() -> None:
    result = build_bot_action_sequence(
        (
            BotActionSlotConfig(
                key="slot_1_r",
                label="R",
                enabled=False,
                template_path=Path("captures/r.png"),
            ),
            BotActionSlotConfig(
                key="slot_2_l",
                label="L",
                enabled=True,
                template_path=Path("captures/l.png"),
            ),
            BotActionSlotConfig(
                key="slot_3_r",
                label="R",
                enabled=True,
                template_path=Path("captures/r2.png"),
            ),
        )
    )

    assert [step.name for step in result.sequence.steps] == ["slot_2_l", "slot_3_r"]
    assert [step.max_scroll_attempts for step in result.sequence.steps] == [4, 4]


def test_build_slot_1_preset_chooser_avoids_reuse_until_pool_is_exhausted() -> None:
    presets = (
        BotActionPreset(id="preset-1", text="gm"),
        BotActionPreset(id="preset-2", text="wagmi"),
        BotActionPreset(id="preset-3", text="lfggg"),
    )
    chooser = build_slot_1_preset_chooser(choose_preset=lambda available: available[0])

    selected_ids = [chooser(presets).id for _ in range(4)]

    assert selected_ids[:3] == ["preset-1", "preset-2", "preset-3"]
    assert selected_ids[3] == "preset-1"
