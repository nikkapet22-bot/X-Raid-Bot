from __future__ import annotations

from pathlib import Path

from raidbot.desktop.automation.models import AutomationSequence, AutomationStep


def test_automation_step_keeps_search_and_click_settings() -> None:
    step = AutomationStep(
        name="open raid",
        template_path=Path("templates/open.png"),
        match_threshold=0.87,
        max_search_seconds=12,
        max_scroll_attempts=3,
        scroll_amount=640,
        max_click_attempts=5,
        post_click_settle_ms=250,
        click_offset_x=4,
        click_offset_y=-2,
    )

    assert step.name == "open raid"
    assert step.template_path == Path("templates/open.png")
    assert step.match_threshold == 0.87
    assert step.max_search_seconds == 12
    assert step.max_scroll_attempts == 3
    assert step.scroll_amount == 640
    assert step.max_click_attempts == 5
    assert step.post_click_settle_ms == 250
    assert step.click_offset_x == 4
    assert step.click_offset_y == -2
    assert step.template_missing is False


def test_automation_sequence_preserves_ordered_steps_and_target_window_rule() -> None:
    sequence = AutomationSequence(
        id="raid-open",
        name="Open raid",
        target_window_rule={"title_contains": "RaidBot"},
        steps=[
            AutomationStep(
                name="find button",
                template_path=Path("templates/find.png"),
                match_threshold=0.8,
                max_search_seconds=10,
                max_scroll_attempts=2,
                scroll_amount=500,
                max_click_attempts=4,
                post_click_settle_ms=150,
            ),
            AutomationStep(
                name="confirm",
                template_path=Path("templates/confirm.png"),
                match_threshold=0.85,
                max_search_seconds=8,
                max_scroll_attempts=1,
                scroll_amount=300,
                max_click_attempts=3,
                post_click_settle_ms=200,
            ),
        ],
    )

    assert sequence.id == "raid-open"
    assert sequence.name == "Open raid"
    assert sequence.target_window_rule == {"title_contains": "RaidBot"}
    assert [step.name for step in sequence.steps] == ["find button", "confirm"]
