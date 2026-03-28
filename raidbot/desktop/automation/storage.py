from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import AutomationSequence, AutomationStep

_SCHEMA_VERSION = 1


class AutomationStorage:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.sequences_path = base_dir / "automation_sequences.json"

    def load_sequences(self) -> list[AutomationSequence]:
        if not self.sequences_path.exists():
            return []
        data = json.loads(self.sequences_path.read_text(encoding="utf-8"))
        return self._sequences_from_data(data)

    def save_sequences(self, sequences: list[AutomationSequence]) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": _SCHEMA_VERSION,
            "sequences": [self._sequence_to_data(sequence) for sequence in sequences],
        }
        self.sequences_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def _sequences_from_data(self, data: dict[str, Any]) -> list[AutomationSequence]:
        sequences_data = data.get("sequences", [])
        return [self._sequence_from_data(item) for item in sequences_data]

    def _sequence_to_data(self, sequence: AutomationSequence) -> dict[str, Any]:
        return {
            "id": sequence.id,
            "name": sequence.name,
            "target_window_rule": sequence.target_window_rule,
            "steps": [self._step_to_data(step) for step in sequence.steps],
        }

    def _sequence_from_data(self, data: dict[str, Any]) -> AutomationSequence:
        return AutomationSequence(
            id=str(data["id"]),
            name=str(data["name"]),
            target_window_rule=data.get("target_window_rule"),
            steps=[
                self._step_from_data(item, schema_version=data.get("schema_version"))
                for item in data.get("steps", [])
            ],
        )

    def _step_to_data(self, step: AutomationStep) -> dict[str, Any]:
        return {
            "name": step.name,
            "template_path": str(step.template_path),
            "match_threshold": step.match_threshold,
            "max_search_seconds": step.max_search_seconds,
            "max_scroll_attempts": step.max_scroll_attempts,
            "scroll_amount": step.scroll_amount,
            "max_click_attempts": step.max_click_attempts,
            "post_click_settle_ms": step.post_click_settle_ms,
            "click_offset_x": step.click_offset_x,
            "click_offset_y": step.click_offset_y,
            "template_missing": step.template_missing,
        }

    def _step_from_data(self, data: dict[str, Any], schema_version: Any) -> AutomationStep:
        template_path = Path(data["template_path"])
        template_missing = bool(data.get("template_missing", False))
        if schema_version is None and "template_missing" not in data:
            template_missing = not template_path.exists()
        return AutomationStep(
            name=str(data["name"]),
            template_path=template_path,
            match_threshold=float(data["match_threshold"]),
            max_search_seconds=int(data["max_search_seconds"]),
            max_scroll_attempts=int(data["max_scroll_attempts"]),
            scroll_amount=int(data["scroll_amount"]),
            max_click_attempts=int(data["max_click_attempts"]),
            post_click_settle_ms=int(data["post_click_settle_ms"]),
            click_offset_x=int(data.get("click_offset_x", 0)),
            click_offset_y=int(data.get("click_offset_y", 0)),
            template_missing=template_missing,
        )
