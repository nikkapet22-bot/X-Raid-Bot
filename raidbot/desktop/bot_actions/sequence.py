from __future__ import annotations

from dataclasses import dataclass
from random import choice
from collections.abc import Sequence

from raidbot.desktop.automation.models import AutomationSequence, AutomationStep
from raidbot.desktop.models import BotActionPreset, BotActionSlotConfig


BOT_ACTION_STEP_SEARCH_SECONDS = 8.0
SLOT_TEST_STEP_SEARCH_SECONDS = 1.0


@dataclass(frozen=True)
class BotActionBuildWarning:
    slot_index: int
    reason: str


@dataclass(frozen=True)
class BotActionSequenceBuildResult:
    sequence: AutomationSequence
    warnings: tuple[BotActionBuildWarning, ...] = ()


def _choose_slot_1_preset(
    slot: BotActionSlotConfig,
    *,
    choose_preset,
) -> BotActionPreset:
    presets = tuple(slot.presets)
    if not presets:
        raise ValueError("no_presets_configured")
    return choose_preset(presets)


def _build_slot_step(
    slot: BotActionSlotConfig,
    *,
    max_search_seconds: float,
    choose_preset=choice,
) -> AutomationStep:
    is_slot_3 = slot.key == "slot_3_r"
    slot_1_preset = None
    if slot.key == "slot_1_r":
        slot_1_preset = _choose_slot_1_preset(slot, choose_preset=choose_preset)
    return AutomationStep(
        name=slot.key,
        template_path=slot.template_path,
        match_threshold=0.9,
        max_search_seconds=max_search_seconds,
        max_scroll_attempts=0,
        scroll_amount=-120,
        max_click_attempts=2 if is_slot_3 else 1,
        post_click_settle_ms=250,
        pre_confirm_clicks=2 if is_slot_3 else 1,
        inter_click_delay_ms=500,
        preset_text=slot_1_preset.text if slot_1_preset is not None else None,
        preset_image_path=(
            slot_1_preset.image_path if slot_1_preset is not None else None
        ),
        finish_template_path=(
            slot.finish_template_path if slot_1_preset is not None else None
        ),
    )


def build_bot_action_sequence(
    slots: Sequence[BotActionSlotConfig],
    *,
    choose_preset=choice,
) -> BotActionSequenceBuildResult:
    warnings: list[BotActionBuildWarning] = []
    steps: list[AutomationStep] = []
    for slot_index, slot in enumerate(slots):
        if not slot.enabled or slot.template_path is None:
            continue
        if slot.key == "slot_1_r" and not slot.presets:
            warnings.append(
                BotActionBuildWarning(
                    slot_index=slot_index,
                    reason="no_presets_configured",
                )
            )
            continue
        steps.append(
            _build_slot_step(
                slot,
                max_search_seconds=BOT_ACTION_STEP_SEARCH_SECONDS,
                choose_preset=choose_preset,
            )
        )
    return BotActionSequenceBuildResult(
        sequence=AutomationSequence(
            id="bot-actions",
            name="Bot Actions",
            steps=steps,
        ),
        warnings=tuple(warnings),
    )


def build_slot_test_sequence(
    slot: BotActionSlotConfig,
    *,
    choose_preset=choice,
) -> AutomationSequence:
    return AutomationSequence(
        id=f"slot-test-{slot.key}",
        name=f"Test {slot.label}",
        steps=[
            _build_slot_step(
                slot,
                max_search_seconds=SLOT_TEST_STEP_SEARCH_SECONDS,
                choose_preset=choose_preset,
            )
        ],
    )
