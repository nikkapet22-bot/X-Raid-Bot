from __future__ import annotations

from PySide6.QtWidgets import QApplication

from raidbot.headless.actions import PlaywrightXActionExecutor
from raidbot.headless.config import HeadlessConfigStore
from raidbot.headless.listener import HeadlessRaidListenerAdapter
from raidbot.headless.runner import HeadlessRaidRunner
from raidbot.headless.session import PlaywrightSessionManager
from raidbot.headless.window import HeadlessWindow


class HeadlessApp:
    def __init__(self, config_store: HeadlessConfigStore | None = None) -> None:
        self.config_store = config_store or HeadlessConfigStore()
        self.shared_config = self.config_store.load_shared_config()
        self.settings = self.config_store.load_settings()
        self.window = HeadlessWindow()
        self.window.set_auth_state(
            PlaywrightSessionManager(
                user_data_dir=self.config_store.playwright_user_data_dir
            ).get_auth_state()
        )
        self.window.actionTogglesChanged.connect(self._save_action_toggles)
        self.window.bootstrapRequested.connect(self._bootstrap_login)
        self.window.startRequested.connect(self._start)
        self.window.stopRequested.connect(self._stop)
        self.session_manager = PlaywrightSessionManager(
            user_data_dir=self.config_store.playwright_user_data_dir
        )
        self.runner = HeadlessRaidRunner(
            session_manager=self.session_manager,
            action_executor=PlaywrightXActionExecutor(),
            enabled_actions=self.settings.enabled_actions,
        )
        self.listener = HeadlessRaidListenerAdapter(
            shared_config=self.shared_config,
            on_job=self._handle_job,
        )

    def _save_action_toggles(self, toggles) -> None:
        self.settings = self.settings.__class__(enabled_actions=toggles)
        self.config_store.save_settings(self.settings)
        self.runner = HeadlessRaidRunner(
            session_manager=self.session_manager,
            action_executor=PlaywrightXActionExecutor(),
            enabled_actions=toggles,
        )

    def _bootstrap_login(self) -> None:
        self.session_manager.launch_bootstrap_context()
        self.window.append_log("Bootstrap Login launched")

    def _start(self) -> None:
        self.window.append_log("Headless listener ready")

    def _stop(self) -> None:
        self.window.append_log("Headless listener stopped")

    def _handle_job(self, job) -> None:
        self.window.set_last_detected_raid(job.normalized_url)
        result = self.runner.run(job)
        self.window.set_last_result(result)
        self.window.append_log(f"{job.normalized_url}: {result.reason}")


def main() -> int:
    app = QApplication.instance() or QApplication([])
    headless_app = HeadlessApp()
    headless_app.window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
