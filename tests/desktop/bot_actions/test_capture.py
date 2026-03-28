from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRect
from PySide6.QtGui import QColor, QPixmap

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
    def __init__(self, geometry: QRect, name: str, color: QColor | None = None) -> None:
        self._geometry = geometry
        self.name = name
        self.color = color or QColor("black")

    def geometry(self) -> QRect:
        return QRect(self._geometry)

    def grabWindow(self, _window_id: int, x: int = 0, y: int = 0, width: int = -1, height: int = -1):
        pixmap = QPixmap(
            width if width >= 0 else self._geometry.width(),
            height if height >= 0 else self._geometry.height(),
        )
        pixmap.fill(self.color)
        return pixmap


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


def test_capture_virtual_desktop_snapshot_composes_screen_pixmaps(qtbot) -> None:
    from raidbot.desktop.bot_actions.capture import capture_virtual_desktop_snapshot

    left_screen = FakeScreen(QRect(0, 0, 40, 20), "left", QColor("red"))
    right_screen = FakeScreen(QRect(40, 0, 30, 20), "right", QColor("blue"))

    geometry, pixmap = capture_virtual_desktop_snapshot([left_screen, right_screen])

    image = pixmap.toImage()
    assert geometry == QRect(0, 0, 70, 20)
    assert image.pixelColor(10, 10) == QColor("red")
    assert image.pixelColor(50, 10) == QColor("blue")
