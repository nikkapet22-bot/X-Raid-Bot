from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtCore import QEventLoop, QRect, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QKeyEvent, QMouseEvent, QPainter
from PySide6.QtWidgets import QApplication, QRubberBand, QWidget

from raidbot.desktop.models import BotActionSlotConfig


class _CallbackCaptureOverlay:
    def __init__(self, capture: Callable[[], Any | None]) -> None:
        self._capture = capture

    def capture(self) -> Any | None:
        return self._capture()


class _SnippingOverlayWidget(QWidget):
    selectionFinished = Signal(object)

    def __init__(self) -> None:
        super().__init__(None)
        self._origin = None
        self._rubber_band = QRubberBand(QRubberBand.Shape.Rectangle, self)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setWindowState(Qt.WindowState.WindowFullScreen)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMouseTracking(True)
        self._set_virtual_geometry()

    def _set_virtual_geometry(self) -> None:
        screens = QGuiApplication.screens()
        if not screens:
            return
        geometry = screens[0].geometry()
        for screen in screens[1:]:
            geometry = geometry.united(screen.geometry())
        self.setGeometry(geometry)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 80))

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            self._finish(None)
            return
        self._origin = event.globalPosition().toPoint()
        local_origin = self.mapFromGlobal(self._origin)
        self._rubber_band.setGeometry(QRect(local_origin, local_origin))
        self._rubber_band.show()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._origin is None:
            return
        current = self.mapFromGlobal(event.globalPosition().toPoint())
        origin = self.mapFromGlobal(self._origin)
        self._rubber_band.setGeometry(QRect(origin, current).normalized())

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton or self._origin is None:
            self._finish(None)
            return
        end_point = event.globalPosition().toPoint()
        selection = QRect(self._origin, end_point).normalized()
        self._finish(selection if selection.width() > 1 and selection.height() > 1 else None)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self._finish(None)
            return
        super().keyPressEvent(event)

    def _finish(self, selection: QRect | None) -> None:
        self._rubber_band.hide()
        self.hide()
        self.selectionFinished.emit(selection)


class QtSnippingOverlay:
    def capture(self):
        app = QApplication.instance()
        if app is None:
            raise RuntimeError("A QApplication instance is required for slot capture.")

        overlay = _SnippingOverlayWidget()
        event_loop = QEventLoop()
        selection: QRect | None = None

        def complete(result: QRect | None) -> None:
            nonlocal selection
            selection = result
            event_loop.quit()

        overlay.selectionFinished.connect(complete)
        overlay.show()
        overlay.raise_()
        overlay.activateWindow()
        event_loop.exec()
        overlay.deleteLater()
        if selection is None:
            return None

        screen = QGuiApplication.screenAt(selection.center())
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        if screen is None:
            return None
        return screen.grabWindow(
            0,
            selection.x(),
            selection.y(),
            selection.width(),
            selection.height(),
        )


class SlotCaptureService:
    def __init__(
        self,
        *,
        base_dir: Path,
        capture_overlay: Any | None = None,
        snip_image: Callable[[], Any | None] | None = None,
    ) -> None:
        self.base_dir = Path(base_dir)
        if capture_overlay is not None:
            self.capture_overlay = capture_overlay
        elif snip_image is not None:
            self.capture_overlay = _CallbackCaptureOverlay(snip_image)
        else:
            self.capture_overlay = QtSnippingOverlay()

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
