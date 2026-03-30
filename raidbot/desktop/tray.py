from __future__ import annotations

from typing import Any

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from raidbot.desktop.models import BotRuntimeState


_TOGGLE_PRESENTATION = {
    BotRuntimeState.setup_required.value: ("Setup required", False),
    BotRuntimeState.stopped.value: ("Start bot", True),
    BotRuntimeState.starting.value: ("Starting...", False),
    BotRuntimeState.running.value: ("Stop bot", True),
    BotRuntimeState.stopping.value: ("Stopping...", False),
    BotRuntimeState.error.value: ("Retry start", True),
}


class TrayController:
    def __init__(
        self,
        *,
        window,
        controller,
        icon: QIcon,
        tray_icon_factory=QSystemTrayIcon,
        menu_factory=QMenu,
        initial_bot_state: str = "stopped",
        quit_callback=None,
        parent=None,
    ) -> None:
        self.window = window
        self.controller = controller
        self.quit_callback = quit_callback
        self._bot_state = initial_bot_state

        self.tray = tray_icon_factory(icon, parent)
        self.menu = menu_factory()
        self.show_action = self.menu.addAction("Show", self.restore_window)
        self.toggle_action = self.menu.addAction(
            self._toggle_label_for_state(self._bot_state),
            self.toggle_bot,
        )
        self.quit_action = self.menu.addAction("Quit", self.quit)
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self._handle_activated)
        self.tray.show()

        if hasattr(self.controller, "botStateChanged"):
            self.controller.botStateChanged.connect(self.update_bot_state)

    def update_bot_state(self, state: str) -> None:
        self._bot_state = state
        self.toggle_action.setText(self._toggle_label_for_state(state))
        if hasattr(self.toggle_action, "setEnabled"):
            self.toggle_action.setEnabled(self._toggle_enabled_for_state(state))

    def toggle_bot(self) -> None:
        if not self._toggle_enabled_for_state(self._bot_state):
            return
        if self._bot_state == "running":
            self.controller.stop_bot()
            return
        self.controller.start_bot()

    def restore_window(self) -> None:
        if hasattr(self.window, "restore_from_tray"):
            self.window.restore_from_tray()
            return
        self.window.showNormal()
        self.window.raise_()
        self.window.activateWindow()

    def quit(self) -> None:
        if self.quit_callback is not None:
            self.quit_callback()
            return
        self.window.close()

    def _handle_activated(self, reason: Any) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.restore_window()

    def _toggle_label_for_state(self, state: str) -> str:
        return _TOGGLE_PRESENTATION.get(state, ("Start bot", True))[0]

    def _toggle_enabled_for_state(self, state: str) -> bool:
        return _TOGGLE_PRESENTATION.get(state, ("Start bot", True))[1]
