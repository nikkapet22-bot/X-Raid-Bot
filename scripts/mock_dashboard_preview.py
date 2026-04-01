from __future__ import annotations

import argparse
import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from raidbot.desktop.branding import APP_NAME
from raidbot.desktop.main_window import MainWindow
from raidbot.desktop.models import (
    ActivityEntry,
    BotRuntimeState,
    DesktopAppConfig,
    DesktopAppState,
    RaidProfileConfig,
    RaidProfileState,
    SuccessfulProfileRun,
    TelegramConnectionState,
)
from raidbot.desktop.storage import DesktopStorage
from raidbot.desktop.theme import build_application_stylesheet


PROFILE_DIRECTORIES = ("Default", "test1", "test2", "test3")


def _build_preview_config(appdata_root: Path) -> DesktopAppConfig:
    return DesktopAppConfig(
        telegram_api_id=1,
        telegram_api_hash="preview-hash",
        telegram_session_path=appdata_root / "RaidBot" / "raidbot.session",
        telegram_phone_number=None,
        whitelisted_chat_ids=[1],
        allowed_sender_ids=[1],
        allowed_sender_entries=("@raidar",),
        chrome_profile_directory="Default",
        raid_profiles=tuple(
            RaidProfileConfig(profile_directory=directory, label=directory)
            for directory in PROFILE_DIRECTORIES
        ),
    )


def _hour_series(
    now: datetime,
    counts: list[int],
    *,
    duration_seconds: float,
) -> list[SuccessfulProfileRun]:
    start_hour = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=23)
    runs: list[SuccessfulProfileRun] = []
    for hour_index, count in enumerate(counts):
        hour_start = start_hour + timedelta(hours=hour_index)
        is_current_hour = hour_start == now.replace(minute=0, second=0, microsecond=0)
        available_seconds = max(
            1,
            int((now - hour_start).total_seconds()),
        ) if is_current_hour else 3599
        for run_index in range(count):
            offset_seconds = min(
                available_seconds,
                15 + (run_index * max(1, available_seconds // max(count, 1))),
            )
            minute, second = divmod(offset_seconds, 60)
            minute = min(59, minute)
            runs.append(
                SuccessfulProfileRun(
                    timestamp=hour_start + timedelta(minutes=minute, seconds=second),
                    duration_seconds=duration_seconds + float(run_index % 3),
                )
            )
    return runs


def _activity_from_runs(
    runs: list[SuccessfulProfileRun],
    *,
    include_failure: bool = False,
) -> list[ActivityEntry]:
    recent_runs = sorted(runs, key=lambda entry: entry.timestamp)[-6:]
    activity: list[ActivityEntry] = []
    for index, run in enumerate(recent_runs):
        profile_directory = PROFILE_DIRECTORIES[index % len(PROFILE_DIRECTORIES)]
        url = f"https://x.com/i/status/{930000000000000000 + index}"
        started_at = run.timestamp - timedelta(seconds=int(run.duration_seconds or 3))
        activity.extend(
            [
                ActivityEntry(
                    timestamp=started_at,
                    action="automation_started",
                    url=url,
                    reason="automation_started",
                    profile_directory=profile_directory,
                ),
                ActivityEntry(
                    timestamp=run.timestamp,
                    action="automation_succeeded",
                    url=url,
                    reason="automation_succeeded",
                    profile_directory=profile_directory,
                ),
                ActivityEntry(
                    timestamp=run.timestamp,
                    action="session_closed",
                    url=url,
                    reason="automation_succeeded",
                    profile_directory=profile_directory,
                ),
            ]
        )
    if include_failure and runs:
        activity.insert(
            0,
            ActivityEntry(
                timestamp=runs[-1].timestamp - timedelta(minutes=2),
                action="automation_failed",
                url="https://x.com/i/status/999999999999",
                reason="window_not_focusable",
                profile_directory="test3",
            ),
        )
    return activity


def _profile_states(*, mixed_failures: bool = False) -> tuple[RaidProfileState, ...]:
    states = []
    for directory in PROFILE_DIRECTORIES:
        if mixed_failures and directory in {"test2", "test3"}:
            states.append(
                RaidProfileState(
                    profile_directory=directory,
                    label=directory,
                    status="red",
                    last_error="window_not_focusable",
                )
            )
            continue
        states.append(
            RaidProfileState(
                profile_directory=directory,
                label=directory,
                status="green",
                last_error=None,
            )
        )
    return tuple(states)


def _build_steady_state(now: datetime) -> DesktopAppState:
    runs = _hour_series(now, [0] * 8 + [4] * 16, duration_seconds=3.0)
    return DesktopAppState(
        bot_state=BotRuntimeState.running,
        connection_state=TelegramConnectionState.connected,
        raids_detected=16,
        raids_opened=16,
        raids_completed=16,
        raids_failed=1,
        last_successful_raid_open_at=runs[-1].timestamp.isoformat(),
        successful_profile_runs=runs,
        activity=_activity_from_runs(runs),
        raid_profile_states=_profile_states(),
    )


def _build_burst_state(now: datetime) -> DesktopAppState:
    runs = _hour_series(
        now,
        [0, 0, 0, 0, 12, 0, 0, 16, 0, 0, 8, 0, 0, 0, 20, 0, 0, 12, 0, 0, 0, 16, 0, 8],
        duration_seconds=4.0,
    )
    return DesktopAppState(
        bot_state=BotRuntimeState.running,
        connection_state=TelegramConnectionState.connected,
        raids_detected=23,
        raids_opened=23,
        raids_completed=23,
        raids_failed=2,
        last_successful_raid_open_at=runs[-1].timestamp.isoformat(),
        successful_profile_runs=runs,
        activity=_activity_from_runs(runs),
        raid_profile_states=_profile_states(),
    )


def _build_mixed_failure_state(now: datetime) -> DesktopAppState:
    runs = _hour_series(
        now,
        [0, 0, 4, 2, 0, 4, 0, 2, 4, 0, 2, 0, 4, 2, 0, 4, 0, 2, 4, 0, 2, 0, 4, 2],
        duration_seconds=5.0,
    )
    return DesktopAppState(
        bot_state=BotRuntimeState.running,
        connection_state=TelegramConnectionState.connected,
        raids_detected=18,
        raids_opened=18,
        raids_completed=12,
        raids_failed=6,
        last_successful_raid_open_at=runs[-1].timestamp.isoformat(),
        successful_profile_runs=runs,
        activity=_activity_from_runs(runs, include_failure=True),
        raid_profile_states=_profile_states(mixed_failures=True),
        last_error="window_not_focusable",
    )


SCENARIOS = {
    "steady-4p": _build_steady_state,
    "burst-4p": _build_burst_state,
    "mixed-failures": _build_mixed_failure_state,
}


class MockController(QObject):
    botStateChanged = Signal(str)
    connectionStateChanged = Signal(str)
    statsChanged = Signal(object)
    activityAdded = Signal(object)
    errorRaised = Signal(str)
    configChanged = Signal(object)
    automationQueueStateChanged = Signal(str)
    botActionRunEvent = Signal(object)

    def __init__(self, config: DesktopAppConfig) -> None:
        super().__init__()
        self.config = config

    def start_bot(self) -> None:
        return None

    def stop_bot(self) -> None:
        return None

    def stop_bot_and_wait(self) -> bool:
        return True

    def is_bot_active(self) -> bool:
        return False

    def apply_config(self, config: DesktopAppConfig) -> None:
        self.config = config
        self.config_changed.emit(config)

    def add_raid_profile(self, profile_directory: str, label: str) -> None:
        return None

    def remove_raid_profile(self, profile_directory: str) -> None:
        return None

    def move_raid_profile(self, profile_directory: str, direction: str) -> None:
        return None

    def reauthorize_session(self) -> None:
        return None

    def reset_dashboard_metric(self, metric_key: str) -> None:
        return None

    def request_detected_chats(self):
        return []

    def request_chrome_profiles(self):
        return []

    def request_bot_action_presets(self):
        return []

    def set_auto_run_settle_ms(self, settle_ms: int) -> None:
        return None

    def set_bot_action_slot_enabled(self, slot_index: int, enabled: bool) -> None:
        return None

    def test_bot_action_slot(self, slot_index: int) -> None:
        return None

    def set_bot_action_slot_template_path(
        self, slot_index: int, template_path: Path | None
    ) -> None:
        return None

    def set_page_ready_template_path(self, template_path: Path | None) -> None:
        return None

    def set_bot_action_slot_1_presets(self, presets) -> None:
        return None

    def restart_raid_profile(self, profile_directory: str) -> None:
        return None

    def set_raid_profile_raid_on_restart(
        self, profile_directory: str, enabled: bool
    ) -> None:
        return None


def build_scenario_state(
    scenario: str,
    *,
    now: datetime | None = None,
) -> DesktopAppState:
    if scenario not in SCENARIOS:
        raise ValueError(f"Unsupported preview scenario: {scenario}")
    return SCENARIOS[scenario](now or datetime.now().replace(microsecond=0))


def seed_preview_appdata(
    appdata_root: Path,
    scenario: str,
    *,
    now: datetime | None = None,
) -> DesktopStorage:
    storage = DesktopStorage(appdata_root / "RaidBot")
    storage.save_config(_build_preview_config(appdata_root))
    storage.save_state(build_scenario_state(scenario, now=now))
    return storage


def build_preview_window(
    *,
    scenario: str,
    storage: DesktopStorage,
):
    window = MainWindow(
        controller=MockController(storage.load_config()),
        storage=storage,
        tray_controller_factory=lambda *args, **kwargs: None,
    )
    if hasattr(window, "setWindowTitle"):
        window.setWindowTitle(f"{APP_NAME} MOCK - {scenario}")
    if hasattr(window, "show"):
        window.show()
    return window


def launch_preview_application(
    *,
    scenario: str,
    appdata_root: Path,
    app_factory=QApplication,
    now: datetime | None = None,
) -> int:
    os.environ["RAIDBOT_CHART_MODE"] = "smoothed_rate"
    storage = seed_preview_appdata(appdata_root, scenario, now=now)
    app = app_factory(sys.argv[:1])
    if hasattr(app, "setApplicationName"):
        app.setApplicationName(f"{APP_NAME} MOCK")
    if hasattr(app, "setApplicationDisplayName"):
        app.setApplicationDisplayName(f"{APP_NAME} MOCK")
    if hasattr(app, "setStyleSheet"):
        app.setStyleSheet(build_application_stylesheet())
    window = build_preview_window(scenario=scenario, storage=storage)
    if app is not None:
        app._raidbot_mock_preview_window = window
    return int(app.exec())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Launch the real desktop UI with disposable fake dashboard data.",
    )
    parser.add_argument(
        "--scenario",
        choices=sorted(SCENARIOS),
        default="steady-4p",
        help="Preview data scenario to seed before launching the app.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    with tempfile.TemporaryDirectory(prefix="raidbot-dashboard-preview-") as temp_dir:
        preview_root = Path(temp_dir)
        appdata_root = preview_root / "AppData"
        appdata_root.mkdir(parents=True, exist_ok=True)
        return launch_preview_application(
            scenario=args.scenario,
            appdata_root=appdata_root,
        )


if __name__ == "__main__":
    raise SystemExit(main())
