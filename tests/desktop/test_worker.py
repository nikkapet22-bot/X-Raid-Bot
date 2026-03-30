from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from raidbot.chrome import OpenedRaidContext
from raidbot.desktop.automation.models import AutomationSequence, AutomationStep
from raidbot.desktop.automation.runner import RunResult
from raidbot.desktop.automation.storage import AutomationStorage
from raidbot.desktop.automation.windowing import WindowInfo
from raidbot.desktop.models import (
    ActivityEntry,
    BotActionPreset,
    BotActionSlotConfig,
    BotRuntimeState,
    DesktopAppConfig,
    DesktopAppState,
    RaidProfileConfig,
    RaidProfileState,
    TelegramConnectionState,
)
from raidbot.models import (
    IncomingMessage,
    MessageOutcome,
    RaidActionJob,
    RaidActionRequirements,
    RaidDetectionResult,
    RaidExecutionResult,
)


class FakeStorage:
    def __init__(
        self,
        initial_state: DesktopAppState | None = None,
        *,
        base_dir: Path | None = None,
    ) -> None:
        self.initial_state = initial_state or DesktopAppState()
        self.saved_states: list[DesktopAppState] = []
        self.base_dir = base_dir or Path(".")

    def load_state(self) -> DesktopAppState:
        return deepcopy(self.initial_state)

    def save_state(self, state: DesktopAppState) -> None:
        self.saved_states.append(deepcopy(state))


class FakeLauncher:
    def __init__(self, profile_directory: str) -> None:
        self.profile_directory = profile_directory


class FakeBackend:
    def __init__(self, profile_directory: str) -> None:
        self._launcher = FakeLauncher(profile_directory)


class FakeService:
    def __init__(
        self,
        config: DesktopAppConfig,
        *,
        detection_result: RaidDetectionResult | None = None,
        detection_result_factory=None,
    ) -> None:
        self.allowed_chat_ids = set(config.whitelisted_chat_ids)
        self.allowed_sender_ids = set(config.allowed_sender_ids)
        self.default_requirements = RaidActionRequirements(
            like=config.default_action_like,
            repost=config.default_action_repost,
            bookmark=config.default_action_bookmark,
            reply=config.default_action_reply,
        )
        self.preset_replies = tuple(config.preset_replies)
        self.detection_result = detection_result or RaidDetectionResult(kind="not_a_raid")
        self.detection_result_factory = detection_result_factory
        self.handled_messages: list[IncomingMessage] = []

    def handle_message(self, message: IncomingMessage) -> RaidDetectionResult:
        self.handled_messages.append(message)
        if self.detection_result_factory is not None:
            return self.detection_result_factory(message)
        return self.detection_result


class FakePipeline:
    def __init__(
        self,
        config: DesktopAppConfig,
        *,
        execution_result: RaidExecutionResult | None = None,
        on_execute=None,
    ) -> None:
        self.execution_result = execution_result or RaidExecutionResult(
            kind="executor_not_configured",
            handed_off=True,
        )
        self.on_execute = on_execute
        self.execute_calls: list[tuple[RaidActionJob, object | None]] = []
        self.should_continue_results: list[bool] = []
        self._backend = FakeBackend(config.chrome_profile_directory)

    def execute(self, job: RaidActionJob, *, should_continue=None) -> RaidExecutionResult:
        self.execute_calls.append((job, should_continue))
        if self.on_execute is not None:
            return self.on_execute(job, should_continue)
        if should_continue is not None:
            self.should_continue_results.append(bool(should_continue()))
        return self.execution_result


class FakeWindowManager:
    def __init__(self, windows: list[object]) -> None:
        self.windows = list(windows)

    def list_chrome_windows(self) -> list[object]:
        return list(self.windows)

    def find_owned_chrome_window(self, profile_directory: str):
        _ = profile_directory
        return self.windows[0] if self.windows else None


class FakeAutomationRuntime:
    def __init__(
        self,
        *,
        windows: list[object] | None = None,
        run_sequence_results: list[RunResult] | None = None,
        wait_for_step_result: RunResult | None = None,
        on_run_sequence=None,
    ) -> None:
        self.window_manager = FakeWindowManager(windows or [])
        self.run_sequence_results = list(run_sequence_results or [])
        self.wait_for_step_result = wait_for_step_result
        self.on_run_sequence = on_run_sequence
        self.run_calls: list[tuple[str, int | None]] = []
        self.run_sequences: list[AutomationSequence] = []
        self.wait_for_step_calls: list[tuple[Path, int | None]] = []
        self.request_stop_calls = 0

        def _input_init(instance) -> None:
            instance.close_active_tab_calls = 0
            instance.close_active_window_calls = 0

        self.input_driver = type(
            "FakeInputDriver",
            (),
            {
                "__init__": _input_init,
                "close_active_tab": lambda self: setattr(
                    self,
                    "close_active_tab_calls",
                    self.close_active_tab_calls + 1,
                ),
                "close_active_window": lambda self: setattr(
                    self,
                    "close_active_window_calls",
                    self.close_active_window_calls + 1,
                ),
            },
        )()
        self._active_runner = SimpleNamespace(input_driver=self.input_driver)

    def list_target_windows(self) -> list[object]:
        return self.window_manager.list_chrome_windows()

    def wait_for_step_match(
        self,
        step: AutomationStep,
        selected_window_handle: int | None,
        *,
        require_interactable_window: bool = True,
    ):
        _ = require_interactable_window
        self.wait_for_step_calls.append((step.template_path, selected_window_handle))
        if self.wait_for_step_result is not None:
            return self.wait_for_step_result
        return RunResult(
            status="dry_run_match_found",
            window_handle=selected_window_handle,
            step_index=0,
        )

    def run_sequence(self, sequence: AutomationSequence, selected_window_handle: int | None):
        self.run_calls.append((sequence.id, selected_window_handle))
        self.run_sequences.append(sequence)
        self._active_runner = SimpleNamespace(input_driver=self.input_driver)
        if self.on_run_sequence is not None:
            result = self.on_run_sequence(sequence, selected_window_handle)
            if result is not None:
                return result
        if self.run_sequence_results:
            return self.run_sequence_results.pop(0)
        return RunResult(status="completed", window_handle=selected_window_handle)

    def request_stop(self) -> None:
        self.request_stop_calls += 1


class MultiProfileRuntime:
    def __init__(self, run_results: list[RunResult]) -> None:
        self.windows: list[WindowInfo] = []
        self.run_results = list(run_results)
        self.run_calls: list[tuple[str, int | None]] = []
        self.closed_window_handles: list[int] = []
        self._active_handle: int | None = None

        def _input_init(instance) -> None:
            instance.close_active_window_calls = 0

        def _close_active_window(instance) -> None:
            if self._active_handle is not None:
                self.closed_window_handles.append(self._active_handle)
                self.windows = [
                    window for window in self.windows if window.handle != self._active_handle
                ]
            instance.close_active_window_calls += 1

        self.input_driver = type(
            "FakeInputDriver",
            (),
            {
                "__init__": _input_init,
                "close_active_window": _close_active_window,
            },
        )()
        self._active_runner = SimpleNamespace(input_driver=self.input_driver)

    def list_target_windows(self) -> list[WindowInfo]:
        return list(self.windows)

    def run_sequence(self, sequence: AutomationSequence, selected_window_handle: int | None):
        self.run_calls.append((sequence.id, selected_window_handle))
        self._active_handle = selected_window_handle
        if self.run_results:
            return self.run_results.pop(0)
        return RunResult(status="completed", window_handle=selected_window_handle)

    def request_stop(self) -> None:
        return None


class WindowSpawningChromeOpener:
    def __init__(
        self,
        *,
        profile_directory: str,
        runtime: MultiProfileRuntime,
        handle_by_profile: dict[str, int],
        title_by_profile: dict[str, str] | None = None,
        **_kwargs,
    ) -> None:
        self.profile_directory = profile_directory
        self.runtime = runtime
        self.handle_by_profile = handle_by_profile
        self.title_by_profile = title_by_profile or {}
        self.open_calls: list[tuple[str, int | None]] = []
        self.open_raid_window_calls: list[str] = []

    def open(self, url: str, *, window_handle: int | None = None) -> OpenedRaidContext:
        self.open_calls.append((url, window_handle))
        return OpenedRaidContext(
            normalized_url=url,
            opened_at=1.0,
            window_handle=window_handle,
            profile_directory=self.profile_directory,
        )

    def open_raid_window(self, url: str) -> OpenedRaidContext:
        self.open_raid_window_calls.append(url)
        handle = self.handle_by_profile[self.profile_directory]
        self.runtime.windows.append(
            WindowInfo(
                handle=handle,
                title=self.title_by_profile.get(self.profile_directory, f"{self.profile_directory} - Chrome"),
                bounds=(0, 0, 100, 100),
                last_focused_at=float(handle),
            )
        )
        return OpenedRaidContext(
            normalized_url=url,
            opened_at=1.0,
            window_handle=None,
            profile_directory=self.profile_directory,
        )


class FakeChromeOpener:
    def __init__(self, *_, **kwargs) -> None:
        self.profile_directory = kwargs.get("profile_directory")
        self.open_calls: list[tuple[str, int | None]] = []
        self.open_raid_window_calls: list[str] = []

    def open(self, url: str, *, window_handle: int | None = None) -> OpenedRaidContext:
        self.open_calls.append((url, window_handle))
        return OpenedRaidContext(
            normalized_url=url,
            opened_at=1.0,
            window_handle=window_handle,
            profile_directory=self.profile_directory or "",
        )

    def open_raid_window(self, url: str) -> OpenedRaidContext:
        self.open_raid_window_calls.append(url)
        return OpenedRaidContext(
            normalized_url=url,
            opened_at=1.0,
            window_handle=None,
            profile_directory=self.profile_directory or "",
        )


class FailingChromeOpener:
    def __init__(self, *_, **kwargs) -> None:
        self.profile_directory = kwargs.get("profile_directory")
        self.open_calls: list[tuple[str, int | None]] = []
        self.open_raid_window_calls: list[str] = []

    def open(self, url: str, *, window_handle: int | None = None):
        self.open_calls.append((url, window_handle))
        raise RuntimeError("browser_startup_failure")

    def open_raid_window(self, url: str):
        self.open_raid_window_calls.append(url)
        raise RuntimeError("browser_startup_failure")


class FlakyChromeOpener:
    def __init__(self, *_, **kwargs) -> None:
        self.profile_directory = kwargs.get("profile_directory")
        self.open_calls: list[tuple[str, int | None]] = []
        self.open_raid_window_calls: list[str] = []
        self.failures_remaining = 1

    def open(self, url: str, *, window_handle: int | None = None) -> OpenedRaidContext:
        self.open_calls.append((url, window_handle))
        if self.failures_remaining:
            self.failures_remaining -= 1
            raise RuntimeError("browser_startup_failure")
        return OpenedRaidContext(
            normalized_url=url,
            opened_at=1.0,
            window_handle=window_handle,
            profile_directory=self.profile_directory or "",
        )

    def open_raid_window(self, url: str) -> OpenedRaidContext:
        self.open_raid_window_calls.append(url)
        if self.failures_remaining:
            self.failures_remaining -= 1
            raise RuntimeError("browser_startup_failure")
        return OpenedRaidContext(
            normalized_url=url,
            opened_at=1.0,
            window_handle=None,
            profile_directory=self.profile_directory or "",
        )


class FakeListener:
    def __init__(self, on_connection_state_change=None) -> None:
        self.on_connection_state_change = on_connection_state_change
        self.stop_calls = 0
        self.run_calls = 0

    async def run_forever(self) -> None:
        self.run_calls += 1
        if self.on_connection_state_change is not None:
            self.on_connection_state_change("connecting")
            self.on_connection_state_change("connected")
            self.on_connection_state_change("disconnected")

    async def stop(self) -> None:
        self.stop_calls += 1


class TrackingDedupeStore:
    def __init__(self) -> None:
        self.mark_calls: list[str] = []
        self._seen: set[str] = set()

    def contains(self, url: str) -> bool:
        return url in self._seen

    def mark_if_new(self, url: str) -> bool:
        self.mark_calls.append(url)
        if url in self._seen:
            return False
        self._seen.add(url)
        return True


def build_config(**overrides) -> DesktopAppConfig:
    values = {
        "telegram_api_id": 123456,
        "telegram_api_hash": "hash-value",
        "telegram_session_path": Path("raidbot.session"),
        "telegram_phone_number": "+40123456789",
        "whitelisted_chat_ids": [-1001],
        "allowed_sender_ids": [42],
        "chrome_profile_directory": "Profile 3",
    }
    values.update(overrides)
    return DesktopAppConfig(**values)


def build_job(normalized_url: str = "https://x.com/i/status/123") -> RaidActionJob:
    return RaidActionJob(
        normalized_url=normalized_url,
        raw_url=normalized_url,
        chat_id=-1001,
        sender_id=42,
        requirements=RaidActionRequirements(
            like=True,
            repost=True,
            bookmark=False,
            reply=True,
        ),
        preset_replies=("gm",),
        trace_id="raid-1",
    )


def build_message(text: str = "Likes 10 | 8 [%]\n\nhttps://x.com/i/status/123") -> IncomingMessage:
    return IncomingMessage(
        chat_id=-1001,
        sender_id=42,
        text=text,
    )


def detect_job_from_message(message: IncomingMessage) -> RaidDetectionResult:
    url = message.text.splitlines()[-1].strip()
    return RaidDetectionResult.job_detected(build_job(url))


def build_worker(
    storage: FakeStorage,
    events: list[dict],
    now: datetime,
    *,
    config: DesktopAppConfig | None = None,
    service_factory=None,
    pipeline_factory=None,
    listener_factory=None,
    automation_runtime_factory=None,
    chrome_opener_factory=None,
    manual_run_active=None,
    auto_run_wait=None,
):
    from raidbot.desktop.worker import DesktopBotWorker

    config = config or build_config()
    created_services = []
    created_pipelines = []
    created_listeners = []

    def default_service_factory(current_config: DesktopAppConfig) -> FakeService:
        service = FakeService(current_config)
        created_services.append(service)
        return service

    def default_pipeline_factory(current_config: DesktopAppConfig) -> FakePipeline:
        pipeline = FakePipeline(current_config)
        created_pipelines.append(pipeline)
        return pipeline

    def default_listener_factory(**kwargs) -> FakeListener:
        listener = FakeListener(
            on_connection_state_change=kwargs.get("on_connection_state_change")
        )
        created_listeners.append(listener)
        return listener

    worker = DesktopBotWorker(
        config=config,
        storage=storage,
        emit_event=events.append,
        service_factory=service_factory or default_service_factory,
        pipeline_factory=pipeline_factory or default_pipeline_factory,
        listener_factory=listener_factory or default_listener_factory,
        automation_runtime_factory=automation_runtime_factory,
        chrome_opener_factory=chrome_opener_factory,
        manual_run_active=manual_run_active,
        auto_run_wait=auto_run_wait,
        now=lambda: now,
    )
    return worker, created_services, created_pipelines, created_listeners


def build_default_worker(
    storage: FakeStorage,
    events: list[dict],
    now: datetime,
    *,
    config: DesktopAppConfig | None = None,
    chrome_environment_factory,
    listener_factory=None,
    automation_runtime_factory=None,
    chrome_opener_factory=None,
    manual_run_active=None,
    auto_run_wait=None,
):
    from raidbot.desktop.worker import DesktopBotWorker

    config = config or build_config()
    return DesktopBotWorker(
        config=config,
        storage=storage,
        emit_event=events.append,
        chrome_environment_factory=chrome_environment_factory,
        listener_factory=listener_factory or (lambda **kwargs: FakeListener()),
        automation_runtime_factory=automation_runtime_factory,
        chrome_opener_factory=chrome_opener_factory,
        manual_run_active=manual_run_active,
        auto_run_wait=auto_run_wait,
        now=lambda: now,
    )


def build_sequence(sequence_id: str = "seq-1") -> AutomationSequence:
    return AutomationSequence(
        id=sequence_id,
        name="Default automation",
        target_window_rule="Chrome",
        steps=[
            AutomationStep(
                name="Open menu",
                template_path=Path("templates/menu.png"),
                match_threshold=0.9,
                max_search_seconds=1.0,
                max_scroll_attempts=0,
                scroll_amount=-120,
                max_click_attempts=1,
                post_click_settle_ms=100,
            )
        ],
    )


def build_bot_action_slots(
    *,
    enabled_keys: tuple[str, ...] = ("slot_1_r",),
    missing_template_keys: tuple[str, ...] = (),
    slot_1_presets: tuple[BotActionPreset, ...] | None = None,
    slot_1_finish_template_path: Path | None = None,
) -> tuple[BotActionSlotConfig, ...]:
    if slot_1_presets is None:
        slot_1_presets = (
            BotActionPreset(id="preset-1", text="gm"),
        )
    if slot_1_finish_template_path is None:
        slot_1_finish_template_path = Path(__file__)
    slots: list[BotActionSlotConfig] = []
    for key, label in (
        ("slot_1_r", "R"),
        ("slot_2_l", "L"),
        ("slot_3_r", "R"),
        ("slot_4_b", "B"),
    ):
        enabled = key in enabled_keys
        template_path = None
        if enabled and key not in missing_template_keys:
            template_path = Path(__file__)
        slots.append(
            BotActionSlotConfig(
                key=key,
                label=label,
                enabled=enabled,
                template_path=template_path,
                presets=slot_1_presets if key == "slot_1_r" else (),
                finish_template_path=(
                    slot_1_finish_template_path if key == "slot_1_r" else None
                ),
            )
        )
    return tuple(slots)


def test_worker_records_sender_rejected_detection() -> None:
    events: list[dict] = []
    timestamp = datetime(2026, 3, 27, 10, 0, 0)
    storage = FakeStorage()
    detection = RaidDetectionResult(kind="sender_rejected")

    def service_factory(config: DesktopAppConfig) -> FakeService:
        return FakeService(config, detection_result=detection)

    worker, _services, _pipelines, _listeners = build_worker(
        storage,
        events,
        timestamp,
        service_factory=service_factory,
    )
    worker._service = service_factory(worker.config)
    worker._pipeline = FakePipeline(worker.config)

    outcome = worker._handle_message(build_message())

    assert outcome == detection
    assert worker.state.sender_rejected == 1
    assert worker.state.non_matching_skipped == 1
    assert worker.state.activity[-1] == ActivityEntry(
        timestamp=timestamp,
        action="sender_rejected",
        url=None,
        reason="sender_rejected",
    )
    assert [event["type"] for event in events] == ["stats_changed", "activity_added"]


def test_worker_queues_detected_links_and_processes_fifo(tmp_path) -> None:
    events: list[dict] = []
    timestamp = datetime(2026, 3, 27, 10, 2, 0)
    storage = FakeStorage(base_dir=tmp_path)
    first_url = "https://x.com/i/status/111"
    second_url = "https://x.com/i/status/222"
    first_message = build_message(f"Likes 10 | 8 [%]\n\n{first_url}")
    second_message = build_message(f"Likes 10 | 8 [%]\n\n{second_url}")
    runtime: FakeAutomationRuntime | None = None
    opener = FakeChromeOpener(profile_directory="Profile 3")
    worker_ref: dict[str, object] = {}
    first_run_triggered = {"value": False}
    run_callback = lambda _sequence, _handle: None

    def runtime_factory(_emit_event):
        nonlocal runtime
        runtime = FakeAutomationRuntime(
            windows=[
                WindowInfo(
                    handle=7,
                    title="RaidBot - Chrome",
                    bounds=(0, 0, 100, 100),
                    last_focused_at=1.0,
                )
                ],
            on_run_sequence=lambda sequence, handle: run_callback(sequence, handle),
        )
        return runtime

    worker, _created_services, _pipelines, _listeners = build_worker(
        storage,
        events,
        timestamp,
        config=build_config(
            auto_run_enabled=True,
            bot_action_slots=build_bot_action_slots(
                enabled_keys=("slot_1_r", "slot_3_r")
            ),
        ),
        service_factory=lambda config: FakeService(
            config,
            detection_result_factory=detect_job_from_message,
        ),
        automation_runtime_factory=runtime_factory,
        chrome_opener_factory=lambda **kwargs: opener,
    )
    worker_ref["worker"] = worker
    worker._service = worker._build_service(worker.config)
    run_callback = lambda _sequence, _handle: (
        (
            worker_ref["worker"]._handle_message(second_message)
            if not first_run_triggered["value"]
            else None
        ),
        first_run_triggered.__setitem__("value", True),
        None,
    )[1]

    outcome = worker._handle_message(first_message)

    assert outcome.kind == "job_detected"
    assert opener.open_calls == []
    assert opener.open_raid_window_calls == [first_url, second_url]
    assert runtime is not None
    assert runtime.run_calls == [
        ("bot-actions", 7),
        ("bot-actions", 7),
    ]
    assert runtime.input_driver.close_active_window_calls == 2
    assert runtime.input_driver.close_active_tab_calls == 0
    assert worker.state.automation_queue_state == "idle"


def test_worker_executes_multi_profile_success_in_order(tmp_path) -> None:
    events: list[dict] = []
    timestamp = datetime(2026, 3, 29, 12, 0, 0)
    storage = FakeStorage(base_dir=tmp_path)
    runtime = MultiProfileRuntime(
        run_results=[
            RunResult(status="completed", window_handle=41),
            RunResult(status="completed", window_handle=43),
        ]
    )
    created_openers: list[WindowSpawningChromeOpener] = []
    handle_by_profile = {"Default": 41, "Profile 3": 43}

    def chrome_opener_factory(**kwargs):
        opener = WindowSpawningChromeOpener(
            runtime=runtime,
            handle_by_profile=handle_by_profile,
            **kwargs,
        )
        created_openers.append(opener)
        return opener

    worker, _services, _pipelines, _listeners = build_worker(
        storage,
        events,
        timestamp,
        config=build_config(
            chrome_profile_directory="Default",
            auto_run_enabled=True,
            raid_profiles=(
                RaidProfileConfig("Default", "George", True),
                RaidProfileConfig("Profile 3", "Maria", True),
            ),
            bot_action_slots=build_bot_action_slots(),
        ),
        service_factory=lambda config: FakeService(
            config,
            detection_result_factory=detect_job_from_message,
        ),
        automation_runtime_factory=lambda _emit_event: runtime,
        chrome_opener_factory=chrome_opener_factory,
    )
    worker._service = worker._build_service(worker.config)

    outcome = worker._handle_message(build_message("Likes 10 | 8 [%]\n\nhttps://x.com/i/status/123"))

    assert outcome.kind == "job_detected"
    assert [opener.profile_directory for opener in created_openers] == ["Default", "Profile 3"]
    assert [opener.open_raid_window_calls for opener in created_openers] == [
        ["https://x.com/i/status/123"],
        ["https://x.com/i/status/123"],
    ]
    assert runtime.run_calls == [("bot-actions", 41), ("bot-actions", 43)]
    assert runtime.closed_window_handles == [41, 43]
    assert worker.state.raid_profile_states == (
        RaidProfileState("Default", "George", "green", None),
        RaidProfileState("Profile 3", "Maria", "green", None),
    )
    assert worker.state.automation_queue_state == "idle"


def test_worker_continues_after_profile_failure_and_marks_profile_red(tmp_path) -> None:
    events: list[dict] = []
    timestamp = datetime(2026, 3, 29, 12, 5, 0)
    storage = FakeStorage(base_dir=tmp_path)
    runtime = MultiProfileRuntime(
        run_results=[
            RunResult(status="completed", window_handle=41),
            RunResult(status="failed", window_handle=43, failure_reason="not_logged_in"),
            RunResult(status="completed", window_handle=45),
        ]
    )
    created_openers: list[WindowSpawningChromeOpener] = []
    handle_by_profile = {"Default": 41, "Profile 3": 43, "Profile 9": 45}

    def chrome_opener_factory(**kwargs):
        opener = WindowSpawningChromeOpener(
            runtime=runtime,
            handle_by_profile=handle_by_profile,
            **kwargs,
        )
        created_openers.append(opener)
        return opener

    worker, _services, _pipelines, _listeners = build_worker(
        storage,
        events,
        timestamp,
        config=build_config(
            chrome_profile_directory="Default",
            auto_run_enabled=True,
            raid_profiles=(
                RaidProfileConfig("Default", "George", True),
                RaidProfileConfig("Profile 3", "Maria", True),
                RaidProfileConfig("Profile 9", "Pasok", True),
            ),
            bot_action_slots=build_bot_action_slots(),
        ),
        service_factory=lambda config: FakeService(
            config,
            detection_result_factory=detect_job_from_message,
        ),
        automation_runtime_factory=lambda _emit_event: runtime,
        chrome_opener_factory=chrome_opener_factory,
    )
    worker._service = worker._build_service(worker.config)

    outcome = worker._handle_message(build_message("Likes 10 | 8 [%]\n\nhttps://x.com/i/status/456"))

    assert outcome.kind == "job_detected"
    assert [opener.profile_directory for opener in created_openers] == [
        "Default",
        "Profile 3",
        "Profile 9",
    ]
    assert runtime.run_calls == [
        ("bot-actions", 41),
        ("bot-actions", 43),
        ("bot-actions", 45),
    ]
    assert runtime.closed_window_handles == [41, 45]
    assert worker.state.raids_detected == 1
    assert worker.state.raids_opened == 1
    assert worker.state.raids_completed == 1
    assert worker.state.raids_failed == 0
    assert worker.state.raid_profile_states == (
        RaidProfileState("Default", "George", "green", None),
        RaidProfileState("Profile 3", "Maria", "red", "not_logged_in"),
        RaidProfileState("Profile 9", "Pasok", "green", None),
    )
    assert worker.state.automation_queue_state == "idle"
    assert worker.state.automation_queue_length == 0
    assert worker.state.automation_current_url is None
    assert worker.state.automation_last_error is None
    assert [entry.action for entry in worker.state.activity] == [
        "raid_detected",
        "auto_queued",
        "automation_started",
        "automation_succeeded",
        "session_closed",
        "automation_started",
        "automation_failed",
        "automation_started",
        "automation_succeeded",
        "session_closed",
    ]
    queue_states = [
        event["state"] for event in events if event["type"] == "automation_queue_state_changed"
    ]
    queue_lengths = [
        event["length"]
        for event in events
        if event["type"] == "automation_queue_length_changed"
    ]
    current_urls = [
        event["url"] for event in events if event["type"] == "automation_current_url_changed"
    ]
    started = [event for event in events if event["type"] == "automation_run_started"]
    succeeded = [event for event in events if event["type"] == "automation_run_succeeded"]

    assert queue_states == ["queued", "running", "idle"]
    assert queue_lengths == [1, 0]
    assert current_urls == ["https://x.com/i/status/456", None]
    assert [event["profile_directory"] for event in started] == [
        "Default",
        "Profile 3",
        "Profile 9",
    ]
    assert [event["profile_directory"] for event in succeeded] == [
        "Default",
        "Profile 9",
    ]


def test_worker_distributes_slot_1_presets_across_profiles_before_reusing() -> None:
    events: list[dict] = []
    timestamp = datetime(2026, 3, 29, 15, 0, 0)
    storage = FakeStorage()
    runtime = MultiProfileRuntime(run_results=[])
    runtime.run_sequences = []
    original_run_sequence = runtime.run_sequence

    def recording_run_sequence(sequence, selected_window_handle):
        runtime.run_sequences.append(sequence)
        return original_run_sequence(sequence, selected_window_handle)

    runtime.run_sequence = recording_run_sequence
    created_openers: list[WindowSpawningChromeOpener] = []
    handle_by_profile = {
        "Default": 61,
        "Profile 3": 63,
        "Profile 9": 65,
        "Profile 12": 67,
    }

    def chrome_opener_factory(**kwargs):
        opener = WindowSpawningChromeOpener(
            runtime=runtime,
            handle_by_profile=handle_by_profile,
            **kwargs,
        )
        created_openers.append(opener)
        return opener

    worker, _services, _pipelines, _listeners = build_worker(
        storage,
        events,
        timestamp,
        config=build_config(
            chrome_profile_directory="Default",
            auto_run_enabled=True,
            raid_profiles=(
                RaidProfileConfig("Default", "George", True),
                RaidProfileConfig("Profile 3", "Maria", True),
                RaidProfileConfig("Profile 9", "Pasok", True),
                RaidProfileConfig("Profile 12", "Elena", True),
            ),
            bot_action_slots=build_bot_action_slots(
                slot_1_presets=(
                    BotActionPreset(id="preset-1", text="gm"),
                    BotActionPreset(id="preset-2", text="wagmi"),
                    BotActionPreset(id="preset-3", text="lfggg"),
                ),
            ),
        ),
        service_factory=lambda config: FakeService(
            config,
            detection_result_factory=detect_job_from_message,
        ),
        automation_runtime_factory=lambda _emit_event: runtime,
        chrome_opener_factory=chrome_opener_factory,
    )
    worker._service = worker._build_service(worker.config)

    outcome = worker._handle_message(build_message("Likes 10 | 8 [%]\n\nhttps://x.com/i/status/999"))

    assert outcome.kind == "job_detected"
    assert [opener.profile_directory for opener in created_openers] == [
        "Default",
        "Profile 3",
        "Profile 9",
        "Profile 12",
    ]
    slot_1_texts = [sequence.steps[0].preset_text for sequence in runtime.run_sequences]

    assert len(slot_1_texts) == 4
    assert len(set(slot_1_texts[:3])) == 3
    assert slot_1_texts[3] in set(slot_1_texts[:3])
    assert len(set(slot_1_texts)) == 3


def test_worker_reacquires_target_window_after_open_when_focus_moves(tmp_path) -> None:
    events: list[dict] = []
    timestamp = datetime(2026, 3, 27, 10, 2, 30)
    storage = FakeStorage(base_dir=tmp_path)
    runtime: FakeAutomationRuntime | None = None

    class FocusAwareWindowManager(FakeWindowManager):
        def find_owned_chrome_window(self, profile_directory: str):
            _ = profile_directory
            return max(
                self.windows,
                key=lambda window: getattr(window, "last_focused_at", 0.0),
                default=None,
            )

    initial_window = WindowInfo(
        handle=7,
        title="Old RaidBot - Chrome",
        bounds=(0, 0, 100, 100),
        last_focused_at=2.0,
    )
    newly_focused_window = WindowInfo(
        handle=9,
        title="Opened Raid - Chrome",
        bounds=(100, 100, 300, 300),
        last_focused_at=1.0,
    )

    def runtime_factory(_emit_event):
        nonlocal runtime
        runtime = FakeAutomationRuntime(windows=[initial_window, newly_focused_window])
        runtime.window_manager = FocusAwareWindowManager(
            [initial_window, newly_focused_window]
        )
        return runtime

    class ReacquiringChromeOpener(FakeChromeOpener):
        def open_raid_window(self, url: str) -> OpenedRaidContext:
            context = super().open_raid_window(url)
            assert runtime is not None
            runtime.window_manager.windows = [
                WindowInfo(
                    handle=7,
                    title="Old RaidBot - Chrome",
                    bounds=(0, 0, 100, 100),
                    last_focused_at=1.0,
                ),
                WindowInfo(
                    handle=9,
                    title="Opened Raid - Chrome",
                    bounds=(100, 100, 300, 300),
                    last_focused_at=3.0,
                ),
            ]
            return context

    opener = ReacquiringChromeOpener(profile_directory="Profile 3")
    worker, _created_services, _pipelines, _listeners = build_worker(
        storage,
        events,
        timestamp,
        config=build_config(
            auto_run_enabled=True,
            bot_action_slots=build_bot_action_slots(enabled_keys=("slot_2_l",)),
        ),
        service_factory=lambda config: FakeService(
            config,
            detection_result_factory=detect_job_from_message,
        ),
        automation_runtime_factory=runtime_factory,
        chrome_opener_factory=lambda **kwargs: opener,
        auto_run_wait=lambda _seconds: None,
    )
    worker._service = worker._build_service(worker.config)

    outcome = worker._handle_message(
        build_message("Likes 10 | 8 [%]\n\nhttps://x.com/i/status/777")
    )

    assert outcome.kind == "job_detected"
    assert opener.open_calls == []
    assert opener.open_raid_window_calls == ["https://x.com/i/status/777"]
    assert runtime is not None
    assert runtime.run_calls == [("bot-actions", 9)]
    started = [event for event in events if event["type"] == "automation_run_started"]
    assert started == [
        {
            "type": "automation_run_started",
            "sequence_id": "bot-actions",
            "url": "https://x.com/i/status/777",
            "window_handle": 9,
            "profile_directory": "Profile 3",
        }
    ]


def test_worker_leaves_auto_run_queued_while_manual_automation_is_active_and_resumes_after_release(
    tmp_path,
) -> None:
    events: list[dict] = []
    timestamp = datetime(2026, 3, 27, 10, 3, 0)
    storage = FakeStorage(base_dir=tmp_path)
    opener = FakeChromeOpener(profile_directory="Profile 3")
    runtime: FakeAutomationRuntime | None = None
    manual_run_active = {"value": True}

    def runtime_factory(_emit_event):
        nonlocal runtime
        runtime = FakeAutomationRuntime(
            windows=[
                WindowInfo(
                    handle=9,
                    title="RaidBot - Chrome",
                    bounds=(0, 0, 100, 100),
                    last_focused_at=1.0,
                )
            ]
        )
        return runtime

    worker, _created_services, _pipelines, _listeners = build_worker(
        storage,
        events,
        timestamp,
        config=build_config(
            auto_run_enabled=True,
            bot_action_slots=build_bot_action_slots(),
        ),
        service_factory=lambda config: FakeService(
            config,
            detection_result_factory=detect_job_from_message,
        ),
        automation_runtime_factory=runtime_factory,
        chrome_opener_factory=lambda **kwargs: opener,
        manual_run_active=lambda: manual_run_active["value"],
    )
    worker._service = worker._build_service(worker.config)

    outcome = worker._handle_message(build_message())

    assert outcome.kind == "job_detected"
    assert opener.open_calls == []
    assert runtime is not None
    assert runtime.run_calls == []
    assert worker.state.automation_queue_state == "queued"
    assert worker.state.automation_queue_length == 1

    manual_run_active["value"] = False

    worker.notify_manual_automation_finished()

    assert opener.open_calls == []
    assert opener.open_raid_window_calls == ["https://x.com/i/status/123"]
    assert runtime.run_calls == [("bot-actions", 9)]
    assert worker.state.automation_queue_state == "idle"
    assert worker.state.automation_queue_length == 0


def test_worker_applies_auto_run_settle_delay_before_running_sequence(tmp_path) -> None:
    events: list[dict] = []
    timestamp = datetime(2026, 3, 27, 10, 4, 0)
    storage = FakeStorage(base_dir=tmp_path)
    opener = FakeChromeOpener(profile_directory="Profile 3")
    runtime: FakeAutomationRuntime | None = None
    calls: list[tuple[str, float | int | None]] = []

    def runtime_factory(_emit_event):
        nonlocal runtime
        runtime = FakeAutomationRuntime(
            windows=[
                WindowInfo(
                    handle=17,
                    title="RaidBot - Chrome",
                    bounds=(0, 0, 100, 100),
                    last_focused_at=1.0,
                )
            ],
            on_run_sequence=lambda _sequence, handle: calls.append(("run", handle)),
        )
        return runtime

    worker, _created_services, _pipelines, _listeners = build_worker(
        storage,
        events,
        timestamp,
        config=build_config(
            auto_run_enabled=True,
            bot_action_slots=build_bot_action_slots(),
            auto_run_settle_ms=2200,
        ),
        service_factory=lambda config: FakeService(
            config,
            detection_result_factory=detect_job_from_message,
        ),
        automation_runtime_factory=runtime_factory,
        chrome_opener_factory=lambda **kwargs: opener,
        auto_run_wait=lambda seconds: calls.append(("wait", seconds)),
    )
    worker._service = worker._build_service(worker.config)

    outcome = worker._handle_message(build_message())

    assert outcome.kind == "job_detected"
    assert opener.open_calls == []
    assert opener.open_raid_window_calls == ["https://x.com/i/status/123"]
    assert runtime is not None
    assert runtime.run_calls == [("bot-actions", 17)]
    assert calls == [("wait", 2.2), ("run", 17)]


def test_worker_marks_profile_red_when_dedicated_raid_window_cannot_be_identified(
    tmp_path,
) -> None:
    events: list[dict] = []
    timestamp = datetime(2026, 3, 27, 10, 5, 0)
    storage = FakeStorage(base_dir=tmp_path)
    opener = FakeChromeOpener(profile_directory="Profile 3")
    runtime: FakeAutomationRuntime | None = None

    class AmbiguousChromeWindowManager:
        def list_chrome_windows(self) -> list[object]:
            return [
                WindowInfo(
                    handle=23,
                    title="Personal - Chrome",
                    bounds=(0, 0, 100, 100),
                    last_focused_at=1.0,
                ),
                WindowInfo(
                    handle=24,
                    title="Work - Chrome",
                    bounds=(0, 0, 100, 100),
                    last_focused_at=0.5,
                ),
            ]

    def runtime_factory(_emit_event):
        nonlocal runtime
        runtime = FakeAutomationRuntime()
        runtime.window_manager = AmbiguousChromeWindowManager()
        return runtime

    worker, _created_services, _pipelines, _listeners = build_worker(
        storage,
        events,
        timestamp,
        config=build_config(
            auto_run_enabled=True,
            bot_action_slots=build_bot_action_slots(),
        ),
        service_factory=lambda config: FakeService(
            config,
            detection_result_factory=detect_job_from_message,
        ),
        automation_runtime_factory=runtime_factory,
        chrome_opener_factory=lambda **kwargs: opener,
    )
    worker._service = worker._build_service(worker.config)

    outcome = worker._handle_message(build_message())

    assert outcome.kind == "job_detected"
    assert opener.open_calls == []
    assert opener.open_raid_window_calls == ["https://x.com/i/status/123"]
    assert runtime is not None
    assert runtime.run_calls == []
    assert [event for event in events if event["type"] == "automation_run_failed"] == [
        {
            "type": "automation_run_failed",
            "sequence_id": "bot-actions",
            "url": "https://x.com/i/status/123",
            "reason": "target_window_not_found",
            "profile_directory": "Profile 3",
        }
    ]
    assert worker.state.browser_session_failed == 1
    assert worker.state.open_failures == 1
    assert worker.state.last_error == "target_window_not_found"
    assert worker.state.automation_queue_state == "paused"
    assert worker.state.automation_queue_length == 0
    assert worker.state.automation_last_error == "target_window_not_found"
    assert worker.state.raid_profile_states == (
        RaidProfileState("Profile 3", "Profile 3", "red", "target_window_not_found"),
    )


def test_worker_continues_pending_queue_when_only_hidden_auto_run_flag_is_disabled_mid_run(
    tmp_path,
) -> None:
    events: list[dict] = []
    timestamp = datetime(2026, 3, 27, 10, 4, 0)
    storage = FakeStorage(base_dir=tmp_path)
    first_url = "https://x.com/i/status/333"
    second_url = "https://x.com/i/status/444"
    first_message = build_message(f"Likes 10 | 8 [%]\n\n{first_url}")
    second_message = build_message(f"Likes 10 | 8 [%]\n\n{second_url}")
    runtime: FakeAutomationRuntime | None = None
    opener = FakeChromeOpener(profile_directory="Profile 3")
    worker_ref: dict[str, object] = {}
    first_run_triggered = {"value": False}
    run_callback = lambda _sequence, _handle: None

    def runtime_factory(_emit_event):
        nonlocal runtime
        runtime = FakeAutomationRuntime(
            windows=[
                WindowInfo(
                    handle=11,
                    title="RaidBot - Chrome",
                    bounds=(0, 0, 100, 100),
                    last_focused_at=1.0,
                )
            ],
            on_run_sequence=lambda sequence, handle: run_callback(sequence, handle),
        )
        return runtime

    worker, _created_services, _pipelines, _listeners = build_worker(
        storage,
        events,
        timestamp,
        config=build_config(
            auto_run_enabled=True,
            bot_action_slots=build_bot_action_slots(),
        ),
        service_factory=lambda config: FakeService(
            config,
            detection_result_factory=detect_job_from_message,
        ),
        automation_runtime_factory=runtime_factory,
        chrome_opener_factory=lambda **kwargs: opener,
    )
    worker_ref["worker"] = worker
    worker._service = worker._build_service(worker.config)

    def disable_after_queue(_sequence, _handle):
        if not first_run_triggered["value"]:
            worker_ref["worker"]._handle_message(second_message)
            worker_ref["worker"].config.auto_run_enabled = False
            first_run_triggered["value"] = True
        return None

    run_callback = disable_after_queue
    outcome = worker._handle_message(first_message)

    assert outcome.kind == "job_detected"
    assert opener.open_calls == []
    assert opener.open_raid_window_calls == [first_url, second_url]
    assert runtime is not None
    assert runtime.run_calls == [("bot-actions", 11), ("bot-actions", 11)]
    assert runtime.input_driver.close_active_window_calls == 2
    assert runtime.input_driver.close_active_tab_calls == 0
    assert worker.state.automation_queue_state == "idle"
    assert worker.state.automation_queue_length == 0
    assert worker.state.automation_current_url is None
    assert worker.state.automation_last_error is None
    assert [entry.action for entry in worker.state.activity] == [
        "raid_detected",
        "auto_queued",
        "automation_started",
        "raid_detected",
        "auto_queued",
        "automation_succeeded",
        "session_closed",
        "automation_started",
        "automation_succeeded",
        "session_closed",
    ]


def test_worker_clear_automation_queue_preserves_running_state(tmp_path) -> None:
    events: list[dict] = []
    timestamp = datetime(2026, 3, 27, 10, 5, 0)
    storage = FakeStorage(base_dir=tmp_path)
    opener = FakeChromeOpener(profile_directory="Profile 3")
    runtime: FakeAutomationRuntime | None = None
    worker_ref: dict[str, object] = {}
    second_message = build_message("Likes 10 | 8 [%]\n\nhttps://x.com/i/status/555")
    clear_checked = {"value": False}

    def runtime_factory(_emit_event):
        nonlocal runtime

        def on_run_sequence(_sequence, _handle):
            if not clear_checked["value"]:
                clear_checked["value"] = True
                worker_ref["worker"].clear_automation_queue()
                worker_ref["worker"]._handle_message(second_message)
                assert runtime is not None
                assert runtime.run_calls == [("bot-actions", 7)]
            return None

        runtime = FakeAutomationRuntime(
            windows=[
                WindowInfo(
                    handle=7,
                    title="RaidBot - Chrome",
                    bounds=(0, 0, 100, 100),
                    last_focused_at=1.0,
                )
            ],
            on_run_sequence=on_run_sequence,
        )
        return runtime

    worker, _created_services, _pipelines, _listeners = build_worker(
        storage,
        events,
        timestamp,
        config=build_config(
            auto_run_enabled=True,
            bot_action_slots=build_bot_action_slots(),
        ),
        service_factory=lambda config: FakeService(
            config,
            detection_result_factory=detect_job_from_message,
        ),
        automation_runtime_factory=runtime_factory,
        chrome_opener_factory=lambda **kwargs: opener,
    )
    worker_ref["worker"] = worker
    worker._service = worker._build_service(worker.config)

    outcome = worker._handle_message(build_message("Likes 10 | 8 [%]\n\nhttps://x.com/i/status/444"))

    assert outcome.kind == "job_detected"
    assert opener.open_calls == []
    assert opener.open_raid_window_calls == [
        "https://x.com/i/status/444",
        "https://x.com/i/status/555",
    ]
    assert runtime is not None
    assert runtime.run_calls == [("bot-actions", 7), ("bot-actions", 7)]
    assert runtime.input_driver.close_active_window_calls == 2
    assert runtime.input_driver.close_active_tab_calls == 0
    assert worker.state.automation_queue_state == "idle"
    assert worker.state.automation_queue_length == 0
    assert worker.state.automation_current_url is None
    assert worker.state.automation_last_error is None


def test_worker_uses_legacy_pipeline_path_when_no_bot_action_slots_are_enabled(tmp_path) -> None:
    events: list[dict] = []
    timestamp = datetime(2026, 3, 27, 10, 5, 0)
    storage = FakeStorage(base_dir=tmp_path)
    pipeline = FakePipeline(
        build_config(),
        execution_result=RaidExecutionResult(
            kind="executor_not_configured",
            handed_off=True,
        ),
    )

    worker, _services, _pipelines, _listeners = build_worker(
        storage,
        events,
        timestamp,
        config=build_config(
            auto_run_enabled=False,
            bot_action_slots=build_bot_action_slots(enabled_keys=()),
        ),
        service_factory=lambda config: FakeService(
            config,
            detection_result_factory=detect_job_from_message,
        ),
        pipeline_factory=lambda _config: pipeline,
    )
    worker._service = worker._build_service(worker.config)
    worker._pipeline = pipeline
    dedupe_store = TrackingDedupeStore()
    worker._dedupe_store = dedupe_store

    outcome = worker._handle_message(build_message("Likes 10 | 8 [%]\n\nhttps://x.com/i/status/555"))

    assert outcome.kind == "job_detected"
    assert [call[0].normalized_url for call in pipeline.execute_calls] == [
        "https://x.com/i/status/555"
    ]
    assert pipeline.should_continue_results == [True]
    assert dedupe_store.mark_calls == ["https://x.com/i/status/555"]
    assert worker.state.automation_queue_state == "idle"
    assert worker.state.automation_queue_length == 0
    assert worker.state.automation_last_error is None
    assert [entry.action for entry in worker.state.activity] == [
        "raid_detected",
        "browser_session_opened",
        "executor_not_configured",
    ]


def test_worker_prefers_bot_action_auto_run_when_slots_are_enabled_even_if_hidden_flag_is_false(
    tmp_path,
) -> None:
    events: list[dict] = []
    timestamp = datetime(2026, 3, 27, 10, 5, 15)
    storage = FakeStorage(base_dir=tmp_path)
    opener = FakeChromeOpener(profile_directory="Profile 3")
    runtime: FakeAutomationRuntime | None = None
    pipeline = FakePipeline(build_config())

    def runtime_factory(_emit_event):
        nonlocal runtime
        runtime = FakeAutomationRuntime(
            windows=[
                WindowInfo(
                    handle=17,
                    title="RaidBot - Chrome",
                    bounds=(0, 0, 100, 100),
                    last_focused_at=1.0,
                )
            ],
        )
        return runtime

    worker, _services, _pipelines, _listeners = build_worker(
        storage,
        events,
        timestamp,
        config=build_config(
            auto_run_enabled=False,
            bot_action_slots=build_bot_action_slots(enabled_keys=("slot_1_r",)),
        ),
        service_factory=lambda config: FakeService(
            config,
            detection_result_factory=detect_job_from_message,
        ),
        pipeline_factory=lambda _config: pipeline,
        automation_runtime_factory=runtime_factory,
        chrome_opener_factory=lambda **kwargs: opener,
    )
    worker._service = worker._build_service(worker.config)
    worker._pipeline = pipeline

    outcome = worker._handle_message(build_message("Likes 10 | 8 [%]\n\nhttps://x.com/i/status/515"))

    assert outcome.kind == "job_detected"
    assert pipeline.execute_calls == []
    assert opener.open_calls == []
    assert opener.open_raid_window_calls == ["https://x.com/i/status/515"]
    assert runtime is not None
    assert runtime.run_calls == [("bot-actions", 17)]


def test_worker_preserves_reserved_url_duplicate_guard_when_auto_run_is_disabled(
    tmp_path,
) -> None:
    events: list[dict] = []
    timestamp = datetime(2026, 3, 27, 10, 5, 30)
    storage = FakeStorage(base_dir=tmp_path)
    pipeline = FakePipeline(
        build_config(),
        execution_result=RaidExecutionResult(
            kind="executor_not_configured",
            handed_off=True,
        ),
    )

    worker, _services, _pipelines, _listeners = build_worker(
        storage,
        events,
        timestamp,
        config=build_config(
            auto_run_enabled=False,
            bot_action_slots=build_bot_action_slots(),
        ),
        service_factory=lambda config: FakeService(
            config,
            detection_result_factory=detect_job_from_message,
        ),
        pipeline_factory=lambda _config: pipeline,
    )
    worker._service = worker._build_service(worker.config)
    worker._pipeline = pipeline
    worker._automation_reserved_urls.add("https://x.com/i/status/555")
    dedupe_store = TrackingDedupeStore()
    worker._dedupe_store = dedupe_store

    outcome = worker._handle_message(build_message("Likes 10 | 8 [%]\n\nhttps://x.com/i/status/555"))

    assert outcome.kind == "duplicate"
    assert pipeline.execute_calls == []
    assert dedupe_store.mark_calls == []
    assert [entry.action for entry in worker.state.activity] == [
        "raid_detected",
        "duplicate",
    ]


def test_worker_marks_profile_red_when_window_open_fails(tmp_path) -> None:
    events: list[dict] = []
    timestamp = datetime(2026, 3, 27, 10, 10, 0)
    storage = FakeStorage(base_dir=tmp_path)
    opener = FailingChromeOpener(profile_directory="Profile 3")
    runtime: FakeAutomationRuntime | None = None

    def runtime_factory(_emit_event):
        nonlocal runtime
        runtime = FakeAutomationRuntime(
            windows=[
                WindowInfo(
                    handle=9,
                    title="RaidBot - Chrome",
                    bounds=(0, 0, 100, 100),
                    last_focused_at=1.0,
                )
            ],
        )
        return runtime

    worker, _services, _pipelines, _listeners = build_worker(
        storage,
        events,
        timestamp,
        config=build_config(
            auto_run_enabled=True,
            bot_action_slots=build_bot_action_slots(),
        ),
        service_factory=lambda config: FakeService(
            config,
            detection_result_factory=detect_job_from_message,
        ),
        automation_runtime_factory=runtime_factory,
        chrome_opener_factory=lambda **kwargs: opener,
    )
    worker._service = worker._build_service(worker.config)

    outcome = worker._handle_message(build_message("Likes 10 | 8 [%]\n\nhttps://x.com/i/status/123"))

    assert outcome.kind == "job_detected"
    assert opener.open_calls == []
    assert opener.open_raid_window_calls == ["https://x.com/i/status/123"]
    assert runtime is not None
    assert runtime.run_calls == []
    assert runtime.input_driver.close_active_tab_calls == 0
    assert worker.state.raids_opened == 0
    assert worker.state.browser_session_failed == 1
    assert worker.state.open_failures == 1
    assert worker.state.last_error == "browser_startup_failure"
    assert worker.state.automation_queue_state == "paused"
    assert worker.state.automation_queue_length == 0
    assert worker.state.automation_current_url is None
    assert worker.state.automation_last_error == "browser_startup_failure"
    assert worker.state.raid_profile_states == (
        RaidProfileState("Profile 3", "Profile 3", "red", "browser_startup_failure"),
    )
    assert [entry.action for entry in worker.state.activity] == [
        "raid_detected",
        "auto_queued",
        "automation_failed",
    ]
    assert any(
        event == {"type": "error", "message": "browser_startup_failure"}
        for event in events
    )


def test_worker_missing_bot_action_slots_pause_without_run_failed_event_or_open_failure(
    tmp_path,
) -> None:
    events: list[dict] = []
    timestamp = datetime(2026, 3, 27, 10, 10, 30)
    storage = FakeStorage(base_dir=tmp_path)

    worker, _services, _pipelines, _listeners = build_worker(
        storage,
        events,
        timestamp,
        config=build_config(
            auto_run_enabled=True,
            bot_action_slots=build_bot_action_slots(enabled_keys=()),
        ),
        service_factory=lambda config: FakeService(
            config,
            detection_result_factory=detect_job_from_message,
        ),
    )
    worker._service = worker._build_service(worker.config)

    outcome = worker._handle_message(
        build_message("Likes 10 | 8 [%]\n\nhttps://x.com/i/status/987")
    )

    assert outcome.kind == "job_detected"
    assert [event for event in events if event["type"] == "automation_run_failed"] == []
    assert [event for event in events if event["type"] == "automation_run_started"] == []
    assert worker.state.browser_session_failed == 0
    assert worker.state.open_failures == 0
    assert worker.state.automation_queue_state == "paused"
    assert worker.state.automation_queue_length == 0
    assert worker.state.automation_last_error == "bot_action_not_configured"


@pytest.mark.parametrize("failure_reason", ["navigation_failure", "page_ready_timeout"])
def test_worker_leaves_failed_window_open_and_marks_profile_red(
    tmp_path,
    failure_reason: str,
) -> None:
    events: list[dict] = []
    timestamp = datetime(2026, 3, 27, 10, 12, 0)
    storage = FakeStorage(base_dir=tmp_path)
    opener = FakeChromeOpener(profile_directory="Profile 3")
    runtime: FakeAutomationRuntime | None = None

    def runtime_factory(_emit_event):
        nonlocal runtime
        runtime = FakeAutomationRuntime(
            windows=[
                WindowInfo(
                    handle=13,
                    title="RaidBot - Chrome",
                    bounds=(0, 0, 100, 100),
                    last_focused_at=1.0,
                )
            ],
            run_sequence_results=[
                RunResult(status="failed", failure_reason=failure_reason)
            ],
        )
        return runtime

    worker, _services, _pipelines, _listeners = build_worker(
        storage,
        events,
        timestamp,
        config=build_config(
            auto_run_enabled=True,
            bot_action_slots=build_bot_action_slots(),
        ),
        service_factory=lambda config: FakeService(
            config,
            detection_result_factory=detect_job_from_message,
        ),
        automation_runtime_factory=runtime_factory,
        chrome_opener_factory=lambda **kwargs: opener,
    )
    worker._service = worker._build_service(worker.config)

    outcome = worker._handle_message(build_message("Likes 10 | 8 [%]\n\nhttps://x.com/i/status/123"))

    assert outcome.kind == "job_detected"
    assert opener.open_calls == []
    assert opener.open_raid_window_calls == ["https://x.com/i/status/123"]
    assert runtime is not None
    assert runtime.run_calls == [("bot-actions", 13)]
    assert runtime.input_driver.close_active_tab_calls == 0
    assert worker.state.raids_opened == 1
    assert worker.state.last_successful_raid_open_at == "2026-03-27T10:12:00"
    assert worker.state.browser_session_failed == 1
    assert worker.state.session_closed == 0
    assert worker.state.last_error == failure_reason
    assert worker.state.automation_queue_state == "paused"
    assert worker.state.automation_queue_length == 0
    assert worker.state.automation_current_url is None
    assert worker.state.automation_last_error == failure_reason
    assert worker.state.raid_profile_states == (
        RaidProfileState("Profile 3", "Profile 3", "red", failure_reason),
    )
    assert [entry.action for entry in worker.state.activity] == [
        "raid_detected",
        "auto_queued",
        "automation_started",
        "automation_failed",
    ]
    assert any(event == {"type": "error", "message": failure_reason} for event in events)


def test_worker_waits_for_page_ready_before_running_sequence(tmp_path) -> None:
    events: list[dict] = []
    timestamp = datetime(2026, 3, 27, 10, 12, 30)
    storage = FakeStorage(base_dir=tmp_path)
    opener = FakeChromeOpener(profile_directory="Profile 3")
    runtime: FakeAutomationRuntime | None = None
    page_ready_path = tmp_path / "page_ready.png"
    page_ready_path.write_bytes(b"capture")

    def runtime_factory(_emit_event):
        nonlocal runtime
        runtime = FakeAutomationRuntime(
            windows=[
                WindowInfo(
                    handle=15,
                    title="RaidBot - Chrome",
                    bounds=(0, 0, 100, 100),
                    last_focused_at=1.0,
                )
            ],
        )
        return runtime

    worker, _services, _pipelines, _listeners = build_worker(
        storage,
        events,
        timestamp,
        config=build_config(
            auto_run_enabled=True,
            page_ready_template_path=page_ready_path,
            bot_action_slots=build_bot_action_slots(enabled_keys=("slot_2_l",)),
        ),
        service_factory=lambda config: FakeService(
            config,
            detection_result_factory=detect_job_from_message,
        ),
        automation_runtime_factory=runtime_factory,
        chrome_opener_factory=lambda **kwargs: opener,
    )
    worker._service = worker._build_service(worker.config)

    outcome = worker._handle_message(
        build_message("Likes 10 | 8 [%]\n\nhttps://x.com/i/status/222")
    )

    assert outcome.kind == "job_detected"
    assert runtime is not None
    assert runtime.wait_for_step_calls == [(page_ready_path, 15)]
    assert runtime.run_calls == [("bot-actions", 15)]


def test_worker_marks_profile_failed_when_page_ready_never_appears(tmp_path) -> None:
    events: list[dict] = []
    timestamp = datetime(2026, 3, 27, 10, 12, 45)
    storage = FakeStorage(base_dir=tmp_path)
    opener = FakeChromeOpener(profile_directory="Profile 3")
    runtime: FakeAutomationRuntime | None = None
    page_ready_path = tmp_path / "page_ready.png"
    page_ready_path.write_bytes(b"capture")

    def runtime_factory(_emit_event):
        nonlocal runtime
        runtime = FakeAutomationRuntime(
            windows=[
                WindowInfo(
                    handle=18,
                    title="RaidBot - Chrome",
                    bounds=(0, 0, 100, 100),
                    last_focused_at=1.0,
                )
            ],
            wait_for_step_result=RunResult(
                status="failed",
                failure_reason="match_not_found",
                window_handle=18,
                step_index=0,
            ),
        )
        return runtime

    worker, _services, _pipelines, _listeners = build_worker(
        storage,
        events,
        timestamp,
        config=build_config(
            auto_run_enabled=True,
            page_ready_template_path=page_ready_path,
            bot_action_slots=build_bot_action_slots(enabled_keys=("slot_2_l",)),
        ),
        service_factory=lambda config: FakeService(
            config,
            detection_result_factory=detect_job_from_message,
        ),
        automation_runtime_factory=runtime_factory,
        chrome_opener_factory=lambda **kwargs: opener,
    )
    worker._service = worker._build_service(worker.config)

    outcome = worker._handle_message(
        build_message("Likes 10 | 8 [%]\n\nhttps://x.com/i/status/333")
    )

    assert outcome.kind == "job_detected"
    assert runtime is not None
    assert runtime.wait_for_step_calls == [(page_ready_path, 18)]
    assert runtime.run_calls == []
    assert worker.state.raids_detected == 1
    assert worker.state.raids_opened == 1
    assert worker.state.raids_completed == 0
    assert worker.state.raids_failed == 1
    assert worker.state.raid_profile_states == (
        RaidProfileState("Profile 3", "Profile 3", "red", "page_ready_not_found"),
    )


def test_worker_pauses_when_all_raid_profiles_are_blocked(tmp_path) -> None:
    events: list[dict] = []
    timestamp = datetime(2026, 3, 27, 10, 13, 30)
    storage = FakeStorage(
        DesktopAppState(
            raid_profile_states=(
                RaidProfileState("Default", "George", "red", "not_logged_in"),
                RaidProfileState("Profile 3", "Maria", "red", "session_expired"),
            )
        ),
        base_dir=tmp_path,
    )
    opener = FakeChromeOpener(profile_directory="Default")
    runtime: FakeAutomationRuntime | None = None

    def runtime_factory(_emit_event):
        nonlocal runtime
        runtime = FakeAutomationRuntime(
            windows=[
                WindowInfo(
                    handle=21,
                    title="RaidBot - Chrome",
                    bounds=(0, 0, 100, 100),
                    last_focused_at=1.0,
                )
            ],
        )
        return runtime

    worker, _services, _pipelines, _listeners = build_worker(
        storage,
        events,
        timestamp,
        config=build_config(
            auto_run_enabled=True,
            raid_profiles=(
                RaidProfileConfig("Default", "George", True),
                RaidProfileConfig("Profile 3", "Maria", True),
            ),
            bot_action_slots=build_bot_action_slots(enabled_keys=("slot_2_l",)),
        ),
        service_factory=lambda config: FakeService(
            config,
            detection_result_factory=detect_job_from_message,
        ),
        automation_runtime_factory=runtime_factory,
        chrome_opener_factory=lambda **kwargs: opener,
    )
    worker._service = worker._build_service(worker.config)

    outcome = worker._handle_message(
        build_message("Likes 10 | 8 [%]\n\nhttps://x.com/i/status/444")
    )

    assert outcome.kind == "job_detected"
    assert opener.open_calls == []
    assert opener.open_raid_window_calls == []
    assert worker.state.raids_detected == 1
    assert worker.state.raids_opened == 0
    assert worker.state.raids_completed == 0
    assert worker.state.raids_failed == 0
    assert worker.state.automation_queue_state == "paused"
    assert worker.state.automation_last_error == "all_profiles_blocked"
    assert any(event == {"type": "error", "message": "all_profiles_blocked"} for event in events)


def test_worker_skips_page_ready_probe_when_template_not_configured(tmp_path) -> None:
    events: list[dict] = []
    timestamp = datetime(2026, 3, 27, 10, 13, 0)
    storage = FakeStorage(base_dir=tmp_path)
    opener = FakeChromeOpener(profile_directory="Profile 3")
    runtime: FakeAutomationRuntime | None = None

    def runtime_factory(_emit_event):
        nonlocal runtime
        runtime = FakeAutomationRuntime(
            windows=[
                WindowInfo(
                    handle=21,
                    title="RaidBot - Chrome",
                    bounds=(0, 0, 100, 100),
                    last_focused_at=1.0,
                )
            ],
        )
        return runtime

    worker, _services, _pipelines, _listeners = build_worker(
        storage,
        events,
        timestamp,
        config=build_config(
            auto_run_enabled=True,
            bot_action_slots=build_bot_action_slots(enabled_keys=("slot_2_l",)),
        ),
        service_factory=lambda config: FakeService(
            config,
            detection_result_factory=detect_job_from_message,
        ),
        automation_runtime_factory=runtime_factory,
        chrome_opener_factory=lambda **kwargs: opener,
    )
    worker._service = worker._build_service(worker.config)

    outcome = worker._handle_message(
        build_message("Likes 10 | 8 [%]\n\nhttps://x.com/i/status/444")
    )

    assert outcome.kind == "job_detected"
    assert runtime is not None
    assert runtime.wait_for_step_calls == []
    assert runtime.run_calls == [("bot-actions", 21)]


def test_worker_skips_failed_profile_until_restarted(tmp_path) -> None:
    events: list[dict] = []
    timestamp = datetime(2026, 3, 27, 10, 11, 0)
    storage = FakeStorage(base_dir=tmp_path)
    opener = FlakyChromeOpener(profile_directory="Profile 3")
    runtime: FakeAutomationRuntime | None = None
    second_message = build_message("Likes 10 | 8 [%]\n\nhttps://x.com/i/status/456")
    third_message = build_message("Likes 10 | 8 [%]\n\nhttps://x.com/i/status/789")

    def runtime_factory(_emit_event):
        nonlocal runtime
        runtime = FakeAutomationRuntime(
            windows=[
                WindowInfo(
                    handle=10,
                    title="RaidBot - Chrome",
                    bounds=(0, 0, 100, 100),
                    last_focused_at=1.0,
                )
            ],
        )
        return runtime

    worker, _services, _pipelines, _listeners = build_worker(
        storage,
        events,
        timestamp,
        config=build_config(
            auto_run_enabled=True,
            bot_action_slots=build_bot_action_slots(),
        ),
        service_factory=lambda config: FakeService(
            config,
            detection_result_factory=detect_job_from_message,
        ),
        automation_runtime_factory=runtime_factory,
        chrome_opener_factory=lambda **kwargs: opener,
    )
    worker._service = worker._build_service(worker.config)

    first_outcome = worker._handle_message(build_message("Likes 10 | 8 [%]\n\nhttps://x.com/i/status/123"))
    second_outcome = worker._handle_message(second_message)
    worker.restart_raid_profile("Profile 3")
    third_outcome = worker._handle_message(third_message)

    assert first_outcome.kind == "job_detected"
    assert second_outcome.kind == "job_detected"
    assert third_outcome.kind == "job_detected"
    assert opener.open_calls == []
    assert opener.open_raid_window_calls == [
        "https://x.com/i/status/123",
        "https://x.com/i/status/789",
    ]
    assert runtime is not None
    assert runtime.run_calls == [("bot-actions", 10)]
    assert runtime.input_driver.close_active_window_calls == 1
    assert runtime.input_driver.close_active_tab_calls == 0
    assert worker.state.browser_session_failed == 1
    assert worker.state.automation_queue_state == "idle"
    assert worker.state.automation_queue_length == 0
    assert worker.state.automation_current_url is None
    assert worker.state.automation_last_error is None
    assert worker.state.raid_profile_states == (
        RaidProfileState("Profile 3", "Profile 3", "green", None),
    )


def test_worker_opens_fresh_raid_window_and_runs_against_detected_opened_handle(
    tmp_path,
) -> None:
    events: list[dict] = []
    timestamp = datetime(2026, 3, 27, 10, 11, 30)
    storage = FakeStorage(base_dir=tmp_path)
    runtime: FakeAutomationRuntime | None = None

    initial_window = WindowInfo(
        handle=7,
        title="Personal - Chrome",
        bounds=(0, 0, 100, 100),
        last_focused_at=2.0,
    )
    new_raid_window = WindowInfo(
        handle=9,
        title="Raid - Chrome",
        bounds=(100, 100, 300, 300),
        last_focused_at=1.0,
    )

    def runtime_factory(_emit_event):
        nonlocal runtime
        runtime = FakeAutomationRuntime(windows=[initial_window])
        return runtime

    class DedicatedWindowOpener(FakeChromeOpener):
        def open_raid_window(self, url: str) -> OpenedRaidContext:
            context = super().open_raid_window(url)
            assert runtime is not None
            runtime.window_manager.windows = [initial_window, new_raid_window]
            return context

    opener = DedicatedWindowOpener(profile_directory="Profile 3")
    worker, _services, _pipelines, _listeners = build_worker(
        storage,
        events,
        timestamp,
        config=build_config(
            auto_run_enabled=True,
            bot_action_slots=build_bot_action_slots(enabled_keys=("slot_2_l",)),
        ),
        service_factory=lambda config: FakeService(
            config,
            detection_result_factory=detect_job_from_message,
        ),
        automation_runtime_factory=runtime_factory,
        chrome_opener_factory=lambda **kwargs: opener,
        auto_run_wait=lambda _seconds: None,
    )
    worker._service = worker._build_service(worker.config)

    outcome = worker._handle_message(
        build_message("Likes 10 | 8 [%]\n\nhttps://x.com/i/status/777")
    )

    assert outcome.kind == "job_detected"
    assert opener.open_calls == []
    assert opener.open_raid_window_calls == ["https://x.com/i/status/777"]
    assert runtime is not None
    assert runtime.run_calls == [("bot-actions", 9)]


def test_worker_restart_raid_profile_clears_failed_state(tmp_path) -> None:
    events: list[dict] = []
    timestamp = datetime(2026, 3, 27, 10, 11, 45)
    storage = FakeStorage(
        DesktopAppState(
            raid_profile_states=(
                RaidProfileState("Profile 3", "Profile 3", "red", "not_logged_in"),
            )
        ),
        base_dir=tmp_path,
    )
    worker, _services, _pipelines, _listeners = build_worker(storage, events, timestamp)

    worker.restart_raid_profile("Profile 3")

    assert worker.state.raid_profile_states == (
        RaidProfileState("Profile 3", "Profile 3", "green", None),
    )
    assert events[-1]["type"] == "stats_changed"


def test_worker_skips_red_profile_and_continues_remaining_profiles_on_future_raids(
    tmp_path,
) -> None:
    events: list[dict] = []
    timestamp = datetime(2026, 3, 27, 10, 15, 0)
    storage = FakeStorage(base_dir=tmp_path)
    runtime = MultiProfileRuntime(
        run_results=[
            RunResult(status="failed", window_handle=41, failure_reason="not_logged_in"),
            RunResult(status="completed", window_handle=43),
            RunResult(status="completed", window_handle=43),
        ]
    )
    created_openers: list[WindowSpawningChromeOpener] = []
    handle_by_profile = {"Default": 41, "Profile 3": 43}

    def chrome_opener_factory(**kwargs):
        opener = WindowSpawningChromeOpener(
            runtime=runtime,
            handle_by_profile=handle_by_profile,
            **kwargs,
        )
        created_openers.append(opener)
        return opener

    worker, _services, _pipelines, _listeners = build_worker(
        storage,
        events,
        timestamp,
        config=build_config(
            chrome_profile_directory="Default",
            auto_run_enabled=True,
            raid_profiles=(
                RaidProfileConfig("Default", "George", True),
                RaidProfileConfig("Profile 3", "Maria", True),
            ),
            bot_action_slots=build_bot_action_slots(),
        ),
        service_factory=lambda config: FakeService(
            config,
            detection_result_factory=detect_job_from_message,
        ),
        automation_runtime_factory=lambda _emit_event: runtime,
        chrome_opener_factory=chrome_opener_factory,
    )
    worker._service = worker._build_service(worker.config)

    first_outcome = worker._handle_message(
        build_message("Likes 10 | 8 [%]\n\nhttps://x.com/i/status/333")
    )
    second_outcome = worker._handle_message(
        build_message("Likes 10 | 8 [%]\n\nhttps://x.com/i/status/444")
    )

    assert first_outcome.kind == "job_detected"
    assert second_outcome.kind == "job_detected"
    assert [opener.profile_directory for opener in created_openers] == ["Default", "Profile 3"]
    assert [opener.open_raid_window_calls for opener in created_openers] == [
        ["https://x.com/i/status/333"],
        ["https://x.com/i/status/333", "https://x.com/i/status/444"],
    ]
    assert runtime.run_calls == [
        ("bot-actions", 41),
        ("bot-actions", 43),
        ("bot-actions", 43),
    ]
    assert runtime.closed_window_handles == [43, 43]
    assert worker.state.raid_profile_states == (
        RaidProfileState("Default", "George", "red", "not_logged_in"),
        RaidProfileState("Profile 3", "Maria", "green", None),
    )


def test_worker_rejects_bot_action_queue_when_no_slots_are_enabled(tmp_path) -> None:
    events: list[dict] = []
    timestamp = datetime(2026, 3, 27, 10, 15, 30)
    storage = FakeStorage(base_dir=tmp_path)
    opener = FakeChromeOpener(profile_directory="Profile 3")
    runtime: FakeAutomationRuntime | None = None

    def runtime_factory(_emit_event):
        nonlocal runtime
        runtime = FakeAutomationRuntime(
            windows=[
                WindowInfo(
                    handle=18,
                    title="RaidBot - Chrome",
                    bounds=(0, 0, 100, 100),
                    last_focused_at=1.0,
                )
            ]
        )
        return runtime

    worker, _services, _pipelines, _listeners = build_worker(
        storage,
        events,
        timestamp,
        config=build_config(
            auto_run_enabled=True,
            bot_action_slots=build_bot_action_slots(enabled_keys=()),
        ),
        service_factory=lambda config: FakeService(
            config,
            detection_result_factory=detect_job_from_message,
        ),
        automation_runtime_factory=runtime_factory,
        chrome_opener_factory=lambda **kwargs: opener,
    )
    worker._service = worker._build_service(worker.config)

    outcome = worker._handle_message(build_message("Likes 10 | 8 [%]\n\nhttps://x.com/i/status/111"))

    assert outcome.kind == "job_detected"
    assert opener.open_calls == []
    assert runtime is None or runtime.run_calls == []
    assert worker.state.browser_session_failed == 0
    assert worker.state.open_failures == 0
    assert worker.state.automation_queue_state == "paused"
    assert worker.state.automation_queue_length == 0
    assert worker.state.automation_last_error == "bot_action_not_configured"


def test_worker_refuses_to_open_chrome_when_bot_action_captured_image_is_missing(
    tmp_path,
) -> None:
    events: list[dict] = []
    timestamp = datetime(2026, 3, 27, 10, 15, 45)
    storage = FakeStorage(base_dir=tmp_path)
    opener = FakeChromeOpener(profile_directory="Profile 3")
    runtime: FakeAutomationRuntime | None = None

    def runtime_factory(_emit_event):
        nonlocal runtime
        runtime = FakeAutomationRuntime(
            windows=[
                WindowInfo(
                    handle=19,
                    title="RaidBot - Chrome",
                    bounds=(0, 0, 100, 100),
                    last_focused_at=1.0,
                )
            ]
        )
        return runtime

    worker, _services, _pipelines, _listeners = build_worker(
        storage,
        events,
        timestamp,
        config=build_config(
            auto_run_enabled=True,
            bot_action_slots=build_bot_action_slots(
                enabled_keys=("slot_1_r", "slot_2_l"),
                missing_template_keys=("slot_2_l",),
            ),
        ),
        service_factory=lambda config: FakeService(
            config,
            detection_result_factory=detect_job_from_message,
        ),
        automation_runtime_factory=runtime_factory,
        chrome_opener_factory=lambda **kwargs: opener,
    )
    worker._service = worker._build_service(worker.config)

    outcome = worker._handle_message(build_message("Likes 10 | 8 [%]\n\nhttps://x.com/i/status/222"))

    assert outcome.kind == "job_detected"
    assert opener.open_calls == []
    assert runtime is None or runtime.run_calls == []
    assert worker.state.browser_session_failed == 0
    assert worker.state.open_failures == 0
    assert worker.state.automation_queue_state == "paused"
    assert worker.state.automation_queue_length == 0
    assert worker.state.automation_last_error == "captured_image_missing"


def test_worker_refuses_to_open_chrome_when_enabled_bot_action_template_file_is_missing_on_disk(
    tmp_path,
) -> None:
    events: list[dict] = []
    timestamp = datetime(2026, 3, 27, 10, 15, 50)
    storage = FakeStorage(base_dir=tmp_path)
    opener = FakeChromeOpener(profile_directory="Profile 3")
    runtime: FakeAutomationRuntime | None = None
    slots = list(build_bot_action_slots(enabled_keys=("slot_1_r",)))
    slots[0] = BotActionSlotConfig(
        key=slots[0].key,
        label=slots[0].label,
        enabled=True,
        template_path=tmp_path / "missing-slot-template.png",
    )

    def runtime_factory(_emit_event):
        nonlocal runtime
        runtime = FakeAutomationRuntime(
            windows=[
                WindowInfo(
                    handle=20,
                    title="RaidBot - Chrome",
                    bounds=(0, 0, 100, 100),
                    last_focused_at=1.0,
                )
            ]
        )
        return runtime

    worker, _services, _pipelines, _listeners = build_worker(
        storage,
        events,
        timestamp,
        config=build_config(
            auto_run_enabled=True,
            bot_action_slots=tuple(slots),
        ),
        service_factory=lambda config: FakeService(
            config,
            detection_result_factory=detect_job_from_message,
        ),
        automation_runtime_factory=runtime_factory,
        chrome_opener_factory=lambda **kwargs: opener,
    )
    worker._service = worker._build_service(worker.config)

    outcome = worker._handle_message(build_message("Likes 10 | 8 [%]\n\nhttps://x.com/i/status/333"))

    assert outcome.kind == "job_detected"
    assert opener.open_calls == []
    assert runtime is None or runtime.run_calls == []
    assert worker.state.browser_session_failed == 0
    assert worker.state.open_failures == 0
    assert worker.state.automation_queue_state == "paused"
    assert worker.state.automation_queue_length == 0
    assert worker.state.automation_last_error == "captured_image_missing"


def test_worker_skips_slot_1_when_no_presets_exist_but_runs_later_slots() -> None:
    events: list[dict] = []
    timestamp = datetime(2026, 3, 27, 10, 18, 0)
    storage = FakeStorage()
    opener = FakeChromeOpener(profile_directory="Profile 3")
    runtime: FakeAutomationRuntime | None = None

    def runtime_factory(_emit_event):
        nonlocal runtime
        runtime = FakeAutomationRuntime(
            windows=[
                WindowInfo(
                    handle=21,
                    title="RaidBot - Chrome",
                    bounds=(0, 0, 100, 100),
                    last_focused_at=1.0,
                )
            ]
        )
        return runtime

    worker, _services, _pipelines, _listeners = build_worker(
        storage,
        events,
        timestamp,
        config=build_config(
            auto_run_enabled=True,
            bot_action_slots=build_bot_action_slots(
                enabled_keys=("slot_1_r", "slot_2_l"),
                slot_1_presets=(),
                slot_1_finish_template_path=None,
            ),
        ),
        service_factory=lambda config: FakeService(
            config,
            detection_result_factory=detect_job_from_message,
        ),
        automation_runtime_factory=runtime_factory,
        chrome_opener_factory=lambda **kwargs: opener,
    )
    worker._service = worker._build_service(worker.config)

    outcome = worker._handle_message(build_message("Likes 10 | 8 [%]\n\nhttps://x.com/i/status/444"))

    assert outcome.kind == "job_detected"
    assert opener.open_raid_window_calls == ["https://x.com/i/status/444"]
    assert runtime is not None
    assert runtime.run_calls == [("bot-actions", 21)]
    assert [step.name for step in runtime.run_sequences[0].steps] == ["slot_2_l"]
    assert any(
        event.get("type") == "automation_runtime_event"
        and isinstance(event.get("event"), dict)
        and event["event"].get("reason") == "no_presets_configured"
        for event in events
    )


def test_worker_clear_automation_queue_does_not_reenable_failed_profile(tmp_path) -> None:
    events: list[dict] = []
    timestamp = datetime(2026, 3, 27, 10, 20, 0)
    storage = FakeStorage(base_dir=tmp_path)
    opener = FakeChromeOpener(profile_directory="Profile 3")
    runtime: FakeAutomationRuntime | None = None
    third_message = build_message("Likes 10 | 8 [%]\n\nhttps://x.com/i/status/777")

    def runtime_factory(_emit_event):
        nonlocal runtime
        runtime = FakeAutomationRuntime(
            windows=[
                WindowInfo(
                    handle=23,
                    title="RaidBot - Chrome",
                    bounds=(0, 0, 100, 100),
                    last_focused_at=1.0,
                )
            ],
        )
        return runtime

    worker, _services, _pipelines, _listeners = build_worker(
        storage,
        events,
        timestamp,
        config=build_config(
            auto_run_enabled=True,
            bot_action_slots=build_bot_action_slots(),
        ),
        service_factory=lambda config: FakeService(
            config,
            detection_result_factory=detect_job_from_message,
        ),
        automation_runtime_factory=runtime_factory,
        chrome_opener_factory=lambda **kwargs: opener,
    )
    worker._service = worker._build_service(worker.config)

    runtime_factory_called = {"value": False}

    def runtime_factory_with_failure(_emit_event):
        runtime_factory_called["value"] = True
        nonlocal runtime
        runtime = FakeAutomationRuntime(
            windows=[
                WindowInfo(
                    handle=23,
                    title="RaidBot - Chrome",
                    bounds=(0, 0, 100, 100),
                    last_focused_at=1.0,
                )
            ],
            run_sequence_results=[
                RunResult(status="failed", failure_reason="ui_did_not_change")
            ],
        )
        return runtime

    worker.automation_runtime_factory = runtime_factory_with_failure
    outcome = worker._handle_message(build_message("Likes 10 | 8 [%]\n\nhttps://x.com/i/status/555"))
    assert outcome.kind == "job_detected"

    worker.clear_automation_queue()
    recovery_outcome = worker._handle_message(third_message)

    assert runtime_factory_called["value"] is True
    assert recovery_outcome.kind == "job_detected"
    assert opener.open_calls == []
    assert opener.open_raid_window_calls == [
        "https://x.com/i/status/555",
    ]
    assert runtime is not None
    assert runtime.run_calls == [("bot-actions", 23)]
    assert runtime.input_driver.close_active_window_calls == 0
    assert runtime.input_driver.close_active_tab_calls == 0
    assert worker.state.automation_queue_state == "paused"
    assert worker.state.automation_queue_length == 0
    assert worker.state.automation_current_url is None
    assert worker.state.automation_last_error == "all_profiles_blocked"
    assert worker.state.raid_profile_states == (
        RaidProfileState("Profile 3", "Profile 3", "red", "ui_did_not_change"),
    )


def test_worker_resume_automation_queue_recovers_after_bot_action_slots_are_configured(
    tmp_path,
) -> None:
    events: list[dict] = []
    timestamp = datetime(2026, 3, 27, 10, 22, 0)
    storage = FakeStorage(base_dir=tmp_path)
    opener = FakeChromeOpener(profile_directory="Profile 3")
    runtime: FakeAutomationRuntime | None = None
    first_message = build_message("Likes 10 | 8 [%]\n\nhttps://x.com/i/status/888")
    second_message = build_message("Likes 10 | 8 [%]\n\nhttps://x.com/i/status/999")

    def runtime_factory(_emit_event):
        nonlocal runtime
        runtime = FakeAutomationRuntime(
            windows=[
                WindowInfo(
                    handle=29,
                    title="RaidBot - Chrome",
                    bounds=(0, 0, 100, 100),
                    last_focused_at=1.0,
                )
            ],
        )
        return runtime

    worker, _services, _pipelines, _listeners = build_worker(
        storage,
        events,
        timestamp,
        config=build_config(
            auto_run_enabled=True,
            bot_action_slots=build_bot_action_slots(enabled_keys=()),
        ),
        service_factory=lambda config: FakeService(
            config,
            detection_result_factory=detect_job_from_message,
        ),
        automation_runtime_factory=runtime_factory,
        chrome_opener_factory=lambda **kwargs: opener,
    )
    worker._service = worker._build_service(worker.config)

    first_outcome = worker._handle_message(first_message)
    worker.config.bot_action_slots = build_bot_action_slots()
    worker.resume_automation_queue()
    second_outcome = worker._handle_message(second_message)

    assert first_outcome.kind == "job_detected"
    assert second_outcome.kind == "job_detected"
    assert opener.open_calls == []
    assert opener.open_raid_window_calls == [
        "https://x.com/i/status/888",
        "https://x.com/i/status/999",
    ]
    assert runtime is not None
    assert runtime.run_calls == [("bot-actions", 29), ("bot-actions", 29)]
    assert runtime.input_driver.close_active_window_calls == 2
    assert runtime.input_driver.close_active_tab_calls == 0
    assert worker.state.automation_queue_state == "idle"
    assert worker.state.automation_queue_length == 0
    assert worker.state.automation_current_url is None
    assert worker.state.automation_last_error is None
    assert [entry.action for entry in worker.state.activity] == [
        "raid_detected",
        "automation_failed",
        "automation_started",
        "automation_succeeded",
        "session_closed",
        "raid_detected",
        "auto_queued",
        "automation_started",
        "automation_succeeded",
        "session_closed",
    ]


def test_worker_preserves_dedupe_across_service_rebuilds(tmp_path) -> None:
    events: list[dict] = []
    timestamp = datetime(2026, 3, 27, 10, 25, 0)
    storage = FakeStorage(base_dir=tmp_path)
    opener = FakeChromeOpener(profile_directory="Profile 3")
    runtime: FakeAutomationRuntime | None = None

    def runtime_factory(_emit_event):
        nonlocal runtime
        runtime = FakeAutomationRuntime(
            windows=[
                WindowInfo(
                    handle=31,
                    title="RaidBot - Chrome",
                    bounds=(0, 0, 100, 100),
                    last_focused_at=1.0,
                )
            ],
        )
        return runtime

    worker = build_default_worker(
        storage,
        events,
        timestamp,
        config=build_config(
            auto_run_enabled=True,
            bot_action_slots=build_bot_action_slots(),
        ),
        chrome_environment_factory=lambda: SimpleNamespace(
            chrome_path=Path(r"C:\Chrome\chrome.exe"),
            user_data_dir=Path(r"C:\Chrome\User Data"),
        ),
        automation_runtime_factory=runtime_factory,
        chrome_opener_factory=lambda **kwargs: opener,
    )
    worker._dedupe_store = TrackingDedupeStore()
    worker._service = worker._build_service(worker.config)

    first_outcome = worker._handle_message(build_message())
    worker._service = worker._build_service(worker.config)
    second_outcome = worker._handle_message(build_message())

    assert first_outcome.kind == "job_detected"
    assert second_outcome.kind == "duplicate"
    assert opener.open_calls == []
    assert opener.open_raid_window_calls == ["https://x.com/i/status/123"]
    assert runtime is not None
    assert runtime.run_calls == [("bot-actions", 31)]
    assert worker.state.duplicates_skipped == 1


def test_worker_loads_persisted_state_and_saves_updates() -> None:
    events: list[dict] = []
    timestamp = datetime(2026, 3, 27, 10, 30, 0)
    storage = FakeStorage(
        DesktopAppState(
            raids_opened=4,
            activity=[
                ActivityEntry(
                    timestamp=datetime(2026, 3, 27, 10, 0, 0),
                    action="browser_session_opened",
                    url="https://x.com/i/status/100",
                    reason="executor_not_configured",
                )
            ],
        )
    )
    worker, _services, _pipelines, _listeners = build_worker(storage, events, timestamp)

    worker._record_activity("sender_rejected", reason="sender_rejected")

    assert worker.state.raids_opened == 4
    assert worker.state.sender_rejected == 1
    assert len(worker.state.activity) == 2
    assert storage.saved_states[-1].sender_rejected == 1


def test_worker_restores_dedupe_from_persisted_automation_activity_on_startup(
    tmp_path,
) -> None:
    events: list[dict] = []
    timestamp = datetime(2026, 3, 27, 10, 32, 0)
    storage = FakeStorage(
        DesktopAppState(
            activity=[
                ActivityEntry(
                    timestamp=datetime(2026, 3, 27, 10, 0, 0),
                    action="automation_started",
                    url="https://x.com/i/status/100",
                    reason="automation_started",
                )
            ]
        ),
        base_dir=tmp_path,
    )
    opener = FakeChromeOpener(profile_directory="Profile 3")
    runtime: FakeAutomationRuntime | None = None

    def runtime_factory(_emit_event):
        nonlocal runtime
        runtime = FakeAutomationRuntime(
            windows=[
                WindowInfo(
                    handle=33,
                    title="RaidBot - Chrome",
                    bounds=(0, 0, 100, 100),
                    last_focused_at=1.0,
                )
            ],
        )
        return runtime

    worker = build_default_worker(
        storage,
        events,
        timestamp,
        config=build_config(
            auto_run_enabled=True,
            bot_action_slots=build_bot_action_slots(),
        ),
        chrome_environment_factory=lambda: SimpleNamespace(
            chrome_path=Path(r"C:\Chrome\chrome.exe"),
            user_data_dir=Path(r"C:\Chrome\User Data"),
        ),
        automation_runtime_factory=runtime_factory,
        chrome_opener_factory=lambda **kwargs: opener,
    )
    worker._service = worker._build_service(worker.config)

    outcome = worker._handle_message(
        build_message("Likes 10 | 8 [%]\n\nhttps://x.com/i/status/100")
    )

    assert outcome.kind == "duplicate"
    assert opener.open_raid_window_calls == []
    assert runtime is None
    assert worker.state.duplicates_skipped == 1


def test_worker_records_duplicate_detection_without_entering_error_state() -> None:
    events: list[dict] = []
    timestamp = datetime(2026, 3, 27, 10, 35, 0)
    storage = FakeStorage()
    worker, _services, _pipelines, _listeners = build_worker(storage, events, timestamp)

    worker.state.bot_state = BotRuntimeState.running
    worker._record_detection_result(
        RaidDetectionResult(
            kind="duplicate",
            normalized_url="https://x.com/i/status/100",
        )
    )

    assert worker.state.duplicates_skipped == 1
    assert worker.state.bot_state is BotRuntimeState.running
    assert worker.state.last_error is None
    assert worker.state.activity[-1] == ActivityEntry(
        timestamp=timestamp,
        action="duplicate",
        url="https://x.com/i/status/100",
        reason="duplicate",
    )
    assert [event["type"] for event in events] == ["stats_changed", "activity_added"]


@pytest.mark.asyncio
async def test_worker_run_emits_state_changes_and_stop_uses_listener() -> None:
    events: list[dict] = []
    timestamp = datetime(2026, 3, 27, 10, 40, 0)
    storage = FakeStorage()
    listener = FakeListener()

    worker, _services, _pipelines, _listeners = build_worker(
        storage,
        events,
        timestamp,
        listener_factory=lambda **kwargs: listener,
    )

    await worker.run()
    await worker.stop()

    assert listener.run_calls == 1
    assert listener.stop_calls == 1
    assert worker.state.bot_state is BotRuntimeState.stopped
    assert worker.state.connection_state is TelegramConnectionState.disconnected
    assert storage.saved_states[-1].bot_state is BotRuntimeState.stopped
    assert [event["type"] for event in events[:4]] == [
        "bot_state_changed",
        "connection_state_changed",
        "connection_state_changed",
        "bot_state_changed",
    ]
    connection_events = [
        event for event in events if event["type"] == "connection_state_changed"
    ]
    assert [event["state"] for event in connection_events] == [
        "connecting",
        "connected",
        "disconnected",
    ]


@pytest.mark.asyncio
async def test_worker_apply_config_updates_live_fields_without_restart() -> None:
    events: list[dict] = []
    timestamp = datetime(2026, 3, 27, 10, 45, 0)
    storage = FakeStorage()
    service = FakeService(build_config())
    pipeline = FakePipeline(build_config())
    worker, created_services, created_pipelines, created_listeners = build_worker(
        storage,
        events,
        timestamp,
    )

    worker._service = service
    worker._pipeline = pipeline
    worker._listener = FakeListener()
    new_config = build_config(
        whitelisted_chat_ids=[-1001, -2002],
        allowed_sender_ids=[99, 101],
        chrome_profile_directory="Profile 9",
        preset_replies=("gm", "lfg"),
        default_action_like=False,
        default_action_repost=False,
        default_action_bookmark=True,
        default_action_reply=False,
    )

    await worker.apply_config(new_config)

    assert worker.config == new_config
    assert worker._service.allowed_chat_ids == {-1001, -2002}
    assert worker._service.allowed_sender_ids == {99, 101}
    assert worker._service.preset_replies == ("gm", "lfg")
    assert worker._service.default_requirements == RaidActionRequirements(
        like=False,
        repost=False,
        bookmark=True,
        reply=False,
    )
    assert worker._pipeline._backend._launcher.profile_directory == "Profile 9"
    assert worker._listener.stop_calls == 0
    assert created_services == []
    assert created_pipelines == []
    assert created_listeners == []


@pytest.mark.asyncio
async def test_worker_apply_config_refreshes_auto_run_chrome_opener(tmp_path) -> None:
    events: list[dict] = []
    timestamp = datetime(2026, 3, 27, 10, 46, 0)
    storage = FakeStorage(base_dir=tmp_path)
    created_openers: list[FakeChromeOpener] = []
    runtime: FakeAutomationRuntime | None = None

    def chrome_opener_factory(**kwargs):
        opener = FakeChromeOpener(**kwargs)
        created_openers.append(opener)
        return opener

    def runtime_factory(_emit_event):
        nonlocal runtime
        runtime = FakeAutomationRuntime(
            windows=[
                WindowInfo(
                    handle=41,
                    title="RaidBot - Chrome",
                    bounds=(0, 0, 100, 100),
                    last_focused_at=1.0,
                )
            ],
        )
        return runtime

    worker, _services, _pipelines, _listeners = build_worker(
        storage,
        events,
        timestamp,
        config=build_config(
            auto_run_enabled=True,
            bot_action_slots=build_bot_action_slots(),
        ),
        service_factory=lambda config: FakeService(
            config,
            detection_result_factory=detect_job_from_message,
        ),
        automation_runtime_factory=runtime_factory,
        chrome_opener_factory=chrome_opener_factory,
    )
    worker._service = worker._build_service(worker.config)

    first_outcome = worker._handle_message(build_message("Likes 10 | 8 [%]\n\nhttps://x.com/i/status/123"))
    await worker.apply_config(
        build_config(
            chrome_profile_directory="Profile 9",
            auto_run_enabled=True,
            bot_action_slots=build_bot_action_slots(),
        )
    )
    second_outcome = worker._handle_message(build_message("Likes 10 | 8 [%]\n\nhttps://x.com/i/status/456"))

    assert first_outcome.kind == "job_detected"
    assert second_outcome.kind == "job_detected"
    assert [opener.profile_directory for opener in created_openers] == [
        "Profile 3",
        "Profile 9",
    ]
    assert [opener.open_calls for opener in created_openers] == [[], []]
    assert [opener.open_raid_window_calls for opener in created_openers] == [
        ["https://x.com/i/status/123"],
        ["https://x.com/i/status/456"],
    ]
    assert runtime is not None
    assert runtime.run_calls == [("bot-actions", 41), ("bot-actions", 41)]


@pytest.mark.asyncio
async def test_worker_apply_config_refreshes_auto_run_chrome_opener_on_telegram_restart(
    tmp_path,
) -> None:
    events: list[dict] = []
    timestamp = datetime(2026, 3, 27, 10, 46, 30)
    storage = FakeStorage(base_dir=tmp_path)
    created_openers: list[FakeChromeOpener] = []
    runtime: FakeAutomationRuntime | None = None

    def chrome_opener_factory(**kwargs):
        opener = FakeChromeOpener(**kwargs)
        created_openers.append(opener)
        return opener

    def runtime_factory(_emit_event):
        nonlocal runtime
        runtime = FakeAutomationRuntime(
            windows=[
                WindowInfo(
                    handle=43,
                    title="RaidBot - Chrome",
                    bounds=(0, 0, 100, 100),
                    last_focused_at=1.0,
                )
            ],
        )
        return runtime

    worker, _services, _pipelines, _listeners = build_worker(
        storage,
        events,
        timestamp,
        config=build_config(
            auto_run_enabled=True,
            bot_action_slots=build_bot_action_slots(),
        ),
        service_factory=lambda config: FakeService(
            config,
            detection_result_factory=detect_job_from_message,
        ),
        automation_runtime_factory=runtime_factory,
        chrome_opener_factory=chrome_opener_factory,
    )
    worker._service = worker._build_service(worker.config)
    worker._listener = FakeListener()

    first_outcome = worker._handle_message(build_message("Likes 10 | 8 [%]\n\nhttps://x.com/i/status/321"))
    await worker.apply_config(
        build_config(
            telegram_api_hash="new-hash",
            chrome_profile_directory="Profile 9",
            auto_run_enabled=True,
            bot_action_slots=build_bot_action_slots(),
        )
    )
    restart_requested = worker._restart_requested
    worker._restart_requested = False
    worker._service = worker._build_service(worker.config)
    second_outcome = worker._handle_message(build_message("Likes 10 | 8 [%]\n\nhttps://x.com/i/status/654"))

    assert first_outcome.kind == "job_detected"
    assert second_outcome.kind == "job_detected"
    assert restart_requested is True
    assert worker._listener.stop_calls == 1
    assert [opener.profile_directory for opener in created_openers] == [
        "Profile 3",
        "Profile 9",
    ]
    assert [opener.open_calls for opener in created_openers] == [[], []]
    assert [opener.open_raid_window_calls for opener in created_openers] == [
        ["https://x.com/i/status/321"],
        ["https://x.com/i/status/654"],
    ]
    assert runtime is not None
    assert runtime.run_calls == [("bot-actions", 43), ("bot-actions", 43)]


def test_worker_keeps_success_event_sequence_id_stable_when_config_changes_mid_run(
    tmp_path,
) -> None:
    events: list[dict] = []
    timestamp = datetime(2026, 3, 27, 10, 46, 45)
    storage = FakeStorage(base_dir=tmp_path)
    opener = FakeChromeOpener(profile_directory="Profile 3")
    runtime: FakeAutomationRuntime | None = None
    worker_ref: dict[str, object] = {}

    def runtime_factory(_emit_event):
        nonlocal runtime
        runtime = FakeAutomationRuntime(
            windows=[
                WindowInfo(
                    handle=45,
                    title="RaidBot - Chrome",
                    bounds=(0, 0, 100, 100),
                    last_focused_at=1.0,
                )
            ],
            on_run_sequence=lambda _sequence, _handle: setattr(
                worker_ref["worker"].config,
                "bot_action_slots",
                build_bot_action_slots(enabled_keys=("slot_2_l",)),
            ),
        )
        return runtime

    worker, _services, _pipelines, _listeners = build_worker(
        storage,
        events,
        timestamp,
        config=build_config(
            auto_run_enabled=True,
            bot_action_slots=build_bot_action_slots(),
        ),
        service_factory=lambda config: FakeService(
            config,
            detection_result_factory=detect_job_from_message,
        ),
        automation_runtime_factory=runtime_factory,
        chrome_opener_factory=lambda **kwargs: opener,
    )
    worker_ref["worker"] = worker
    worker._service = worker._build_service(worker.config)

    outcome = worker._handle_message(
        build_message("Likes 10 | 8 [%]\n\nhttps://x.com/i/status/321")
    )

    assert outcome.kind == "job_detected"
    run_events = [event for event in events if event["type"].startswith("automation_run_")]
    assert run_events == [
        {
            "type": "automation_run_started",
            "sequence_id": "bot-actions",
            "url": "https://x.com/i/status/321",
            "window_handle": 45,
            "profile_directory": "Profile 3",
        },
        {
            "type": "automation_run_succeeded",
            "sequence_id": "bot-actions",
            "url": "https://x.com/i/status/321",
            "profile_directory": "Profile 3",
        },
    ]


def test_worker_keeps_failure_event_sequence_id_stable_when_config_changes_mid_run(
    tmp_path,
) -> None:
    events: list[dict] = []
    timestamp = datetime(2026, 3, 27, 10, 46, 50)
    storage = FakeStorage(base_dir=tmp_path)
    opener = FakeChromeOpener(profile_directory="Profile 3")
    runtime: FakeAutomationRuntime | None = None
    worker_ref: dict[str, object] = {}

    def runtime_factory(_emit_event):
        nonlocal runtime
        runtime = FakeAutomationRuntime(
            windows=[
                WindowInfo(
                    handle=47,
                    title="RaidBot - Chrome",
                    bounds=(0, 0, 100, 100),
                    last_focused_at=1.0,
                )
            ],
            on_run_sequence=lambda _sequence, _handle: (
                setattr(
                    worker_ref["worker"].config,
                    "bot_action_slots",
                    build_bot_action_slots(enabled_keys=("slot_2_l",)),
                ),
                RunResult(status="failed", failure_reason="image_match_not_found"),
            )[1],
        )
        return runtime

    worker, _services, _pipelines, _listeners = build_worker(
        storage,
        events,
        timestamp,
        config=build_config(
            auto_run_enabled=True,
            bot_action_slots=build_bot_action_slots(),
        ),
        service_factory=lambda config: FakeService(
            config,
            detection_result_factory=detect_job_from_message,
        ),
        automation_runtime_factory=runtime_factory,
        chrome_opener_factory=lambda **kwargs: opener,
    )
    worker_ref["worker"] = worker
    worker._service = worker._build_service(worker.config)

    outcome = worker._handle_message(
        build_message("Likes 10 | 8 [%]\n\nhttps://x.com/i/status/654")
    )

    assert outcome.kind == "job_detected"
    run_events = [event for event in events if event["type"].startswith("automation_run_")]
    assert run_events == [
        {
            "type": "automation_run_started",
            "sequence_id": "bot-actions",
            "url": "https://x.com/i/status/654",
            "window_handle": 47,
            "profile_directory": "Profile 3",
        },
        {
            "type": "automation_run_failed",
            "sequence_id": "bot-actions",
            "url": "https://x.com/i/status/654",
            "reason": "image_match_not_found",
            "profile_directory": "Profile 3",
        },
    ]


def test_worker_does_not_corrupt_active_run_event_when_later_admission_fails_mid_run(
    tmp_path,
) -> None:
    events: list[dict] = []
    timestamp = datetime(2026, 3, 27, 10, 46, 55)
    storage = FakeStorage(base_dir=tmp_path)
    opener = FakeChromeOpener(profile_directory="Profile 3")
    runtime: FakeAutomationRuntime | None = None
    worker_ref: dict[str, object] = {}
    second_message = build_message("Likes 10 | 8 [%]\n\nhttps://x.com/i/status/999")

    def runtime_factory(_emit_event):
        nonlocal runtime
        runtime = FakeAutomationRuntime(
            windows=[
                WindowInfo(
                    handle=49,
                    title="RaidBot - Chrome",
                    bounds=(0, 0, 100, 100),
                    last_focused_at=1.0,
                )
            ],
            on_run_sequence=lambda _sequence, _handle: (
                setattr(
                    worker_ref["worker"].config,
                    "bot_action_slots",
                    build_bot_action_slots(enabled_keys=()),
                ),
                worker_ref["worker"]._handle_message(second_message),
                None,
            )[2],
        )
        return runtime

    worker, _services, _pipelines, _listeners = build_worker(
        storage,
        events,
        timestamp,
        config=build_config(
            auto_run_enabled=True,
            bot_action_slots=build_bot_action_slots(),
        ),
        service_factory=lambda config: FakeService(
            config,
            detection_result_factory=detect_job_from_message,
        ),
        automation_runtime_factory=runtime_factory,
        chrome_opener_factory=lambda **kwargs: opener,
    )
    worker_ref["worker"] = worker
    worker._service = worker._build_service(worker.config)

    outcome = worker._handle_message(
        build_message("Likes 10 | 8 [%]\n\nhttps://x.com/i/status/123")
    )

    assert outcome.kind == "job_detected"
    run_events = [event for event in events if event["type"].startswith("automation_run_")]
    assert run_events == [
        {
            "type": "automation_run_started",
            "sequence_id": "bot-actions",
            "url": "https://x.com/i/status/123",
            "window_handle": 49,
            "profile_directory": "Profile 3",
        },
        {
            "type": "automation_run_succeeded",
            "sequence_id": "bot-actions",
            "url": "https://x.com/i/status/123",
            "profile_directory": "Profile 3",
        },
    ]


def test_worker_build_service_uses_config_default_actions() -> None:
    events: list[dict] = []
    timestamp = datetime(2026, 3, 27, 10, 47, 0)
    storage = FakeStorage()
    worker = build_default_worker(
        storage,
        events,
        timestamp,
        config=build_config(
            default_action_like=False,
            default_action_repost=False,
            default_action_bookmark=True,
            default_action_reply=True,
        ),
        chrome_environment_factory=lambda: None,
    )

    service = worker._build_service(worker.config)
    result = service.handle_message(
        IncomingMessage(
            chat_id=-1001,
            sender_id=42,
            text="Likes 10 | 8 [%]\n\nhttps://x.com/i/status/123",
        )
    )

    assert result.kind == "job_detected"
    assert result.job is not None
    assert result.job.requirements == RaidActionRequirements(
        like=True,
        repost=False,
        bookmark=True,
        reply=True,
    )


@pytest.mark.asyncio
async def test_worker_apply_config_requests_restart_for_telegram_changes() -> None:
    events: list[dict] = []
    timestamp = datetime(2026, 3, 27, 10, 50, 0)
    storage = FakeStorage()
    worker, _services, _pipelines, _listeners = build_worker(storage, events, timestamp)

    worker._service = FakeService(worker.config)
    worker._pipeline = FakePipeline(worker.config)
    worker._listener = FakeListener()
    new_config = build_config(telegram_api_hash="new-hash")

    await worker.apply_config(new_config)

    assert worker.config == new_config
    assert worker._restart_requested is True
    assert worker._listener.stop_calls == 1


@pytest.mark.asyncio
async def test_worker_run_sets_stopped_state_when_listener_exits_normally() -> None:
    events: list[dict] = []
    timestamp = datetime(2026, 3, 27, 10, 55, 0)
    storage = FakeStorage()
    listener = FakeListener()

    worker, _services, _pipelines, _listeners = build_worker(
        storage,
        events,
        timestamp,
        listener_factory=lambda **kwargs: listener,
    )

    await worker.run()

    assert worker.state.bot_state is BotRuntimeState.stopped
    assert worker.state.connection_state is TelegramConnectionState.disconnected
    assert events[-1] == {"type": "bot_state_changed", "state": "stopped"}


@pytest.mark.asyncio
async def test_worker_run_reports_startup_service_build_failures_as_error_state() -> None:
    events: list[dict] = []
    timestamp = datetime(2026, 3, 27, 11, 0, 0)
    storage = FakeStorage()
    worker, _services, _pipelines, _listeners = build_worker(
        storage,
        events,
        timestamp,
        service_factory=lambda _config: (_ for _ in ()).throw(RuntimeError("service boom")),
    )

    with pytest.raises(RuntimeError, match="service boom"):
        await worker.run()

    assert worker.state.bot_state is BotRuntimeState.error
    assert worker.state.last_error == "service boom"
    assert storage.saved_states[-1].bot_state is BotRuntimeState.error
    assert events[-1] == {"type": "error", "message": "service boom"}


@pytest.mark.asyncio
async def test_worker_run_reports_startup_listener_build_failures_as_error_state() -> None:
    events: list[dict] = []
    timestamp = datetime(2026, 3, 27, 11, 5, 0)
    storage = FakeStorage()
    worker, _services, _pipelines, _listeners = build_worker(
        storage,
        events,
        timestamp,
        listener_factory=lambda **kwargs: (_ for _ in ()).throw(RuntimeError("listener boom")),
    )

    with pytest.raises(RuntimeError, match="listener boom"):
        await worker.run()

    assert worker.state.bot_state is BotRuntimeState.error
    assert worker.state.last_error == "listener boom"
    assert storage.saved_states[-1].bot_state is BotRuntimeState.error
    assert events[-1] == {"type": "error", "message": "listener boom"}


def test_worker_ignores_messages_after_stop_is_requested() -> None:
    events: list[dict] = []
    timestamp = datetime(2026, 3, 27, 11, 10, 0)
    storage = FakeStorage()
    handled_messages: list[IncomingMessage] = []

    class CountingService(FakeService):
        def handle_message(self, message: IncomingMessage) -> RaidDetectionResult:
            handled_messages.append(message)
            raise AssertionError("service should not receive messages after stop is requested")

    worker, _services, _pipelines, _listeners = build_worker(
        storage,
        events,
        timestamp,
        service_factory=lambda config: CountingService(config),
    )
    worker._service = CountingService(worker.config)
    worker._stop_requested = True
    worker.state.bot_state = BotRuntimeState.stopped

    outcome = worker._handle_message(build_message())

    assert outcome == MessageOutcome(action="ignored", reason="bot_inactive")
    assert handled_messages == []
    assert events == []
    assert storage.saved_states == []
