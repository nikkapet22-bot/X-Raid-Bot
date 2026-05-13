from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QVariantAnimation
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QPushButton


class AttentionPulseButton(QPushButton):
    def __init__(self, text: str = "", *, parent=None) -> None:
        super().__init__(text, parent)
        self.setProperty("attentionPulseButton", "true")
        self._allow_pulse = True
        self._busy = False
        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setOffset(0, 0)
        self._shadow.setBlurRadius(0)
        self._shadow.setColor(QColor(107, 163, 249, 0))
        self.setGraphicsEffect(self._shadow)

        self._pulse_animation = QVariantAnimation(self)
        self._pulse_animation.setStartValue(0.0)
        self._pulse_animation.setEndValue(1.0)
        self._pulse_animation.setDuration(240)
        self._pulse_animation.setLoopCount(1)
        self._pulse_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._pulse_animation.valueChanged.connect(self._handle_pulse_value_changed)
        self.pressed.connect(self._play_click_animation)

    def pulse_enabled(self) -> bool:
        return self._allow_pulse and self.isEnabled() and not self._busy

    def set_pulse_enabled(self, enabled: bool) -> None:
        self._allow_pulse = bool(enabled)
        self._sync_animation_state()

    def set_busy(self, busy: bool) -> None:
        self._busy = bool(busy)
        self._sync_animation_state()

    def setEnabled(self, enabled: bool) -> None:  # noqa: N802
        super().setEnabled(enabled)
        self._sync_animation_state()

    def _handle_pulse_value_changed(self, value) -> None:
        progress = max(0.0, min(float(value), 1.0))
        flash_level = 1.0 - abs((progress * 2.0) - 1.0)
        alpha = int(185 * flash_level)
        blur = 10.0 + (20.0 * flash_level)
        self._shadow.setColor(QColor(107, 163, 249, alpha))
        self._shadow.setBlurRadius(blur)

    def _play_click_animation(self) -> None:
        if not self.pulse_enabled():
            return
        self._pulse_animation.stop()
        self._pulse_animation.setCurrentTime(0)
        self._pulse_animation.start()

    def _sync_animation_state(self) -> None:
        if self.pulse_enabled():
            return
        if self._pulse_animation.state() == QVariantAnimation.State.Running:
            self._pulse_animation.stop()
        self._shadow.setBlurRadius(0)
        self._shadow.setColor(QColor(107, 163, 249, 0))
