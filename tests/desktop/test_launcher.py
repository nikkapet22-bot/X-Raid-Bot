from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
LAUNCHER_PATH = REPO_ROOT / "Launch RaidBot.bat"
HIDDEN_LAUNCHER_PATH = REPO_ROOT / "Launch RaidBot.vbs"
README_PATH = REPO_ROOT / "README.md"


def test_desktop_launcher_batch_file_uses_pythonw_from_repo_root() -> None:
    assert LAUNCHER_PATH.exists()

    contents = LAUNCHER_PATH.read_text(encoding="utf-8")

    assert "@echo off" in contents
    assert 'cd /d "%~dp0"' in contents
    assert 'start "" pythonw -m raidbot.desktop.app' in contents


def test_hidden_launcher_vbs_runs_pythonw_without_visible_console() -> None:
    assert HIDDEN_LAUNCHER_PATH.exists()

    contents = HIDDEN_LAUNCHER_PATH.read_text(encoding="utf-8")

    assert 'CreateObject("WScript.Shell")' in contents
    assert "pythonw -m raidbot.desktop.app" in contents
    assert ", 0, False" in contents


def test_readme_mentions_double_click_launcher() -> None:
    contents = README_PATH.read_text(encoding="utf-8")

    assert "Launch RaidBot.bat" in contents
    assert "Launch RaidBot.vbs" in contents
