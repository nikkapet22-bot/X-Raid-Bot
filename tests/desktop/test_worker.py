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
    BotRuntimeState,
    DesktopAppConfig,
    DesktopAppState,
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
        on_run_sequence=None,
    ) -> None:
        self.window_manager = FakeWindowManager(windows or [])
        self.run_sequence_results = list(run_sequence_results or [])
        self.on_run_sequence = on_run_sequence
        self.run_calls: list[tuple[str, int | None]] = []
        self.request_stop_calls = 0
        self.input_driver = type(
            "FakeInputDriver",
            (),
            {
                "__init__": lambda self: setattr(self, "close_active_tab_calls", 0),
                "close_active_tab": lambda self: setattr(
                    self,
                    "close_active_tab_calls",
                    self.close_active_tab_calls + 1,
                ),
            },
        )()
        self._active_runner = SimpleNamespace(input_driver=self.input_driver)

    def list_target_windows(self) -> list[object]:
        return self.window_manager.list_chrome_windows()

    def run_sequence(self, sequence: AutomationSequence, selected_window_handle: int | None):
        self.run_calls.append((sequence.id, selected_window_handle))
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


class FakeChromeOpener:
    def __init__(self, *_, **kwargs) -> None:
        self.profile_directory = kwargs.get("profile_directory")
        self.open_calls: list[tuple[str, int | None]] = []

    def open(self, url: str, *, window_handle: int | None = None) -> OpenedRaidContext:
        self.open_calls.append((url, window_handle))
        return OpenedRaidContext(
            normalized_url=url,
            opened_at=1.0,
            window_handle=window_handle,
            profile_directory=self.profile_directory or "",
        )


class FailingChromeOpener:
    def __init__(self, *_, **kwargs) -> None:
        self.profile_directory = kwargs.get("profile_directory")
        self.open_calls: list[tuple[str, int | None]] = []

    def open(self, url: str, *, window_handle: int | None = None):
        self.open_calls.append((url, window_handle))
        raise RuntimeError("browser_startup_failure")


class FlakyChromeOpener:
    def __init__(self, *_, **kwargs) -> None:
        self.profile_directory = kwargs.get("profile_directory")
        self.open_calls: list[tuple[str, int | None]] = []
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
    AutomationStorage(tmp_path).save_sequences([build_sequence()])
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
            default_auto_sequence_id="seq-1",
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
    assert opener.open_calls == [
        (first_url, 7),
        (second_url, 7),
    ]
    assert runtime is not None
    assert runtime.run_calls == [
        ("seq-1", 7),
        ("seq-1", 7),
    ]
    assert runtime.input_driver.close_active_tab_calls == 2
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

    assert queue_states == ["queued", "running", "queued", "running", "idle"]
    assert queue_lengths == [1, 0, 1, 0]
    assert current_urls == [first_url, None, second_url, None]
    assert [event["sequence_id"] for event in started] == ["seq-1", "seq-1"]
    assert [event["sequence_id"] for event in succeeded] == ["seq-1", "seq-1"]


def test_worker_leaves_auto_run_queued_while_manual_automation_is_active_and_resumes_after_release(
    tmp_path,
) -> None:
    events: list[dict] = []
    timestamp = datetime(2026, 3, 27, 10, 3, 0)
    storage = FakeStorage(base_dir=tmp_path)
    AutomationStorage(tmp_path).save_sequences([build_sequence()])
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
            default_auto_sequence_id="seq-1",
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

    assert opener.open_calls == [("https://x.com/i/status/123", 9)]
    assert runtime.run_calls == [("seq-1", 9)]
    assert worker.state.automation_queue_state == "idle"
    assert worker.state.automation_queue_length == 0


def test_worker_applies_auto_run_settle_delay_before_running_sequence(tmp_path) -> None:
    events: list[dict] = []
    timestamp = datetime(2026, 3, 27, 10, 4, 0)
    storage = FakeStorage(base_dir=tmp_path)
    AutomationStorage(tmp_path).save_sequences([build_sequence()])
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
            default_auto_sequence_id="seq-1",
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
    assert opener.open_calls == [("https://x.com/i/status/123", 17)]
    assert runtime is not None
    assert runtime.run_calls == [("seq-1", 17)]
    assert calls == [("wait", 2.2), ("run", 17)]


def test_worker_fails_safe_when_owned_chrome_window_cannot_be_proven(tmp_path) -> None:
    events: list[dict] = []
    timestamp = datetime(2026, 3, 27, 10, 5, 0)
    storage = FakeStorage(base_dir=tmp_path)
    AutomationStorage(tmp_path).save_sequences([build_sequence()])
    opener = FakeChromeOpener(profile_directory="Profile 3")
    runtime: FakeAutomationRuntime | None = None

    class UnownedChromeWindowManager:
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
        runtime.window_manager = UnownedChromeWindowManager()
        return runtime

    worker, _created_services, _pipelines, _listeners = build_worker(
        storage,
        events,
        timestamp,
        config=build_config(
            auto_run_enabled=True,
            default_auto_sequence_id="seq-1",
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
    assert runtime is not None
    assert runtime.run_calls == []
    assert worker.state.automation_queue_state == "paused"
    assert worker.state.automation_queue_length == 0
    assert worker.state.automation_last_error == "target_window_not_found"


def test_worker_leaves_pending_queue_unopened_when_auto_run_is_disabled_mid_run(tmp_path) -> None:
    events: list[dict] = []
    timestamp = datetime(2026, 3, 27, 10, 4, 0)
    storage = FakeStorage(base_dir=tmp_path)
    AutomationStorage(tmp_path).save_sequences([build_sequence()])
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
            default_auto_sequence_id="seq-1",
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
    assert opener.open_calls == [(first_url, 11)]
    assert runtime is not None
    assert runtime.run_calls == [("seq-1", 11)]
    assert runtime.input_driver.close_active_tab_calls == 1
    assert worker.state.automation_queue_state == "queued"
    assert worker.state.automation_queue_length == 1
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
    ]


def test_worker_clear_automation_queue_preserves_running_state(tmp_path) -> None:
    events: list[dict] = []
    timestamp = datetime(2026, 3, 27, 10, 5, 0)
    storage = FakeStorage(base_dir=tmp_path)
    AutomationStorage(tmp_path).save_sequences([build_sequence()])
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
                assert runtime.run_calls == [("seq-1", 7)]
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
            default_auto_sequence_id="seq-1",
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
    assert opener.open_calls == [
        ("https://x.com/i/status/444", 7),
        ("https://x.com/i/status/555", 7),
    ]
    assert runtime is not None
    assert runtime.run_calls == [("seq-1", 7), ("seq-1", 7)]
    assert runtime.input_driver.close_active_tab_calls == 2
    assert worker.state.automation_queue_state == "idle"
    assert worker.state.automation_queue_length == 0
    assert worker.state.automation_current_url is None
    assert worker.state.automation_last_error is None


def test_worker_does_not_open_chrome_when_auto_run_is_disabled_and_does_not_mark_dedupe(
    tmp_path,
) -> None:
    events: list[dict] = []
    timestamp = datetime(2026, 3, 27, 10, 5, 0)
    storage = FakeStorage(base_dir=tmp_path)
    AutomationStorage(tmp_path).save_sequences([build_sequence()])
    opener = FakeChromeOpener(profile_directory="Profile 3")
    runtime: FakeAutomationRuntime | None = None

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
        )
        return runtime

    worker, _services, _pipelines, _listeners = build_worker(
        storage,
        events,
        timestamp,
        config=build_config(
            auto_run_enabled=False,
            default_auto_sequence_id="seq-1",
        ),
        service_factory=lambda config: FakeService(
            config,
            detection_result_factory=detect_job_from_message,
        ),
        automation_runtime_factory=runtime_factory,
        chrome_opener_factory=lambda **kwargs: opener,
    )
    worker._service = worker._build_service(worker.config)
    dedupe_store = TrackingDedupeStore()
    worker._dedupe_store = dedupe_store

    outcome = worker._handle_message(build_message("Likes 10 | 8 [%]\n\nhttps://x.com/i/status/555"))

    assert outcome.kind == "job_detected"
    assert opener.open_calls == []
    assert runtime is not None
    assert runtime.run_calls == []
    assert dedupe_store.mark_calls == []
    assert worker.state.automation_queue_state == "idle"
    assert worker.state.automation_queue_length == 0
    assert worker.state.automation_last_error == "auto_run_disabled"
    assert [entry.action for entry in worker.state.activity] == [
        "raid_detected",
        "automation_failed",
    ]


def test_worker_records_browser_session_failed_result(tmp_path) -> None:
    events: list[dict] = []
    timestamp = datetime(2026, 3, 27, 10, 10, 0)
    storage = FakeStorage(base_dir=tmp_path)
    AutomationStorage(tmp_path).save_sequences([build_sequence()])
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
            default_auto_sequence_id="seq-1",
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
    assert opener.open_calls == [("https://x.com/i/status/123", 9)]
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
    assert [entry.action for entry in worker.state.activity] == [
        "raid_detected",
        "auto_queued",
        "automation_failed",
    ]
    assert any(
        event == {"type": "error", "message": "browser_startup_failure"}
        for event in events
    )


@pytest.mark.parametrize("failure_reason", ["navigation_failure", "page_ready_timeout"])
def test_worker_leaves_failed_tab_open_and_pauses_queue(
    tmp_path,
    failure_reason: str,
) -> None:
    events: list[dict] = []
    timestamp = datetime(2026, 3, 27, 10, 12, 0)
    storage = FakeStorage(base_dir=tmp_path)
    AutomationStorage(tmp_path).save_sequences([build_sequence()])
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
            default_auto_sequence_id="seq-1",
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
    assert opener.open_calls == [("https://x.com/i/status/123", 13)]
    assert runtime is not None
    assert runtime.run_calls == [("seq-1", 13)]
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
    assert [entry.action for entry in worker.state.activity] == [
        "raid_detected",
        "auto_queued",
        "automation_started",
        "automation_failed",
    ]
    assert any(event == {"type": "error", "message": failure_reason} for event in events)


def test_worker_retries_same_url_after_empty_paused_queue_resume(tmp_path) -> None:
    events: list[dict] = []
    timestamp = datetime(2026, 3, 27, 10, 11, 0)
    storage = FakeStorage(base_dir=tmp_path)
    AutomationStorage(tmp_path).save_sequences([build_sequence()])
    opener = FlakyChromeOpener(profile_directory="Profile 3")
    runtime: FakeAutomationRuntime | None = None
    dedupe_store = TrackingDedupeStore()

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
            default_auto_sequence_id="seq-1",
        ),
        service_factory=lambda config: FakeService(
            config,
            detection_result_factory=detect_job_from_message,
        ),
        automation_runtime_factory=runtime_factory,
        chrome_opener_factory=lambda **kwargs: opener,
    )
    worker._service = worker._build_service(worker.config)
    worker._dedupe_store = dedupe_store

    first_outcome = worker._handle_message(build_message("Likes 10 | 8 [%]\n\nhttps://x.com/i/status/123"))
    assert first_outcome.kind == "job_detected"
    assert opener.open_calls == [("https://x.com/i/status/123", 10)]
    assert runtime is not None
    assert runtime.run_calls == []
    assert dedupe_store.mark_calls == []
    assert worker.state.automation_queue_state == "paused"
    assert worker.state.automation_queue_length == 0

    worker.resume_automation_queue()
    second_outcome = worker._handle_message(build_message("Likes 10 | 8 [%]\n\nhttps://x.com/i/status/123"))

    assert second_outcome.kind == "job_detected"
    assert opener.open_calls == [
        ("https://x.com/i/status/123", 10),
        ("https://x.com/i/status/123", 10),
    ]
    assert runtime is not None
    assert runtime.run_calls == [("seq-1", 10)]
    assert runtime.input_driver.close_active_tab_calls == 1
    assert dedupe_store.mark_calls == ["https://x.com/i/status/123"]
    assert worker.state.browser_session_failed == 1
    assert worker.state.automation_queue_state == "idle"
    assert worker.state.automation_queue_length == 0
    assert worker.state.automation_current_url is None
    assert worker.state.automation_last_error is None


def test_worker_resumes_queue_after_failure_and_continues_next_item(tmp_path) -> None:
    events: list[dict] = []
    timestamp = datetime(2026, 3, 27, 10, 15, 0)
    storage = FakeStorage(base_dir=tmp_path)
    AutomationStorage(tmp_path).save_sequences([build_sequence()])
    opener = FakeChromeOpener(profile_directory="Profile 3")
    runtime: FakeAutomationRuntime | None = None
    worker_ref: dict[str, object] = {}
    second_message = build_message("Likes 10 | 8 [%]\n\nhttps://x.com/i/status/444")

    def fail_first_run(sequence: AutomationSequence, _handle: int | None):
        if sequence.id == "seq-1" and len(opener.open_calls) == 1:
            worker_ref["worker"]._handle_message(second_message)
            return RunResult(status="failed", failure_reason="executor_failed")
        return RunResult(status="completed", window_handle=0)

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
            on_run_sequence=fail_first_run,
        )
        return runtime

    worker, _services, _pipelines, _listeners = build_worker(
        storage,
        events,
        timestamp,
        config=build_config(
            auto_run_enabled=True,
            default_auto_sequence_id="seq-1",
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

    outcome = worker._handle_message(build_message("Likes 10 | 8 [%]\n\nhttps://x.com/i/status/333"))
    worker.resume_automation_queue()

    assert outcome.kind == "job_detected"
    assert opener.open_calls == [
        ("https://x.com/i/status/333", 17),
        ("https://x.com/i/status/444", 17),
    ]
    assert runtime is not None
    assert runtime.run_calls == [("seq-1", 17), ("seq-1", 17)]
    assert runtime.input_driver.close_active_tab_calls == 1
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
        "automation_failed",
        "automation_started",
        "automation_succeeded",
        "session_closed",
    ]


def test_worker_clear_automation_queue_preserves_failed_tab(tmp_path) -> None:
    events: list[dict] = []
    timestamp = datetime(2026, 3, 27, 10, 20, 0)
    storage = FakeStorage(base_dir=tmp_path)
    AutomationStorage(tmp_path).save_sequences([build_sequence()])
    opener = FakeChromeOpener(profile_directory="Profile 3")
    runtime: FakeAutomationRuntime | None = None
    worker_ref: dict[str, object] = {}
    second_message = build_message("Likes 10 | 8 [%]\n\nhttps://x.com/i/status/666")
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
            default_auto_sequence_id="seq-1",
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

    def fail_first_run(sequence: AutomationSequence, _handle: int | None):
        if len(opener.open_calls) == 1:
            worker_ref["worker"]._handle_message(second_message)
            return RunResult(status="failed", failure_reason="executor_failed")
        return RunResult(status="completed", window_handle=0)

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
            on_run_sequence=fail_first_run,
        )
        return runtime

    worker.automation_runtime_factory = runtime_factory_with_failure
    outcome = worker._handle_message(build_message("Likes 10 | 8 [%]\n\nhttps://x.com/i/status/555"))
    assert outcome.kind == "job_detected"

    worker.clear_automation_queue()
    recovery_outcome = worker._handle_message(third_message)

    assert runtime_factory_called["value"] is True
    assert recovery_outcome.kind == "job_detected"
    assert opener.open_calls == [
        ("https://x.com/i/status/555", 23),
        ("https://x.com/i/status/777", 23),
    ]
    assert runtime is not None
    assert runtime.run_calls == [("seq-1", 23), ("seq-1", 23)]
    assert runtime.input_driver.close_active_tab_calls == 1
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
        "automation_failed",
        "raid_detected",
        "auto_queued",
        "automation_started",
        "automation_succeeded",
        "session_closed",
    ]


def test_worker_resume_automation_queue_recovers_after_missing_default_sequence(
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
            default_auto_sequence_id="seq-1",
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
    AutomationStorage(tmp_path).save_sequences([build_sequence()])
    worker.resume_automation_queue()
    second_outcome = worker._handle_message(second_message)

    assert first_outcome.kind == "job_detected"
    assert second_outcome.kind == "job_detected"
    assert opener.open_calls == [("https://x.com/i/status/999", 29)]
    assert runtime is not None
    assert runtime.run_calls == [("seq-1", 29)]
    assert runtime.input_driver.close_active_tab_calls == 1
    assert worker.state.automation_queue_state == "idle"
    assert worker.state.automation_queue_length == 0
    assert worker.state.automation_current_url is None
    assert worker.state.automation_last_error is None
    assert [entry.action for entry in worker.state.activity] == [
        "raid_detected",
        "automation_failed",
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
    AutomationStorage(tmp_path).save_sequences([build_sequence()])
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
            default_auto_sequence_id="seq-1",
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
    assert opener.open_calls == [("https://x.com/i/status/123", 31)]
    assert runtime is not None
    assert runtime.run_calls == [("seq-1", 31)]
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
    AutomationStorage(tmp_path).save_sequences([build_sequence()])
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
            default_auto_sequence_id="seq-1",
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
            default_auto_sequence_id="seq-1",
        )
    )
    second_outcome = worker._handle_message(build_message("Likes 10 | 8 [%]\n\nhttps://x.com/i/status/456"))

    assert first_outcome.kind == "job_detected"
    assert second_outcome.kind == "job_detected"
    assert [opener.profile_directory for opener in created_openers] == [
        "Profile 3",
        "Profile 9",
    ]
    assert [opener.open_calls for opener in created_openers] == [
        [("https://x.com/i/status/123", 41)],
        [("https://x.com/i/status/456", 41)],
    ]
    assert runtime is not None
    assert runtime.run_calls == [("seq-1", 41), ("seq-1", 41)]


@pytest.mark.asyncio
async def test_worker_apply_config_refreshes_auto_run_chrome_opener_on_telegram_restart(
    tmp_path,
) -> None:
    events: list[dict] = []
    timestamp = datetime(2026, 3, 27, 10, 46, 30)
    storage = FakeStorage(base_dir=tmp_path)
    AutomationStorage(tmp_path).save_sequences([build_sequence()])
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
            default_auto_sequence_id="seq-1",
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
            default_auto_sequence_id="seq-1",
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
    assert [opener.open_calls for opener in created_openers] == [
        [("https://x.com/i/status/321", 43)],
        [("https://x.com/i/status/654", 43)],
    ]
    assert runtime is not None
    assert runtime.run_calls == [("seq-1", 43), ("seq-1", 43)]


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
