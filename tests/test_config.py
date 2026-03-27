from pathlib import Path

from raidbot.config import Settings


def set_required_env(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("TELEGRAM_API_ID", "123456")
    monkeypatch.setenv("TELEGRAM_API_HASH", "hash-value")
    monkeypatch.setenv("TELEGRAM_SESSION_PATH", str(tmp_path / "raidbot.session"))
    monkeypatch.setenv("TELEGRAM_CHAT_WHITELIST", "-1001,-1002")
    monkeypatch.setenv("CHROME_PATH", r"C:\Program Files\Google\Chrome\Application\chrome.exe")
    monkeypatch.setenv("CHROME_USER_DATA_DIR", r"C:\ChromeProfile")
    monkeypatch.setenv("CHROME_PROFILE_DIRECTORY", "Profile 3")


def test_settings_from_env_parses_sender_allowlist_and_detection_fields(monkeypatch, tmp_path):
    set_required_env(monkeypatch, tmp_path)
    monkeypatch.setenv("ALLOWED_SENDER_IDS", "42,77")
    monkeypatch.setenv("BROWSER_MODE", "launch-only")
    monkeypatch.setenv("EXECUTOR_NAME", "noop")
    monkeypatch.setenv("PRESET_REPLIES", "gm, lfggg")
    monkeypatch.setenv("DEFAULT_ACTION_LIKE", "true")
    monkeypatch.setenv("DEFAULT_ACTION_REPOST", "false")
    monkeypatch.setenv("DEFAULT_ACTION_BOOKMARK", "1")
    monkeypatch.setenv("DEFAULT_ACTION_REPLY", "0")

    settings = Settings.from_env()

    assert settings.telegram_api_id == 123456
    assert settings.telegram_api_hash == "hash-value"
    assert settings.telegram_session_path == Path(tmp_path / "raidbot.session")
    assert settings.telegram_chat_whitelist == {-1001, -1002}
    assert settings.allowed_sender_ids == {42, 77}
    assert settings.chrome_path == Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
    assert settings.chrome_user_data_dir == Path(r"C:\ChromeProfile")
    assert settings.chrome_profile_directory == "Profile 3"
    assert settings.browser_mode == "launch-only"
    assert settings.executor_name == "noop"
    assert settings.preset_replies == ("gm", "lfggg")
    assert settings.default_action_like is True
    assert settings.default_action_repost is False
    assert settings.default_action_bookmark is True
    assert settings.default_action_reply is False
    assert settings.open_cooldown_seconds == 0.0
    assert settings.log_level == "INFO"


def test_settings_from_env_falls_back_to_single_sender_id_when_allowlist_missing(monkeypatch, tmp_path):
    set_required_env(monkeypatch, tmp_path)
    monkeypatch.delenv("ALLOWED_SENDER_IDS", raising=False)
    monkeypatch.setenv("RAIDAR_SENDER_ID", "999888777")

    settings = Settings.from_env()

    assert settings.allowed_sender_ids == {999888777}
    assert not hasattr(settings, "raidar_sender_id")


def test_settings_from_env_rejects_blank_allowlist_when_present(monkeypatch, tmp_path):
    set_required_env(monkeypatch, tmp_path)
    monkeypatch.setenv("ALLOWED_SENDER_IDS", "   ")
    monkeypatch.setenv("RAIDAR_SENDER_ID", "999888777")

    try:
        Settings.from_env()
    except ValueError as exc:
        assert "ALLOWED_SENDER_IDS" in str(exc)
    else:
        raise AssertionError("Expected ValueError for blank ALLOWED_SENDER_IDS")


def test_settings_from_env_rejects_invalid_default_action_boolean(monkeypatch, tmp_path):
    set_required_env(monkeypatch, tmp_path)
    monkeypatch.setenv("ALLOWED_SENDER_IDS", "42")
    monkeypatch.setenv("DEFAULT_ACTION_LIKE", "sometimes")

    try:
        Settings.from_env()
    except ValueError as exc:
        assert "DEFAULT_ACTION_LIKE" in str(exc)
    else:
        raise AssertionError("Expected ValueError for invalid DEFAULT_ACTION_LIKE")


def test_settings_from_env_rejects_missing_required_values(monkeypatch, tmp_path):
    set_required_env(monkeypatch, tmp_path)
    monkeypatch.delenv("TELEGRAM_API_ID", raising=False)
    monkeypatch.setenv("ALLOWED_SENDER_IDS", "42")

    try:
        Settings.from_env()
    except ValueError as exc:
        assert "TELEGRAM_API_ID" in str(exc)
    else:
        raise AssertionError("Expected ValueError for missing TELEGRAM_API_ID")
