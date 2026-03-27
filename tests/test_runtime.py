from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

from raidbot.browser.models import (
    RaidActionJob,
    RaidActionRequirements,
    RaidDetectionResult,
    RaidExecutionResult,
)
from raidbot.config import Settings
from raidbot.models import IncomingMessage


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


def test_build_runtime_wires_browser_pipeline_and_listener(monkeypatch):
    runtime_module = load_runtime_module(monkeypatch)
    calls: list[tuple[str, object]] = []

    class FakeChromeOpener:
        def __init__(self, chrome_path, user_data_dir, profile_directory) -> None:
            self.chrome_path = chrome_path
            self.user_data_dir = user_data_dir
            self.profile_directory = profile_directory
            calls.append(
                (
                    "chrome",
                    (
                        chrome_path,
                        user_data_dir,
                        profile_directory,
                    ),
                )
            )

    class FakeBackend:
        def __init__(self, launcher) -> None:
            self.launcher = launcher
            calls.append(("backend", launcher))

    class FakeExecutor:
        name = "noop"

        def __init__(self) -> None:
            calls.append(("executor", self.name))

    class FakeStore:
        def __init__(self) -> None:
            self.marked: list[str] = []

        def contains(self, url: str) -> bool:
            return url in self.marked

        def mark_if_new(self, url: str) -> bool:
            self.marked.append(url)
            return True

    class FakeService:
        def __init__(self, allowed_chat_ids, allowed_sender_ids, dedupe_store, preset_replies) -> None:
            self.allowed_chat_ids = allowed_chat_ids
            self.allowed_sender_ids = allowed_sender_ids
            self.dedupe_store = dedupe_store
            self.preset_replies = preset_replies
            calls.append(
                (
                    "service",
                    (
                        allowed_chat_ids,
                        allowed_sender_ids,
                        dedupe_store,
                        preset_replies,
                    ),
                )
            )

        def handle_message(self, message):
            return message

    class FakePipeline:
        def __init__(self, backend, executor) -> None:
            self.backend = backend
            self.executor = executor
            calls.append(("pipeline", (backend, executor)))

        def execute(self, job, *, should_continue=None):
            _ = should_continue
            return job

    class FakeListener:
        def __init__(self, api_id, api_hash, session_path, on_message) -> None:
            self.api_id = api_id
            self.api_hash = api_hash
            self.session_path = session_path
            self.on_message = on_message
            calls.append(("listener", (api_id, api_hash, session_path, on_message)))

    monkeypatch.setattr(runtime_module, "ChromeOpener", FakeChromeOpener)
    monkeypatch.setattr(runtime_module, "LaunchOnlyBrowserBackend", FakeBackend)
    monkeypatch.setattr(runtime_module, "NoOpRaidExecutor", FakeExecutor)
    monkeypatch.setattr(runtime_module, "InMemoryOpenedUrlStore", FakeStore)
    monkeypatch.setattr(runtime_module, "RaidService", FakeService)
    monkeypatch.setattr(runtime_module, "BrowserPipeline", FakePipeline)
    monkeypatch.setattr(runtime_module, "TelegramRaidListener", FakeListener)

    settings = Settings(
        telegram_api_id=123456,
        telegram_api_hash="hash-value",
        telegram_session_path=Path("raidbot.session"),
        telegram_chat_whitelist={-1001, -1002},
        allowed_sender_ids={42},
        chrome_path=Path(r"C:\Chrome\chrome.exe"),
        chrome_user_data_dir=Path(r"C:\ChromeData"),
        chrome_profile_directory="Profile 3",
        browser_mode="launch-only",
        executor_name="noop",
        preset_replies=("hello", "world"),
    )

    runtime = runtime_module.build_runtime(settings)

    assert ("chrome", (Path(r"C:\Chrome\chrome.exe"), Path(r"C:\ChromeData"), "Profile 3")) in calls
    assert ("service", ({-1001, -1002}, {42}, runtime.dedupe_store, ("hello", "world"))) in calls
    assert ("pipeline", (runtime.pipeline.backend, runtime.pipeline.executor)) in calls
    assert (
        "listener",
        (
            123456,
            "hash-value",
            "raidbot.session",
            runtime.message_handler,
        ),
    ) in calls
    assert runtime.service.allowed_chat_ids == {-1001, -1002}
    assert runtime.service.allowed_sender_ids == {42}
    assert runtime.service.dedupe_store is runtime.dedupe_store
    assert runtime.service.preset_replies == ("hello", "world")
    assert isinstance(runtime.pipeline.backend, FakeBackend)
    assert isinstance(runtime.pipeline.backend.launcher, FakeChromeOpener)
    assert runtime.pipeline.backend.launcher.chrome_path == Path(r"C:\Chrome\chrome.exe")
    assert runtime.pipeline.backend.launcher.user_data_dir == Path(r"C:\ChromeData")
    assert runtime.pipeline.backend.launcher.profile_directory == "Profile 3"
    assert isinstance(runtime.pipeline.executor, FakeExecutor)
    assert runtime.listener.on_message is runtime.message_handler


def test_runtime_message_handler_returns_non_job_results_directly(monkeypatch):
    runtime_module = load_runtime_module(monkeypatch)
    calls: list[str] = []

    class FakeStore:
        def contains(self, url: str) -> bool:
            calls.append(f"contains:{url}")
            return False

        def mark_if_new(self, url: str) -> bool:
            calls.append(f"mark:{url}")
            return True

    class FakeService:
        def __init__(self, allowed_chat_ids, allowed_sender_ids, dedupe_store, preset_replies) -> None:
            self.dedupe_store = dedupe_store

        def handle_message(self, message):
            calls.append("service")
            return RaidDetectionResult(kind="not_a_raid")

    class FakePipeline:
        def __init__(self, backend, executor) -> None:
            _ = (backend, executor)

        def execute(self, job, *, should_continue=None):
            _ = (job, should_continue)
            calls.append("pipeline")
            return RaidExecutionResult(kind="executor_not_configured", handed_off=True)

    class FakeListener:
        def __init__(self, api_id, api_hash, session_path, on_message) -> None:
            _ = (api_id, api_hash, session_path)
            self.on_message = on_message

    class FakeChromeOpener:
        def __init__(self, chrome_path, user_data_dir, profile_directory) -> None:
            _ = (chrome_path, user_data_dir, profile_directory)

    class FakeBackend:
        def __init__(self, launcher) -> None:
            _ = launcher

    class FakeExecutor:
        name = "noop"

        def __init__(self) -> None:
            pass

    monkeypatch.setattr(runtime_module, "InMemoryOpenedUrlStore", FakeStore)
    monkeypatch.setattr(runtime_module, "RaidService", FakeService)
    monkeypatch.setattr(runtime_module, "BrowserPipeline", FakePipeline)
    monkeypatch.setattr(runtime_module, "TelegramRaidListener", FakeListener)
    monkeypatch.setattr(runtime_module, "ChromeOpener", FakeChromeOpener)
    monkeypatch.setattr(runtime_module, "LaunchOnlyBrowserBackend", FakeBackend)
    monkeypatch.setattr(runtime_module, "NoOpRaidExecutor", FakeExecutor)

    settings = Settings(
        telegram_api_id=123456,
        telegram_api_hash="hash-value",
        telegram_session_path=Path("raidbot.session"),
        telegram_chat_whitelist={-1001},
        allowed_sender_ids={42},
        chrome_path=Path(r"C:\Chrome\chrome.exe"),
        chrome_user_data_dir=Path(r"C:\ChromeData"),
        chrome_profile_directory="Profile 3",
    )

    runtime = runtime_module.build_runtime(settings)
    message = IncomingMessage(chat_id=-1001, sender_id=42, text="hello")

    result = runtime.listener.on_message(message)

    assert result == RaidDetectionResult(kind="not_a_raid")
    assert calls == ["service"]


def test_runtime_message_handler_marks_dedupe_after_handed_off_execution(monkeypatch):
    runtime_module = load_runtime_module(monkeypatch)
    calls: list[str] = []
    job = RaidActionJob(
        normalized_url="https://raid.example/abc",
        raw_url="https://raid.example/abc?utm_source=telegram",
        chat_id=-1001,
        sender_id=42,
        requirements=RaidActionRequirements(
            like=True,
            repost=False,
            bookmark=False,
            reply=True,
        ),
        preset_replies=("hello",),
        trace_id="raid-123",
    )
    detection_result = RaidDetectionResult.job_detected(job)
    execution_result = RaidExecutionResult(kind="executor_not_configured", handed_off=True)

    class FakeStore:
        def __init__(self) -> None:
            self.marked: list[str] = []

        def contains(self, url: str) -> bool:
            calls.append(f"contains:{url}")
            return False

        def mark_if_new(self, url: str) -> bool:
            calls.append(f"mark:{url}")
            self.marked.append(url)
            return True

    class FakeService:
        def __init__(self, allowed_chat_ids, allowed_sender_ids, dedupe_store, preset_replies) -> None:
            self.dedupe_store = dedupe_store

        def handle_message(self, message):
            _ = message
            calls.append("service")
            return detection_result

    class FakePipeline:
        def __init__(self, backend, executor) -> None:
            _ = (backend, executor)

        def execute(self, job_arg, *, should_continue=None):
            _ = should_continue
            calls.append(f"pipeline:{job_arg.normalized_url}")
            return execution_result

    class FakeListener:
        def __init__(self, api_id, api_hash, session_path, on_message) -> None:
            _ = (api_id, api_hash, session_path)
            self.on_message = on_message

    class FakeChromeOpener:
        def __init__(self, chrome_path, user_data_dir, profile_directory) -> None:
            _ = (chrome_path, user_data_dir, profile_directory)

    class FakeBackend:
        def __init__(self, launcher) -> None:
            _ = launcher

    class FakeExecutor:
        name = "noop"

        def __init__(self) -> None:
            pass

    monkeypatch.setattr(runtime_module, "InMemoryOpenedUrlStore", FakeStore)
    monkeypatch.setattr(runtime_module, "RaidService", FakeService)
    monkeypatch.setattr(runtime_module, "BrowserPipeline", FakePipeline)
    monkeypatch.setattr(runtime_module, "TelegramRaidListener", FakeListener)
    monkeypatch.setattr(runtime_module, "ChromeOpener", FakeChromeOpener)
    monkeypatch.setattr(runtime_module, "LaunchOnlyBrowserBackend", FakeBackend)
    monkeypatch.setattr(runtime_module, "NoOpRaidExecutor", FakeExecutor)

    settings = Settings(
        telegram_api_id=123456,
        telegram_api_hash="hash-value",
        telegram_session_path=Path("raidbot.session"),
        telegram_chat_whitelist={-1001},
        allowed_sender_ids={42},
        chrome_path=Path(r"C:\Chrome\chrome.exe"),
        chrome_user_data_dir=Path(r"C:\ChromeData"),
        chrome_profile_directory="Profile 3",
    )

    runtime = runtime_module.build_runtime(settings)
    message = IncomingMessage(chat_id=-1001, sender_id=42, text="raid")

    result = runtime.listener.on_message(message)

    assert result is execution_result
    assert calls == [
        "service",
        "pipeline:https://raid.example/abc",
        "mark:https://raid.example/abc",
    ]
    assert runtime.dedupe_store.marked == ["https://raid.example/abc"]


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
