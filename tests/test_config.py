from pathlib import Path

from raidbot.config import Settings


def test_settings_from_env_parses_required_values(monkeypatch, tmp_path):
    monkeypatch.setenv("TELEGRAM_API_ID", "123456")
    monkeypatch.setenv("TELEGRAM_API_HASH", "hash-value")
    monkeypatch.setenv("TELEGRAM_SESSION_PATH", str(tmp_path / "raidbot.session"))
    monkeypatch.setenv("TELEGRAM_CHAT_WHITELIST", "-1001,-1002")
    monkeypatch.setenv("RAIDAR_SENDER_ID", "999888777")
    monkeypatch.setenv("CHROME_PATH", r"C:\Program Files\Google\Chrome\Application\chrome.exe")
    monkeypatch.setenv("CHROME_USER_DATA_DIR", r"C:\ChromeProfile")
    monkeypatch.setenv("CHROME_PROFILE_DIRECTORY", "Profile 3")

    settings = Settings.from_env()

    assert settings.telegram_api_id == 123456
    assert settings.telegram_api_hash == "hash-value"
    assert settings.telegram_session_path == Path(tmp_path / "raidbot.session")
    assert settings.telegram_chat_whitelist == {-1001, -1002}
    assert settings.raidar_sender_id == 999888777
    assert settings.chrome_path == Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
    assert settings.chrome_user_data_dir == Path(r"C:\ChromeProfile")
    assert settings.chrome_profile_directory == "Profile 3"
    assert settings.open_cooldown_seconds == 0.0
    assert settings.log_level == "INFO"


def test_settings_from_env_rejects_missing_required_values(monkeypatch):
    monkeypatch.delenv("TELEGRAM_API_ID", raising=False)
    monkeypatch.setenv("TELEGRAM_API_HASH", "hash-value")
    monkeypatch.setenv("TELEGRAM_SESSION_PATH", r"C:\raidbot.session")
    monkeypatch.setenv("TELEGRAM_CHAT_WHITELIST", "-1001")
    monkeypatch.setenv("RAIDAR_SENDER_ID", "999888777")
    monkeypatch.setenv("CHROME_PATH", r"C:\Chrome.exe")
    monkeypatch.setenv("CHROME_USER_DATA_DIR", r"C:\ChromeProfile")
    monkeypatch.setenv("CHROME_PROFILE_DIRECTORY", "Profile 3")

    try:
        Settings.from_env()
    except ValueError as exc:
        assert "TELEGRAM_API_ID" in str(exc)
    else:
        raise AssertionError("Expected ValueError for missing TELEGRAM_API_ID")
