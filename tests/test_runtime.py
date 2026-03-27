from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

from raidbot.config import Settings


def load_runtime_module(monkeypatch):
    sys.modules.pop("raidbot.runtime", None)
    sys.modules.pop("raidbot.telegram_client", None)

    telethon_module = ModuleType("telethon")
    events_module = ModuleType("telethon.events")
    telethon_module.TelegramClient = object
    telethon_module.events = events_module
    events_module.NewMessage = object

    monkeypatch.setitem(sys.modules, "telethon", telethon_module)
    monkeypatch.setitem(sys.modules, "telethon.events", events_module)

    return importlib.import_module("raidbot.runtime")


def test_build_runtime_wires_service_and_listener(monkeypatch):
    runtime_module = load_runtime_module(monkeypatch)
    chrome_calls: list[dict[str, object]] = []
    service_calls: list[dict[str, object]] = []
    listener_calls: list[dict[str, object]] = []

    class FakeChromeOpener:
        def __init__(self, chrome_path, user_data_dir, profile_directory) -> None:
            chrome_calls.append(
                {
                    "chrome_path": chrome_path,
                    "user_data_dir": user_data_dir,
                    "profile_directory": profile_directory,
                }
            )

    class FakeStore:
        pass

    class FakeRaidService:
        def __init__(self, allowed_chat_ids, allowed_sender_id, opener, dedupe_store) -> None:
            self.allowed_chat_ids = allowed_chat_ids
            self.allowed_sender_id = allowed_sender_id
            self.opener = opener
            self.dedupe_store = dedupe_store
            service_calls.append(
                {
                    "allowed_chat_ids": allowed_chat_ids,
                    "allowed_sender_id": allowed_sender_id,
                    "opener": opener,
                    "dedupe_store": dedupe_store,
                }
            )

        def handle_message(self, message) -> None:
            return None

    class FakeTelegramRaidListener:
        def __init__(self, api_id, api_hash, session_path, on_message) -> None:
            self.api_id = api_id
            self.api_hash = api_hash
            self.session_path = session_path
            self.on_message = on_message
            listener_calls.append(
                {
                    "api_id": api_id,
                    "api_hash": api_hash,
                    "session_path": session_path,
                    "on_message": on_message,
                }
            )

    monkeypatch.setattr(runtime_module, "ChromeOpener", FakeChromeOpener)
    monkeypatch.setattr(runtime_module, "InMemoryOpenedUrlStore", FakeStore)
    monkeypatch.setattr(runtime_module, "RaidService", FakeRaidService)
    monkeypatch.setattr(runtime_module, "TelegramRaidListener", FakeTelegramRaidListener)

    settings = Settings(
        telegram_api_id=123456,
        telegram_api_hash="hash-value",
        telegram_session_path=Path("raidbot.session"),
        telegram_chat_whitelist={-1001, -1002},
        raidar_sender_id=42,
        chrome_path=Path(r"C:\Chrome\chrome.exe"),
        chrome_user_data_dir=Path(r"C:\ChromeData"),
        chrome_profile_directory="Profile 3",
    )

    runtime = runtime_module.build_runtime(settings)

    assert chrome_calls == [
        {
            "chrome_path": Path(r"C:\Chrome\chrome.exe"),
            "user_data_dir": Path(r"C:\ChromeData"),
            "profile_directory": "Profile 3",
        }
    ]
    assert len(service_calls) == 1
    assert service_calls[0]["allowed_chat_ids"] == {-1001, -1002}
    assert service_calls[0]["allowed_sender_id"] == 42
    assert isinstance(service_calls[0]["opener"], FakeChromeOpener)
    assert isinstance(service_calls[0]["dedupe_store"], FakeStore)
    assert len(listener_calls) == 1
    assert listener_calls[0]["api_id"] == 123456
    assert listener_calls[0]["api_hash"] == "hash-value"
    assert listener_calls[0]["session_path"] == "raidbot.session"
    assert listener_calls[0]["on_message"].__self__ is runtime.service
    assert listener_calls[0]["on_message"].__func__ is FakeRaidService.handle_message
    assert runtime.service.allowed_chat_ids == {-1001, -1002}
    assert runtime.service.allowed_sender_id == 42
    assert runtime.listener.session_path == "raidbot.session"


def test_main_loads_env_builds_runtime_and_runs_listener(monkeypatch):
    sys.modules.pop("raidbot.main", None)
    call_order: list[object] = []
    settings_instance = None

    class FakeSettings:
        log_level = "warning"

        @classmethod
        def from_env(cls):
            nonlocal settings_instance
            call_order.append("settings.from_env")
            settings_instance = cls()
            return settings_instance

    async def fake_run_forever() -> None:
        call_order.append("listener.run_forever")

    def fake_build_runtime(settings):
        call_order.append(("build_runtime", settings))
        return SimpleNamespace(listener=SimpleNamespace(run_forever=fake_run_forever))

    dotenv_module = ModuleType("dotenv")

    def fake_load_dotenv() -> None:
        call_order.append("load_dotenv")

    dotenv_module.load_dotenv = fake_load_dotenv

    config_module = ModuleType("raidbot.config")
    config_module.Settings = FakeSettings

    runtime_module = ModuleType("raidbot.runtime")
    runtime_module.build_runtime = fake_build_runtime

    monkeypatch.setitem(sys.modules, "dotenv", dotenv_module)
    monkeypatch.setitem(sys.modules, "raidbot.config", config_module)
    monkeypatch.setitem(sys.modules, "raidbot.runtime", runtime_module)

    main_module = importlib.import_module("raidbot.main")
    logging_calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        main_module.logging,
        "basicConfig",
        lambda **kwargs: logging_calls.append(kwargs),
    )

    main_module.main()

    assert call_order == [
        "load_dotenv",
        "settings.from_env",
        ("build_runtime", settings_instance),
        "listener.run_forever",
    ]
    assert logging_calls == [{"level": "warning"}]
