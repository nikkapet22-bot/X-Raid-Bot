from __future__ import annotations

import json
from pathlib import Path

from raidbot.desktop.automation.models import AutomationSequence, AutomationStep
from raidbot.desktop.automation.storage import AutomationStorage
from raidbot.desktop.storage import DesktopStorage


def test_automation_storage_uses_desktop_base_dir(tmp_path) -> None:
    storage = DesktopStorage(tmp_path)

    assert storage.automation_sequences_path == tmp_path / "automation_sequences.json"


def test_automation_storage_returns_empty_list_when_missing(tmp_path) -> None:
    storage = AutomationStorage(tmp_path)

    assert storage.load_sequences() == []


def test_automation_sequence_round_trip(tmp_path) -> None:
    storage = AutomationStorage(tmp_path)
    template_path = tmp_path / "templates" / "find.png"
    template_path.parent.mkdir(parents=True)
    template_path.write_bytes(b"template")
    sequences = [
        AutomationSequence(
            id="sequence-1",
            name="Open raid",
            target_window_rule="RaidBot",
            steps=[
                AutomationStep(
                    name="find raid",
                    template_path=template_path,
                    match_threshold=0.9,
                    max_search_seconds=15.5,
                    max_scroll_attempts=2,
                    scroll_amount=600,
                    max_click_attempts=4,
                    post_click_settle_ms=300,
                    click_offset_x=3,
                    click_offset_y=-1,
                )
            ],
        )
    ]

    storage.save_sequences(sequences)

    loaded = storage.load_sequences()

    assert loaded == sequences
    assert storage.sequences_path.exists()
    assert json.loads(storage.sequences_path.read_text(encoding="utf-8"))["schema_version"] == 1


def test_automation_storage_marks_missing_templates_for_legacy_payload(tmp_path) -> None:
    storage = AutomationStorage(tmp_path)
    legacy_payload = {
        "sequences": [
            {
                "id": "legacy-sequence",
                "name": "Legacy sequence",
                "steps": [
                    {
                        "name": "find button",
                        "template_path": "templates/missing.png",
                        "match_threshold": 0.75,
                        "max_search_seconds": 20.0,
                        "max_scroll_attempts": 1,
                        "scroll_amount": 400,
                        "max_click_attempts": 2,
                        "post_click_settle_ms": 100,
                    }
                ],
            }
        ]
    }
    storage.sequences_path.write_text(json.dumps(legacy_payload), encoding="utf-8")

    loaded = storage.load_sequences()

    assert loaded[0].steps[0].template_missing is True
    assert loaded[0].steps[0].template_path == Path("templates/missing.png")


def test_automation_storage_treats_schema_versioned_payload_as_current_schema(tmp_path) -> None:
    storage = AutomationStorage(tmp_path)
    template_path = tmp_path / "templates" / "present.png"
    template_path.parent.mkdir(parents=True)
    template_path.write_bytes(b"template")
    current_payload = {
        "schema_version": 1,
        "sequences": [
            {
                "id": "current-sequence",
                "name": "Current sequence",
                "steps": [
                    {
                        "name": "find button",
                        "template_path": str(template_path),
                        "match_threshold": 0.75,
                        "max_search_seconds": 20.0,
                        "max_scroll_attempts": 1,
                        "scroll_amount": 400,
                        "max_click_attempts": 2,
                        "post_click_settle_ms": 100,
                        "template_missing": True,
                    }
                ],
            }
        ],
    }
    storage.sequences_path.write_text(json.dumps(current_payload), encoding="utf-8")

    loaded = storage.load_sequences()

    assert loaded[0].steps[0].template_missing is True
    assert loaded[0].steps[0].template_path == template_path


def test_automation_storage_marks_deleted_templates_as_missing_for_current_schema(tmp_path) -> None:
    storage = AutomationStorage(tmp_path)
    template_path = tmp_path / "templates" / "ephemeral.png"
    template_path.parent.mkdir(parents=True)
    template_path.write_bytes(b"template")
    sequences = [
        AutomationSequence(
            id="sequence-1",
            name="Open raid",
            steps=[
                AutomationStep(
                    name="find raid",
                    template_path=template_path,
                    match_threshold=0.9,
                    max_search_seconds=15.5,
                    max_scroll_attempts=2,
                    scroll_amount=600,
                    max_click_attempts=4,
                    post_click_settle_ms=300,
                )
            ],
        )
    ]

    storage.save_sequences(sequences)
    template_path.unlink()

    loaded = storage.load_sequences()

    assert loaded[0].steps[0].template_missing is True
    assert loaded[0].steps[0].template_path == template_path


def test_automation_storage_normalizes_structured_target_window_rule_to_title_substring(tmp_path) -> None:
    storage = AutomationStorage(tmp_path)
    payload = {
        "schema_version": 1,
        "sequences": [
            {
                "id": "structured-rule-sequence",
                "name": "Structured rule",
                "target_window_rule": {"title_contains": "RaidBot"},
                "steps": [],
            }
        ],
    }
    storage.sequences_path.write_text(json.dumps(payload), encoding="utf-8")

    loaded = storage.load_sequences()

    assert loaded[0].target_window_rule == "RaidBot"
