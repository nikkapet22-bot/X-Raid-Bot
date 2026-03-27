from pathlib import Path
import subprocess

from raidbot.chrome import ChromeOpener


def test_chrome_opener_builds_expected_command(monkeypatch):
    captured = {}

    def fake_launcher(cmd):
        captured["cmd"] = cmd

    opener = ChromeOpener(
        chrome_path=Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        user_data_dir=Path(r"C:\ChromeProfile"),
        profile_directory="Profile 3",
        launcher=fake_launcher,
    )

    opener.open("https://example.com/status/123")

    assert captured["cmd"] == [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        "--new-tab",
        "--user-data-dir=C:\\ChromeProfile",
        "--profile-directory=Profile 3",
        "https://example.com/status/123",
    ]


def test_chrome_opener_defaults_launcher_to_popen():
    opener = ChromeOpener(
        chrome_path=Path(r"C:\Chrome.exe"),
        user_data_dir=Path(r"C:\ChromeProfile"),
        profile_directory="Profile 3",
    )

    assert opener.launcher is subprocess.Popen
