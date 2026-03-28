from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class AutomationStep:
    name: str
    template_path: Path
    match_threshold: float
    max_search_seconds: int
    max_scroll_attempts: int
    scroll_amount: int
    max_click_attempts: int
    post_click_settle_ms: int
    click_offset_x: int = 0
    click_offset_y: int = 0
    template_missing: bool = False


@dataclass
class AutomationSequence:
    id: str
    name: str
    target_window_rule: dict[str, Any] | None = None
    steps: list[AutomationStep] = field(default_factory=list)
