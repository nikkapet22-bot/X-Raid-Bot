from __future__ import annotations

import threading
import time

from raidbot.headless.models import HeadlessAuthState, HeadlessRunResult


class _FakeListener:
    def __init__(self) -> None:
        self.run_called = threading.Event()
        self.stop_called = threading.Event()
        self._stop = threading.Event()

    def run_forever(self) -> None:
        self.run_called.set()
        self._stop.wait(1.0)

    def stop(self) -> None:
        self.stop_called.set()
        self._stop.set()


class _FakeListenerAdapter:
    def __init__(self) -> None:
        self.listener = _FakeListener()
        self.job_consumer = None

    def set_job_consumer(self, consumer) -> None:
        self.job_consumer = consumer

    def set_detection_callback(self, callback) -> None:
        self.detection_callback = callback

    def build_listener(self):
        return self.listener


class _FakeRunner:
    def __init__(self) -> None:
        self.runs = []

    def run(self, job):
        self.runs.append(job.normalized_url)
        return HeadlessRunResult(
            url=job.normalized_url,
            success=True,
            reason="completed",
            completed_actions=("like",),
        )


class _FakeSessionManager:
    def __init__(self, state: HeadlessAuthState | None = None) -> None:
        self.state = state or HeadlessAuthState(status="authenticated")

    def get_auth_state(self) -> HeadlessAuthState:
        return self.state


class _FakeJob:
    def __init__(self, url: str) -> None:
        self.normalized_url = url


def test_headless_runtime_starts_and_stops_with_state_callbacks() -> None:
    from raidbot.headless.runtime import HeadlessRuntimeController

    adapter = _FakeListenerAdapter()
    runner = _FakeRunner()
    session_manager = _FakeSessionManager()
    running_states: list[bool] = []
    logs: list[str] = []

    runtime = HeadlessRuntimeController(
        listener_adapter=adapter,
        runner=runner,
        session_manager=session_manager,
        on_running_changed=running_states.append,
        on_log=logs.append,
    )

    assert runtime.start() is True
    assert adapter.listener.run_called.wait(1.0)

    runtime.stop()

    assert running_states == [True, False]
    assert adapter.listener.stop_called.is_set()
    assert any("started" in line for line in logs)
    assert any("stopped" in line for line in logs)


def test_headless_runtime_processes_detected_jobs_and_emits_result() -> None:
    from raidbot.headless.runtime import HeadlessRuntimeController

    adapter = _FakeListenerAdapter()
    runner = _FakeRunner()
    session_manager = _FakeSessionManager()
    detected_urls: list[str] = []
    results: list[HeadlessRunResult] = []

    runtime = HeadlessRuntimeController(
        listener_adapter=adapter,
        runner=runner,
        session_manager=session_manager,
        on_last_detected=detected_urls.append,
        on_result=results.append,
    )

    assert runtime.start() is True
    adapter.job_consumer(_FakeJob("https://x.com/i/status/123"))
    deadline = time.time() + 1.0
    while not results and time.time() < deadline:
        time.sleep(0.01)
    runtime.stop()

    assert detected_urls == ["https://x.com/i/status/123"]
    assert [result.reason for result in results] == ["completed"]
    assert runner.runs == ["https://x.com/i/status/123"]


def test_headless_runtime_refuses_start_when_x_auth_missing() -> None:
    from raidbot.headless.runtime import HeadlessRuntimeController

    adapter = _FakeListenerAdapter()
    runner = _FakeRunner()
    session_manager = _FakeSessionManager(
        HeadlessAuthState(status="needs_login", detail="x_auth_required")
    )
    running_states: list[bool] = []
    logs: list[str] = []

    runtime = HeadlessRuntimeController(
        listener_adapter=adapter,
        runner=runner,
        session_manager=session_manager,
        on_running_changed=running_states.append,
        on_log=logs.append,
    )

    assert runtime.start() is False
    assert running_states == []
    assert any("x_auth_required" in line for line in logs)
