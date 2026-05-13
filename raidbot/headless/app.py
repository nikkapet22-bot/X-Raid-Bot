from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from raidbot.desktop.chrome_profiles import detect_chrome_environment
from raidbot.headless.actions import PlaywrightXActionExecutor
from raidbot.headless.config import HeadlessConfigStore
from raidbot.headless.listener import HeadlessRaidListenerAdapter
from raidbot.headless.models import HeadlessActionToggles, HeadlessAuthState, HeadlessRunResult
from raidbot.headless.runner import HeadlessRaidRunner
from raidbot.headless.runtime import HeadlessRuntimeController
from raidbot.headless.session import PlaywrightSessionManager
from raidbot.headless.window import HeadlessWindow


class _HeadlessUiBridge(QObject):
    authStateChanged = Signal(object)
    runningChanged = Signal(bool)
    lastDetectedChanged = Signal(object)
    resultChanged = Signal(object)
    logLineAdded = Signal(str)


class HeadlessApp:
    def __init__(self, config_store: HeadlessConfigStore | None = None) -> None:
        self.config_store = config_store or HeadlessConfigStore()
        self.shared_config = self.config_store.load_shared_config()
        self.settings = self.config_store.load_settings()
        self.window = HeadlessWindow()
        self._ui_bridge = _HeadlessUiBridge()

        self._apply_saved_action_toggles(self.settings.enabled_actions)
        self._load_available_profiles()
        self._wire_ui_bridge()

        self.session_manager = PlaywrightSessionManager(
            user_data_dir=self.config_store.playwright_user_data_dir,
            auth_state_path=self.config_store.auth_state_path,
        )
        self.runner = HeadlessRaidRunner(
            session_manager=self.session_manager,
            action_executor=PlaywrightXActionExecutor(),
            enabled_actions=self.settings.enabled_actions,
        )
        self.listener = HeadlessRaidListenerAdapter(
            shared_config=self.shared_config,
            on_job=lambda _job: None,
        )
        self.runtime = HeadlessRuntimeController(
            listener_adapter=self.listener,
            runner=self.runner,
            session_manager=self.session_manager,
            on_running_changed=self._ui_bridge.runningChanged.emit,
            on_auth_state=self._ui_bridge.authStateChanged.emit,
            on_log=self._ui_bridge.logLineAdded.emit,
            on_last_detected=self._ui_bridge.lastDetectedChanged.emit,
            on_result=self._ui_bridge.resultChanged.emit,
        )

        self.window.actionTogglesChanged.connect(self._save_action_toggles)
        self.window.profileSelectionChanged.connect(self._save_selected_profile_directory)
        self.window.bootstrapRequested.connect(self._bootstrap_login)
        self.window.startRequested.connect(self._start)
        self.window.stopRequested.connect(self._stop)
        self._ui_bridge.authStateChanged.emit(self.session_manager.get_auth_state())

    def _wire_ui_bridge(self) -> None:
        self._ui_bridge.authStateChanged.connect(self.window.set_auth_state)
        self._ui_bridge.runningChanged.connect(self.window.set_runtime_running)
        self._ui_bridge.lastDetectedChanged.connect(self.window.set_last_detected_raid)
        self._ui_bridge.resultChanged.connect(self.window.set_last_result)
        self._ui_bridge.logLineAdded.connect(self.window.append_log)

    def _apply_saved_action_toggles(self, toggles: HeadlessActionToggles) -> None:
        checkbox_states = (
            (self.window.reply_checkbox, toggles.reply),
            (self.window.like_checkbox, toggles.like),
            (self.window.repost_checkbox, toggles.repost),
            (self.window.bookmark_checkbox, toggles.bookmark),
        )
        for checkbox, checked in checkbox_states:
            was_blocked = checkbox.blockSignals(True)
            checkbox.setChecked(checked)
            checkbox.blockSignals(was_blocked)

    def _save_action_toggles(self, toggles: HeadlessActionToggles) -> None:
        self.settings = self.settings.__class__(
            enabled_actions=toggles,
            chrome_profile_directory=self.settings.chrome_profile_directory,
        )
        self.config_store.save_settings(self.settings)
        self.runner.set_enabled_actions(toggles)
        self.runtime.set_enabled_actions(toggles)
        self._ui_bridge.logLineAdded.emit("Enabled actions updated")

    def _save_selected_profile_directory(self, profile_directory: str) -> None:
        normalized = str(profile_directory).strip() or None
        self.settings = self.settings.__class__(
            enabled_actions=self.settings.enabled_actions,
            chrome_profile_directory=normalized,
        )
        self.config_store.save_settings(self.settings)

    def _bootstrap_login(self) -> None:
        profile_directory = self.window.selected_profile_directory()
        if not profile_directory:
            self._ui_bridge.logLineAdded.emit("Import X Auth failed: no Chrome profile selected")
            return
        try:
            auth_state = self.session_manager.import_auth_from_desktop_profile(
                profile_directory
            )
        except Exception as exc:
            self._ui_bridge.logLineAdded.emit(
                f"Import X Auth failed: {str(exc).strip() or 'import_x_auth_failed'}"
            )
            return
        self._ui_bridge.logLineAdded.emit("X auth imported")
        self._ui_bridge.authStateChanged.emit(auth_state)

    def _start(self) -> None:
        self.runtime.start()

    def _stop(self) -> None:
        self.runtime.stop()

    def shutdown(self) -> None:
        self.runtime.stop()

    def _load_available_profiles(self) -> None:
        try:
            chrome_environment = detect_chrome_environment()
        except Exception as exc:
            self.window.set_available_profiles([])
            self._ui_bridge.logLineAdded.emit(
                f"Chrome profiles unavailable: {str(exc).strip() or 'chrome_profiles_unavailable'}"
            )
            return

        self.window.set_available_profiles(chrome_environment.profiles)
        preferred_directory = (
            self.settings.chrome_profile_directory
            or self.shared_config.chrome_profile_directory
        )
        self.window.set_selected_profile_directory(preferred_directory)


def main() -> int:
    app = QApplication.instance() or QApplication([])
    headless_app = HeadlessApp()
    app.aboutToQuit.connect(headless_app.shutdown)
    headless_app.window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
