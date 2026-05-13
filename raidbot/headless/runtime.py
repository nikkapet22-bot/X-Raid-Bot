from __future__ import annotations

import asyncio
import inspect
from queue import Empty, Queue
from threading import Event, Lock, Thread
from typing import Any, Callable

from raidbot.headless.models import HeadlessAuthState, HeadlessRunResult


class HeadlessRuntimeController:
    def __init__(
        self,
        *,
        listener_adapter,
        runner,
        session_manager,
        on_running_changed: Callable[[bool], None] | None = None,
        on_auth_state: Callable[[HeadlessAuthState], None] | None = None,
        on_log: Callable[[str], None] | None = None,
        on_last_detected: Callable[[str], None] | None = None,
        on_result: Callable[[HeadlessRunResult], None] | None = None,
    ) -> None:
        self._listener_adapter = listener_adapter
        self._runner = runner
        self._session_manager = session_manager
        self._on_running_changed = on_running_changed or (lambda _running: None)
        self._on_auth_state = on_auth_state or (lambda _auth: None)
        self._on_log = on_log or (lambda _line: None)
        self._on_last_detected = on_last_detected or (lambda _url: None)
        self._on_result = on_result or (lambda _result: None)
        self._queue: Queue[Any] = Queue()
        self._stop_event = Event()
        self._worker_thread: Thread | None = None
        self._listener_thread: Thread | None = None
        self._listener = None
        self._listener_loop: asyncio.AbstractEventLoop | None = None
        self._running = False
        self._lock = Lock()
        if hasattr(self._listener_adapter, "set_job_consumer"):
            self._listener_adapter.set_job_consumer(self.enqueue_job)
        if hasattr(self._listener_adapter, "set_detection_callback"):
            self._listener_adapter.set_detection_callback(self._handle_detection_result)

    def start(self) -> bool:
        with self._lock:
            if self._running:
                return True
            auth_state = self._session_manager.get_auth_state()
            self._on_auth_state(auth_state)
            if auth_state.status != "authenticated":
                self._on_log(auth_state.detail or auth_state.status)
                return False
            self._stop_event.clear()
            self._listener = self._listener_adapter.build_listener()
            self._worker_thread = Thread(
                target=self._run_worker,
                name="raidbot-headless-worker",
                daemon=True,
            )
            self._listener_thread = Thread(
                target=self._run_listener,
                name="raidbot-headless-listener",
                daemon=True,
            )
            self._running = True
            self._on_running_changed(True)
            self._on_log("Headless runtime started")
            self._worker_thread.start()
            self._listener_thread.start()
            return True

    def stop(self) -> None:
        with self._lock:
            if not self._running:
                return
            self._stop_event.set()
            self._stop_listener()
            self._queue.put(None)
            worker_thread = self._worker_thread
            listener_thread = self._listener_thread
            self._running = False
        if worker_thread is not None:
            worker_thread.join(timeout=5)
        if listener_thread is not None:
            listener_thread.join(timeout=5)
        self._on_running_changed(False)
        self._on_log("Headless runtime stopped")

    def enqueue_job(self, job: Any) -> None:
        if self._stop_event.is_set():
            return
        normalized_url = getattr(job, "normalized_url", None)
        if normalized_url:
            self._on_last_detected(normalized_url)
            self._on_log(f"Detected raid: {normalized_url}")
        self._queue.put(job)

    def set_enabled_actions(self, enabled_actions) -> None:
        if hasattr(self._runner, "set_enabled_actions"):
            self._runner.set_enabled_actions(enabled_actions)

    def _run_worker(self) -> None:
        while not self._stop_event.is_set():
            try:
                job = self._queue.get(timeout=0.1)
            except Empty:
                continue
            if job is None:
                break
            result = self._runner.run(job)
            self._on_result(result)
            normalized_url = getattr(job, "normalized_url", None)
            self._on_log(
                f"{normalized_url}: {result.reason}" if normalized_url else result.reason
            )

    def _run_listener(self) -> None:
        listener = self._listener
        if listener is None:
            return
        run_forever = getattr(listener, "run_forever", None)
        if run_forever is None:
            self._on_log("listener_missing_run_forever")
            return
        if inspect.iscoroutinefunction(run_forever):
            loop = asyncio.new_event_loop()
            self._listener_loop = loop
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(run_forever())
            except Exception as exc:
                self._on_log(str(exc).strip() or "headless_listener_failed")
            finally:
                self._listener_loop = None
                loop.close()
            return
        try:
            run_forever()
        except Exception as exc:
            self._on_log(str(exc).strip() or "headless_listener_failed")

    def _stop_listener(self) -> None:
        listener = self._listener
        if listener is None:
            return
        stop = getattr(listener, "stop", None)
        if stop is None:
            return
        try:
            if inspect.iscoroutinefunction(stop):
                if self._listener_loop is not None:
                    future = asyncio.run_coroutine_threadsafe(stop(), self._listener_loop)
                    future.result(timeout=5)
                else:
                    asyncio.run(stop())
            else:
                stop()
        except Exception as exc:
            self._on_log(str(exc).strip() or "headless_listener_stop_failed")

    def _handle_detection_result(self, result: Any) -> None:
        if getattr(result, "kind", None) == "job_detected":
            return
        reason = getattr(result, "reason", None) or getattr(result, "kind", None)
        if reason:
            self._on_log(f"Skipped raid: {reason}")
