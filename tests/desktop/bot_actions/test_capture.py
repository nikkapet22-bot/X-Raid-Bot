from __future__ import annotations

from pathlib import Path

from raidbot.desktop.models import BotActionSlotConfig


class FakeImage:
    def __init__(self) -> None:
        self.saved_paths: list[Path] = []

    def save(self, path: str) -> None:
        saved_path = Path(path)
        saved_path.write_bytes(b"capture")
        self.saved_paths.append(saved_path)


def test_capture_saves_slot_image_to_deterministic_path(tmp_path) -> None:
    from raidbot.desktop.bot_actions.capture import SlotCaptureService

    fake_image = FakeImage()
    service = SlotCaptureService(base_dir=tmp_path, snip_image=lambda: fake_image)
    slot = BotActionSlotConfig(key="slot_1_r", label="R")

    path = service.capture_slot(slot)

    assert path == tmp_path / "bot_actions" / "slot_1_r.png"
    assert path.name == "slot_1_r.png"
    assert fake_image.saved_paths == [path]
    assert path.exists() is True


def test_capture_cancel_keeps_existing_slot_image(tmp_path) -> None:
    from raidbot.desktop.bot_actions.capture import SlotCaptureService

    service = SlotCaptureService(base_dir=tmp_path, snip_image=lambda: None)
    slot = BotActionSlotConfig(key="slot_1_r", label="R")

    assert service.capture_slot(slot, existing_path=Path("existing.png")) == Path(
        "existing.png"
    )
