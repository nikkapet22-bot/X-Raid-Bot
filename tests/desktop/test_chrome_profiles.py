from __future__ import annotations

from pathlib import Path

import pytest


def test_detect_chrome_environment_reads_profiles_from_local_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from raidbot.desktop.chrome_profiles import detect_chrome_environment

    local_appdata = tmp_path / "Local"
    user_data_dir = local_appdata / "Google" / "Chrome" / "User Data"
    user_data_dir.mkdir(parents=True)
    (user_data_dir / "Local State").write_text(
        '{"profile":{"info_cache":{"Profile 3":{"name":"Raid"},"Default":{"name":"Main"}}}}',
        encoding="utf-8",
    )
    (user_data_dir / "Default").mkdir()
    (user_data_dir / "Profile 3").mkdir()

    chrome_exe = tmp_path / "Program Files" / "Google" / "Chrome" / "Application" / "chrome.exe"
    chrome_exe.parent.mkdir(parents=True)
    chrome_exe.write_text("", encoding="utf-8")

    monkeypatch.setenv("LOCALAPPDATA", str(local_appdata))
    monkeypatch.setenv("PROGRAMFILES", str(tmp_path / "Program Files"))
    monkeypatch.delenv("PROGRAMFILES(X86)", raising=False)

    environment = detect_chrome_environment()

    assert environment.chrome_path == chrome_exe
    assert environment.user_data_dir == user_data_dir
    assert [profile.directory_name for profile in environment.profiles] == ["Default", "Profile 3"]
    assert [profile.label for profile in environment.profiles] == ["Main", "Raid"]


def test_detect_chrome_environment_ignores_profiles_not_listed_in_local_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from raidbot.desktop.chrome_profiles import detect_chrome_environment

    local_appdata = tmp_path / "Local"
    user_data_dir = local_appdata / "Google" / "Chrome" / "User Data"
    user_data_dir.mkdir(parents=True)
    (user_data_dir / "Local State").write_text(
        '{"profile":{"info_cache":{"Default":{"name":"Main"}}}}',
        encoding="utf-8",
    )
    (user_data_dir / "Default").mkdir()
    (user_data_dir / "Profile 7").mkdir()

    chrome_exe = tmp_path / "Program Files" / "Google" / "Chrome" / "Application" / "chrome.exe"
    chrome_exe.parent.mkdir(parents=True)
    chrome_exe.write_text("", encoding="utf-8")

    monkeypatch.setenv("LOCALAPPDATA", str(local_appdata))
    monkeypatch.setenv("PROGRAMFILES", str(tmp_path / "Program Files"))
    monkeypatch.delenv("PROGRAMFILES(X86)", raising=False)

    environment = detect_chrome_environment()

    assert [profile.directory_name for profile in environment.profiles] == ["Default"]


def test_detect_chrome_environment_raises_when_chrome_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from raidbot.desktop.chrome_profiles import detect_chrome_environment

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    monkeypatch.setenv("PROGRAMFILES", str(tmp_path / "Program Files"))
    monkeypatch.delenv("PROGRAMFILES(X86)", raising=False)

    with pytest.raises(RuntimeError, match="Chrome executable not found"):
        detect_chrome_environment()


def test_detect_chrome_environment_uses_program_files_x86_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from raidbot.desktop.chrome_profiles import detect_chrome_environment

    local_appdata = tmp_path / "Local"
    user_data_dir = local_appdata / "Google" / "Chrome" / "User Data"
    user_data_dir.mkdir(parents=True)
    (user_data_dir / "Local State").write_text(
        '{"profile":{"info_cache":{"Default":{"name":"Main"}}}}',
        encoding="utf-8",
    )
    (user_data_dir / "Default").mkdir()

    chrome_exe = tmp_path / "Program Files (x86)" / "Google" / "Chrome" / "Application" / "chrome.exe"
    chrome_exe.parent.mkdir(parents=True)
    chrome_exe.write_text("", encoding="utf-8")

    monkeypatch.delenv("PROGRAMFILES", raising=False)
    monkeypatch.setenv("PROGRAMFILES(X86)", str(tmp_path / "Program Files (x86)"))
    monkeypatch.setenv("LOCALAPPDATA", str(local_appdata))

    environment = detect_chrome_environment()

    assert environment.chrome_path == chrome_exe


def test_detect_chrome_environment_raises_when_local_state_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from raidbot.desktop.chrome_profiles import detect_chrome_environment

    local_appdata = tmp_path / "Local"
    user_data_dir = local_appdata / "Google" / "Chrome" / "User Data"
    user_data_dir.mkdir(parents=True)

    chrome_exe = tmp_path / "Program Files" / "Google" / "Chrome" / "Application" / "chrome.exe"
    chrome_exe.parent.mkdir(parents=True)
    chrome_exe.write_text("", encoding="utf-8")

    monkeypatch.setenv("LOCALAPPDATA", str(local_appdata))
    monkeypatch.setenv("PROGRAMFILES", str(tmp_path / "Program Files"))
    monkeypatch.delenv("PROGRAMFILES(X86)", raising=False)

    with pytest.raises(RuntimeError, match="Chrome Local State file not found"):
        detect_chrome_environment()
