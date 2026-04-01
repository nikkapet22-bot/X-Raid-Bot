from __future__ import annotations

from dataclasses import dataclass
from random import choice
from collections.abc import Sequence

from raidbot.desktop.automation.models import AutomationSequence, AutomationStep
from raidbot.desktop.models import BotActionPreset, BotActionSlotConfig


BOT_ACTION_STEP_SEARCH_SECONDS = 2.0
SLOT_TEST_STEP_SEARCH_SECONDS = 1.0
BOT_ACTION_MATCH_THRESHOLD = 0.9
BOT_ACTION_SLOT_SCROLL_ATTEMPTS = 4
BOT_ACTION_SCROLL_AMOUNT = -360


@dataclass(frozen=True)
class BotActionBuildWarning:
    slot_index: int
    reason: str


@dataclass(frozen=True)
class BotActionSequenceBuildResult:
    sequence: AutomationSequence
    warnings: tuple[BotActionBuildWarning, ...] = ()


def build_slot_1_preset_chooser(
    *,
    choose_preset=choice,
):
    used_preset_ids: set[str] = set()

    def choose_without_reuse(presets: Sequence[BotActionPreset]) -> BotActionPreset:
        if len(presets) <= 1:
            selected = choose_preset(presets)
            used_preset_ids.add(selected.id)
            return selected

        available_presets = tuple(
            preset for preset in presets if preset.id not in used_preset_ids
        )
        if not available_presets:
            used_preset_ids.clear()
            available_presets = tuple(presets)

        selected = choose_preset(available_presets)
        used_preset_ids.add(selected.id)
        return selected

    return choose_without_reuse


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
    slot_1_finish_delay_seconds: int = 2,
    choose_preset=choice,
    allow_scroll_retry: bool = False,
) -> AutomationStep:
    is_slot_3 = slot.key == "slot_3_r"
    slot_1_preset = None
    if slot.key == "slot_1_r":
        slot_1_preset = _choose_slot_1_preset(slot, choose_preset=choose_preset)
    return AutomationStep(
        name=slot.key,
        template_path=slot.template_path,
        match_threshold=BOT_ACTION_MATCH_THRESHOLD,
        max_search_seconds=max_search_seconds,
        max_scroll_attempts=(
            BOT_ACTION_SLOT_SCROLL_ATTEMPTS if allow_scroll_retry else 0
        ),
        scroll_amount=BOT_ACTION_SCROLL_AMOUNT,
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
        finish_delay_seconds=(
            float(slot_1_finish_delay_seconds)
            if slot_1_preset is not None
            else None
        ),
    )


def build_bot_action_sequence(
    slots: Sequence[BotActionSlotConfig],
    *,
    slot_1_finish_delay_seconds: int = 2,
    choose_preset=choice,
) -> BotActionSequenceBuildResult:
    warnings: list[BotActionBuildWarning] = []
    enabled_slots: list[tuple[int, BotActionSlotConfig]] = []
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
        enabled_slots.append((slot_index, slot))

    ordered_slots = [
        *(
            (slot_index, slot)
            for slot_index, slot in enabled_slots
            if slot.key != "slot_1_r"
        ),
        *(
            (slot_index, slot)
            for slot_index, slot in enabled_slots
            if slot.key == "slot_1_r"
        ),
    ]

    steps: list[AutomationStep] = []
    for _slot_index, slot in ordered_slots:
        steps.append(
            _build_slot_step(
                slot,
                max_search_seconds=BOT_ACTION_STEP_SEARCH_SECONDS,
                slot_1_finish_delay_seconds=slot_1_finish_delay_seconds,
                choose_preset=choose_preset,
                allow_scroll_retry=True,
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
    slot_1_finish_delay_seconds: int = 2,
    choose_preset=choice,
) -> AutomationSequence:
    return AutomationSequence(
        id=f"slot-test-{slot.key}",
        name=f"Test {slot.label}",
        steps=[
            _build_slot_step(
                slot,
                max_search_seconds=SLOT_TEST_STEP_SEARCH_SECONDS,
                slot_1_finish_delay_seconds=slot_1_finish_delay_seconds,
                choose_preset=choose_preset,
                allow_scroll_retry=True,
            )
        ],
    )
