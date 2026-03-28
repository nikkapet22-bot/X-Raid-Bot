from __future__ import annotations

from collections.abc import Sequence

from raidbot.desktop.automation.models import AutomationSequence, AutomationStep
from raidbot.desktop.models import BotActionSlotConfig


def build_bot_action_sequence(slots: Sequence[BotActionSlotConfig]) -> AutomationSequence:
    return AutomationSequence(
        id="bot-actions",
        name="Bot Actions",
        steps=[
            AutomationStep(
                name=slot.key,
                template_path=slot.template_path,
                match_threshold=0.9,
                max_search_seconds=1.0,
                max_scroll_attempts=0,
                scroll_amount=-120,
                max_click_attempts=1,
                post_click_settle_ms=250,
            )
            for slot in slots
            if slot.enabled and slot.template_path is not None
        ],
    )
