from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from raidbot.desktop.models import BotActionSlotConfig


class _CallbackCaptureOverlay:
    def __init__(self, capture: Callable[[], Any | None]) -> None:
        self._capture = capture

    def capture(self) -> Any | None:
        return self._capture()


class SlotCaptureService:
    def __init__(
        self,
        *,
        base_dir: Path,
        capture_overlay: Any | None = None,
        snip_image: Callable[[], Any | None] | None = None,
    ) -> None:
        self.base_dir = Path(base_dir)
        self.capture_overlay = capture_overlay or _CallbackCaptureOverlay(
            snip_image or (lambda: None)
        )

    def capture_slot(
        self,
        slot: BotActionSlotConfig,
        existing_path: Path | None = None,
    ) -> Path | None:
        image = self.capture_overlay.capture()
        if image is None:
            return existing_path
        target_path = self.base_dir / "bot_actions" / f"{slot.key}.png"
        target_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(str(target_path))
        return target_path
