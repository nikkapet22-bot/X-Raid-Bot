from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class AutomationStep:
    name: str
    template_path: Path
    match_threshold: float
    max_search_seconds: float
    max_scroll_attempts: int
    scroll_amount: int
    max_click_attempts: int
    post_click_settle_ms: int
    click_offset_x: int = 0
    click_offset_y: int = 0
    template_missing: bool = False
    pre_confirm_clicks: int = 1
    inter_click_delay_ms: int = 500
    preset_text: str | None = None
    preset_image_path: Path | None = None
    finish_template_path: Path | None = None
    finish_template_path_2: Path | None = None


@dataclass
class AutomationSequence:
    id: str
    name: str
    target_window_rule: str | None = None
    steps: list[AutomationStep] = field(default_factory=list)


@dataclass
class MatchResult:
    score: float
    top_left_x: int
    top_left_y: int
    width: int
    height: int

    @property
    def center_x(self) -> int:
        return self.top_left_x + (self.width // 2)

    @property
    def center_y(self) -> int:
        return self.top_left_y + (self.height // 2)
