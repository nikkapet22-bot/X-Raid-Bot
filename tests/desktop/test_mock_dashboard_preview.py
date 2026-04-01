from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from PySide6.QtWidgets import QWidget

from raidbot.desktop.models import DesktopAppState


def _load_preview_module():
    script_path = Path("scripts/mock_dashboard_preview.py")
    if not script_path.exists():
        raise FileNotFoundError(script_path)
    spec = importlib.util.spec_from_file_location(
        "mock_dashboard_preview",
        script_path,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("scenario", ["steady-4p", "burst-4p", "mixed-failures"])
def test_mock_dashboard_preview_scenarios_build_dashboard_state(scenario) -> None:
    module = _load_preview_module()

    state = module.build_scenario_state(scenario)

    assert isinstance(state, DesktopAppState)
    assert state.successful_profile_runs
    assert state.activity
    now = module.datetime.now()
    assert all(run.timestamp <= now for run in state.successful_profile_runs)


def test_mock_dashboard_preview_seed_preview_appdata_writes_temp_state(tmp_path) -> None:
    module = _load_preview_module()

    storage = module.seed_preview_appdata(tmp_path / "AppData", "steady-4p")

    assert storage.base_dir == tmp_path / "AppData" / "RaidBot"
    assert storage.config_path.exists()
    assert storage.state_path.exists()


def test_mock_dashboard_preview_build_preview_window_labels_mock_scenario(tmp_path) -> None:
    module = _load_preview_module()
    storage = module.seed_preview_appdata(tmp_path / "AppData", "burst-4p")
    created: dict[str, object] = {}

    class FakeWindow:
        def __init__(self, *, controller, storage, tray_controller_factory) -> None:
            created["controller"] = controller
            created["storage"] = storage
            created["tray_controller_factory"] = tray_controller_factory
            self.title = ""
            self.shown = False

        def setWindowTitle(self, value: str) -> None:
            self.title = value

        def show(self) -> None:
            self.shown = True

    original_main_window = module.MainWindow
    module.MainWindow = FakeWindow
    try:
        window = module.build_preview_window(
            scenario="burst-4p",
            storage=storage,
        )
    finally:
        module.MainWindow = original_main_window

    assert created["storage"] is storage
    assert created["controller"].config == storage.load_config()
    assert callable(created["tray_controller_factory"])
    assert window.title.endswith("MOCK - burst-4p")
    assert window.shown is True


def test_mock_dashboard_preview_builds_real_main_window(qtbot, tmp_path) -> None:
    module = _load_preview_module()
    storage = module.seed_preview_appdata(tmp_path / "AppData", "burst-4p")

    window = module.build_preview_window(
        scenario="burst-4p",
        storage=storage,
    )
    qtbot.addWidget(window)

    assert isinstance(window, QWidget)
    assert window.windowTitle().endswith("MOCK - burst-4p")
    assert window.raid_activity_chart._series


def test_mock_dashboard_preview_launch_application_uses_smoothed_rate_mode(tmp_path, monkeypatch) -> None:
    module = _load_preview_module()
    launched: dict[str, object] = {}

    class FakeApp:
        def __init__(self, argv) -> None:
            launched["argv"] = argv

        def setApplicationName(self, value: str) -> None:
            launched["app_name"] = value

        def setApplicationDisplayName(self, value: str) -> None:
            launched["display_name"] = value

        def setStyleSheet(self, value: str) -> None:
            launched["stylesheet"] = value

        def exec(self) -> int:
            launched["executed"] = True
            return 0

    def fake_build_preview_window(*, scenario, storage):
        launched["storage"] = storage
        launched["scenario"] = scenario
        launched["title"] = f"fake::{scenario}"
        return object()

    monkeypatch.delenv("RAIDBOT_CHART_MODE", raising=False)
    monkeypatch.setattr(module, "build_preview_window", fake_build_preview_window)

    exit_code = module.launch_preview_application(
        scenario="steady-4p",
        appdata_root=tmp_path / "AppData",
        app_factory=FakeApp,
    )

    assert exit_code == 0
    assert launched["executed"] is True
    assert launched["scenario"] == "steady-4p"
    assert "MOCK" in launched["app_name"]
    assert module.os.environ["RAIDBOT_CHART_MODE"] == "smoothed_rate"
    assert launched["storage"] is not None
    assert hasattr(module, "build_preview_window")


def test_mock_dashboard_preview_launch_application_retains_preview_window(
    tmp_path, monkeypatch
) -> None:
    module = _load_preview_module()
    retained: dict[str, object] = {}

    class FakeApp:
        def __init__(self, argv) -> None:
            retained["app"] = self

        def setApplicationName(self, value: str) -> None:
            pass

        def setApplicationDisplayName(self, value: str) -> None:
            pass

        def setStyleSheet(self, value: str) -> None:
            pass

        def exec(self) -> int:
            return 0

    sentinel_window = object()

    def fake_build_preview_window(*, scenario, storage):
        return sentinel_window

    monkeypatch.setattr(module, "build_preview_window", fake_build_preview_window)

    exit_code = module.launch_preview_application(
        scenario="steady-4p",
        appdata_root=tmp_path / "AppData",
        app_factory=FakeApp,
    )

    assert exit_code == 0
    assert retained["app"]._raidbot_mock_preview_window is sentinel_window


def test_mock_dashboard_preview_cli_help_lists_supported_scenarios() -> None:
    module = _load_preview_module()

    help_text = module.build_parser().format_help()

    assert "steady-4p" in help_text
    assert "burst-4p" in help_text
    assert "mixed-failures" in help_text


def test_mock_dashboard_preview_cli_defaults_cleanly(tmp_path, monkeypatch) -> None:
    module = _load_preview_module()
    launched: dict[str, object] = {}

    class FakeTemporaryDirectory:
        def __init__(self, prefix: str) -> None:
            self.path = tmp_path / "preview-root"

        def __enter__(self) -> str:
            self.path.mkdir(parents=True, exist_ok=True)
            return str(self.path)

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

    def fake_launch_preview_application(**kwargs):
        launched.update(kwargs)
        return 0

    monkeypatch.setattr(module.tempfile, "TemporaryDirectory", FakeTemporaryDirectory)
    monkeypatch.setattr(module, "launch_preview_application", fake_launch_preview_application)

    exit_code = module.main([])

    assert exit_code == 0
    assert launched["scenario"] == "steady-4p"
    assert launched["appdata_root"] == tmp_path / "preview-root" / "AppData"
