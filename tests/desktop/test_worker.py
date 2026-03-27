from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from pathlib import Path

import pytest

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
    def __init__(self, initial_state: DesktopAppState | None = None) -> None:
        self.initial_state = initial_state or DesktopAppState()
        self.saved_states: list[DesktopAppState] = []

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
    ) -> None:
        self.allowed_chat_ids = set(config.whitelisted_chat_ids)
        self.allowed_sender_ids = set(config.allowed_sender_ids)
        self.detection_result = detection_result or RaidDetectionResult(kind="not_a_raid")
        self.handled_messages: list[IncomingMessage] = []

    def handle_message(self, message: IncomingMessage) -> RaidDetectionResult:
        self.handled_messages.append(message)
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


def build_worker(
    storage: FakeStorage,
    events: list[dict],
    now: datetime,
    *,
    config: DesktopAppConfig | None = None,
    service_factory=None,
    pipeline_factory=None,
    listener_factory=None,
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
        now=lambda: now,
    )
    return worker, created_services, created_pipelines, created_listeners


def build_default_worker(
    storage: FakeStorage,
    events: list[dict],
    now: datetime,
    *,
    chrome_environment_factory,
    listener_factory=None,
):
    from raidbot.desktop.worker import DesktopBotWorker

    return DesktopBotWorker(
        config=build_config(),
        storage=storage,
        emit_event=events.append,
        chrome_environment_factory=chrome_environment_factory,
        listener_factory=listener_factory or (lambda **kwargs: FakeListener()),
        now=lambda: now,
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


def test_worker_marks_dedupe_only_after_handed_off_execution() -> None:
    timestamp = datetime(2026, 3, 27, 10, 5, 0)
    job = build_job()
    detection = RaidDetectionResult.job_detected(job)

    first_events: list[dict] = []
    first_storage = FakeStorage()
    first_store = TrackingDedupeStore()
    first_pipeline = FakePipeline(
        build_config(),
        execution_result=RaidExecutionResult(
            kind="browser_startup_failure",
            handed_off=False,
        ),
    )
    first_worker, _services, _pipelines, _listeners = build_worker(
        first_storage,
        first_events,
        timestamp,
        service_factory=lambda config: FakeService(config, detection_result=detection),
        pipeline_factory=lambda config: first_pipeline,
    )
    first_worker._service = FakeService(first_worker.config, detection_result=detection)
    first_worker._pipeline = first_pipeline
    first_worker._dedupe_store = first_store

    first_worker._handle_message(build_message())

    assert first_store.mark_calls == []

    second_events: list[dict] = []
    second_storage = FakeStorage()
    second_store = TrackingDedupeStore()
    second_pipeline = FakePipeline(
        build_config(),
        execution_result=RaidExecutionResult(
            kind="executor_not_configured",
            handed_off=True,
        ),
    )
    second_worker, _services, _pipelines, _listeners = build_worker(
        second_storage,
        second_events,
        timestamp,
        service_factory=lambda config: FakeService(config, detection_result=detection),
        pipeline_factory=lambda config: second_pipeline,
    )
    second_worker._service = FakeService(second_worker.config, detection_result=detection)
    second_worker._pipeline = second_pipeline
    second_worker._dedupe_store = second_store

    second_worker._handle_message(build_message())

    assert second_store.mark_calls == [job.normalized_url]


def test_worker_records_browser_session_failed_result() -> None:
    events: list[dict] = []
    timestamp = datetime(2026, 3, 27, 10, 10, 0)
    storage = FakeStorage()
    job = build_job()
    worker, _services, _pipelines, _listeners = build_worker(
        storage,
        events,
        timestamp,
        service_factory=lambda config: FakeService(
            config,
            detection_result=RaidDetectionResult.job_detected(job),
        ),
        pipeline_factory=lambda config: FakePipeline(
            config,
            execution_result=RaidExecutionResult(
                kind="browser_startup_failure",
                handed_off=False,
            ),
        ),
    )
    worker._service = FakeService(worker.config, detection_result=RaidDetectionResult.job_detected(job))
    worker._pipeline = FakePipeline(
        worker.config,
        execution_result=RaidExecutionResult(
            kind="browser_startup_failure",
            handed_off=False,
        ),
    )

    outcome = worker._handle_message(build_message())

    assert outcome.kind == "browser_startup_failure"
    assert worker.state.raids_opened == 0
    assert worker.state.browser_session_failed == 1
    assert worker.state.open_failures == 1
    assert worker.state.last_error == "browser_startup_failure"
    assert [entry.action for entry in worker.state.activity] == [
        "raid_detected",
        "browser_session_failed",
    ]
    assert [entry.reason for entry in worker.state.activity] == [
        "job_detected",
        "browser_startup_failure",
    ]
    assert events[-1] == {"type": "error", "message": "browser_startup_failure"}


def test_worker_does_not_count_navigation_failure_as_successful_raid() -> None:
    events: list[dict] = []
    timestamp = datetime(2026, 3, 27, 10, 12, 0)
    storage = FakeStorage()
    job = build_job()
    worker, _services, _pipelines, _listeners = build_worker(
        storage,
        events,
        timestamp,
        service_factory=lambda config: FakeService(
            config,
            detection_result=RaidDetectionResult.job_detected(job),
        ),
        pipeline_factory=lambda config: FakePipeline(
            config,
            execution_result=RaidExecutionResult(
                kind="navigation_failure",
                handed_off=False,
            ),
        ),
    )
    worker._service = FakeService(
        worker.config,
        detection_result=RaidDetectionResult.job_detected(job),
    )
    worker._pipeline = FakePipeline(
        worker.config,
        execution_result=RaidExecutionResult(
            kind="navigation_failure",
            handed_off=False,
        ),
    )

    outcome = worker._handle_message(build_message())

    assert outcome.kind == "navigation_failure"
    assert worker.state.raids_opened == 0
    assert worker.state.last_successful_raid_open_at is None
    assert worker.state.browser_session_failed == 1
    assert worker.state.session_closed == 1
    assert [entry.action for entry in worker.state.activity] == [
        "raid_detected",
        "browser_session_failed",
        "session_closed",
    ]


def test_worker_does_not_count_page_ready_timeout_as_successful_raid() -> None:
    events: list[dict] = []
    timestamp = datetime(2026, 3, 27, 10, 13, 0)
    storage = FakeStorage()
    job = build_job()
    worker, _services, _pipelines, _listeners = build_worker(
        storage,
        events,
        timestamp,
        service_factory=lambda config: FakeService(
            config,
            detection_result=RaidDetectionResult.job_detected(job),
        ),
        pipeline_factory=lambda config: FakePipeline(
            config,
            execution_result=RaidExecutionResult(
                kind="page_ready_timeout",
                handed_off=False,
            ),
        ),
    )
    worker._service = FakeService(
        worker.config,
        detection_result=RaidDetectionResult.job_detected(job),
    )
    worker._pipeline = FakePipeline(
        worker.config,
        execution_result=RaidExecutionResult(
            kind="page_ready_timeout",
            handed_off=False,
        ),
    )

    outcome = worker._handle_message(build_message())

    assert outcome.kind == "page_ready_timeout"
    assert worker.state.raids_opened == 0
    assert worker.state.last_successful_raid_open_at is None
    assert worker.state.browser_session_failed == 1
    assert worker.state.session_closed == 1
    assert [entry.action for entry in worker.state.activity] == [
        "raid_detected",
        "browser_session_failed",
        "session_closed",
    ]


def test_worker_records_cancellation_before_executor() -> None:
    events: list[dict] = []
    timestamp = datetime(2026, 3, 27, 10, 15, 0)
    storage = FakeStorage()
    job = build_job()
    created_pipeline: dict[str, FakePipeline] = {}
    worker_ref = {}

    def pipeline_factory(config: DesktopAppConfig) -> FakePipeline:
        def on_execute(job_arg: RaidActionJob, should_continue) -> RaidExecutionResult:
            worker_ref["worker"]._stop_requested = True
            created_pipeline["pipeline"].should_continue_results.append(should_continue())
            return RaidExecutionResult(
                kind="cancelled_before_executor",
                handed_off=False,
            )

        pipeline = FakePipeline(config, on_execute=on_execute)
        created_pipeline["pipeline"] = pipeline
        return pipeline

    worker, _services, _pipelines, _listeners = build_worker(
        storage,
        events,
        timestamp,
        service_factory=lambda config: FakeService(
            config,
            detection_result=RaidDetectionResult.job_detected(job),
        ),
        pipeline_factory=pipeline_factory,
    )
    worker_ref["worker"] = worker
    worker._service = FakeService(worker.config, detection_result=RaidDetectionResult.job_detected(job))
    worker._pipeline = pipeline_factory(worker.config)

    outcome = worker._handle_message(build_message())

    assert outcome.kind == "cancelled_before_executor"
    assert created_pipeline["pipeline"].should_continue_results == [False]
    assert worker.state.raids_opened == 1
    assert worker.state.page_ready == 1
    assert worker.state.session_closed == 1
    assert [entry.action for entry in worker.state.activity] == [
        "raid_detected",
        "browser_session_opened",
        "page_ready",
        "cancelled_before_executor",
        "session_closed",
    ]


def test_worker_records_executor_succeeded_and_session_closed() -> None:
    events: list[dict] = []
    timestamp = datetime(2026, 3, 27, 10, 20, 0)
    storage = FakeStorage()
    job = build_job()
    pipeline = FakePipeline(
        build_config(),
        execution_result=RaidExecutionResult(
            kind="executor_succeeded",
            handed_off=True,
        ),
    )
    worker, _services, _pipelines, _listeners = build_worker(
        storage,
        events,
        timestamp,
        service_factory=lambda config: FakeService(
            config,
            detection_result=RaidDetectionResult.job_detected(job),
        ),
        pipeline_factory=lambda config: pipeline,
    )
    worker._service = FakeService(worker.config, detection_result=RaidDetectionResult.job_detected(job))
    worker._pipeline = pipeline
    worker._dedupe_store = TrackingDedupeStore()

    outcome = worker._handle_message(build_message())

    assert outcome.kind == "executor_succeeded"
    assert pipeline.should_continue_results == [True]
    assert worker.state.raids_opened == 1
    assert worker.state.page_ready == 1
    assert worker.state.executor_succeeded == 1
    assert worker.state.session_closed == 1
    assert worker.state.last_successful_raid_open_at == "2026-03-27T10:20:00"
    assert [entry.action for entry in worker.state.activity] == [
        "raid_detected",
        "browser_session_opened",
        "page_ready",
        "executor_succeeded",
        "session_closed",
    ]


def test_worker_preserves_dedupe_across_service_rebuilds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import raidbot.desktop.worker as worker_module

    opened_urls: list[str] = []
    timestamp = datetime(2026, 3, 27, 10, 25, 0)
    events: list[dict] = []
    storage = FakeStorage()

    class RecordingChromeOpener:
        def __init__(self, *, profile_directory: str, **_kwargs) -> None:
            self.profile_directory = profile_directory

        def open(self, url: str) -> None:
            opened_urls.append(url)

    class FakeChromeEnvironment:
        chrome_path = Path(r"C:\Chrome\chrome.exe")
        user_data_dir = Path(r"C:\Chrome\User Data")

    monkeypatch.setattr(worker_module, "ChromeOpener", RecordingChromeOpener)
    worker = build_default_worker(
        storage,
        events,
        timestamp,
        chrome_environment_factory=lambda: FakeChromeEnvironment(),
    )
    message = build_message()

    worker._service = worker._build_service(worker.config)
    worker._pipeline = worker._build_pipeline(worker.config)
    first_outcome = worker._handle_message(message)
    worker._service = worker._build_service(worker.config)
    worker._pipeline = worker._build_pipeline(worker.config)
    second_outcome = worker._handle_message(message)

    assert first_outcome.kind == "executor_not_configured"
    assert second_outcome.kind == "duplicate"
    assert opened_urls == ["https://x.com/i/status/123"]
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
    )

    await worker.apply_config(new_config)

    assert worker.config == new_config
    assert worker._service.allowed_chat_ids == {-1001, -2002}
    assert worker._service.allowed_sender_ids == {99, 101}
    assert worker._pipeline._backend._launcher.profile_directory == "Profile 9"
    assert worker._listener.stop_calls == 0
    assert created_services == []
    assert created_pipelines == []
    assert created_listeners == []


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
