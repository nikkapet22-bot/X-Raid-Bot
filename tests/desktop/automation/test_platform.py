from __future__ import annotations


def test_automation_runtime_available_reports_missing_optional_dependency(monkeypatch) -> None:
    from raidbot.desktop.automation.platform import automation_runtime_available

    def fake_import_module(name: str):
        if name == "cv2":
            raise ModuleNotFoundError("No module named 'cv2'")
        raise AssertionError(f"unexpected import: {name}")

    monkeypatch.setattr(
        "raidbot.desktop.automation.platform.importlib.import_module",
        fake_import_module,
    )
    monkeypatch.setattr("raidbot.desktop.automation.platform.sys.platform", "win32")

    available, reason = automation_runtime_available()

    assert available is False
    assert reason == "No module named 'cv2'"


def test_automation_runtime_available_returns_windows_only_on_non_windows(monkeypatch) -> None:
    from raidbot.desktop.automation.platform import automation_runtime_available

    called = False

    def fail_import(_name: str):
        nonlocal called
        called = True
        raise AssertionError("imports should not be probed on non-Windows")

    monkeypatch.setattr(
        "raidbot.desktop.automation.platform.importlib.import_module",
        fail_import,
    )
    monkeypatch.setattr("raidbot.desktop.automation.platform.sys.platform", "linux")

    available, reason = automation_runtime_available()

    assert available is False
    assert reason == "Windows only"
    assert called is False


def test_automation_runtime_available_returns_true_on_windows_when_dependencies_exist(
    monkeypatch,
) -> None:
    from raidbot.desktop.automation.platform import automation_runtime_available

    monkeypatch.setattr(
        "raidbot.desktop.automation.platform.importlib.import_module",
        lambda _name: None,
    )
    monkeypatch.setattr("raidbot.desktop.automation.platform.sys.platform", "win32")

    available, reason = automation_runtime_available()

    assert available is True
    assert reason is None
