from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRect

from raidbot.desktop.models import BotActionSlotConfig


class FakeImage:
    def __init__(self) -> None:
        self.saved_paths: list[Path] = []
        self.save_result = True

    def save(self, path: str) -> None:
        saved_path = Path(path)
        if self.save_result:
            saved_path.write_bytes(b"capture")
        self.saved_paths.append(saved_path)
        return self.save_result


class FakeScreen:
    def __init__(self, geometry: QRect, name: str) -> None:
        self._geometry = geometry
        self.name = name

    def geometry(self) -> QRect:
        return QRect(self._geometry)


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


def test_capture_defaults_to_real_qt_snipping_overlay(tmp_path) -> None:
    from raidbot.desktop.bot_actions.capture import QtSnippingOverlay, SlotCaptureService

    service = SlotCaptureService(base_dir=tmp_path)

    assert isinstance(service.capture_overlay, QtSnippingOverlay)


def test_map_capture_rect_to_screen_uses_screen_local_coordinates() -> None:
    from raidbot.desktop.bot_actions.capture import map_capture_rect_to_screen

    left_screen = FakeScreen(QRect(-1920, 0, 1920, 1080), "left")
    primary_screen = FakeScreen(QRect(0, 0, 1920, 1080), "primary")

    screen, rect = map_capture_rect_to_screen(
        QRect(-1800, 100, 300, 200),
        [left_screen, primary_screen],
    )

    assert screen is left_screen
    assert rect == QRect(120, 100, 300, 200)


def test_map_capture_rect_to_screen_chooses_largest_intersection_deterministically() -> None:
    from raidbot.desktop.bot_actions.capture import map_capture_rect_to_screen

    left_screen = FakeScreen(QRect(-1920, 0, 1920, 1080), "left")
    primary_screen = FakeScreen(QRect(0, 0, 1920, 1080), "primary")

    screen, rect = map_capture_rect_to_screen(
        QRect(-100, 10, 400, 100),
        [left_screen, primary_screen],
    )

    assert screen is primary_screen
    assert rect == QRect(0, 10, 300, 100)


def test_capture_raises_when_image_save_fails(tmp_path) -> None:
    from raidbot.desktop.bot_actions.capture import SlotCaptureService

    fake_image = FakeImage()
    fake_image.save_result = False
    service = SlotCaptureService(base_dir=tmp_path, snip_image=lambda: fake_image)
    slot = BotActionSlotConfig(key="slot_1_r", label="R")

    try:
        service.capture_slot(slot)
    except OSError as exc:
        assert "slot_1_r.png" in str(exc)
    else:
        raise AssertionError("Expected image save failure to raise OSError.")
