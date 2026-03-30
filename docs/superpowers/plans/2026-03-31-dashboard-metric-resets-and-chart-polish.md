# Dashboard Metric Resets, Local-Time Migration, And Cumulative Chart Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-card metric reset buttons, migrate legacy dashboard timestamps to local time once, and replace the current cumulative raid chart renderer with a smooth artifact-free implementation.

**Architecture:** Keep reset behavior stable by persisting per-metric baselines in desktop state instead of deleting shared counters or activity. Keep the time correction in storage so legacy rows are fixed once on load, and keep the chart semantics cumulative while replacing only the painter path logic that currently produces rendering artifacts.

**Tech Stack:** Python, PySide6, pytest

---

## File Map

- `raidbot/desktop/models.py`
  - add the persisted dashboard reset state dataclass and attach it to `DesktopAppState`.
- `raidbot/desktop/storage.py`
  - save/load the new reset state and run the one-time legacy UTC-to-local migration for stored dashboard timestamps.
- `raidbot/desktop/controller.py`
  - expose a dashboard metric reset action that works both when the worker is idle and when it is live.
- `raidbot/desktop/worker.py`
  - apply and persist per-metric reset baselines against the live state while the bot is running.
- `raidbot/desktop/main_window.py`
  - render `R` buttons on each metric card, trigger controller resets, apply reset baselines in displayed metrics, and replace the chart painter with a safer smooth cumulative renderer.
- `tests/desktop/test_storage.py`
  - verify reset-state persistence and one-time local-time migration.
- `tests/desktop/test_controller.py`
  - verify reset actions route through the worker when running and persist directly when idle.
- `tests/desktop/test_worker.py`
  - verify each metric reset mutates only its own live state baseline.
- `tests/desktop/test_main_window.py`
  - verify metric cards expose reset buttons, reset only themselves, and chart/data formatting stay correct after the renderer and baseline changes.

### Task 1: Add Persisted Dashboard Reset State And One-Time Local-Time Migration

**Files:**
- Modify: `raidbot/desktop/models.py`
- Modify: `raidbot/desktop/storage.py`
- Test: `tests/desktop/test_storage.py`

- [ ] **Step 1: Write the failing storage tests for reset-state round trip and legacy timestamp migration**

Add focused tests such as:

```python
def test_storage_round_trips_dashboard_metric_reset_state(tmp_path):
    storage = DesktopStorage(tmp_path)
    state = DesktopAppState(
        dashboard_metric_resets=DashboardMetricResetState(
            avg_completion_reset_at=datetime(2026, 3, 31, 23, 15, 0),
            avg_raids_per_hour_reset_at=datetime(2026, 3, 31, 23, 20, 0),
            raids_completed_offset=14,
            raids_failed_offset=2,
            success_rate_completed_offset=14,
            success_rate_failed_offset=2,
            uptime_reset_at=datetime(2026, 3, 31, 23, 25, 0),
            legacy_local_time_migrated=True,
        )
    )
    storage.save_state(state)
    assert storage.load_state().dashboard_metric_resets == state.dashboard_metric_resets


def test_storage_migrates_legacy_dashboard_timestamps_to_local_time_once(tmp_path, monkeypatch):
    storage = DesktopStorage(tmp_path)
    raw = {
        "bot_state": "stopped",
        "connection_state": "disconnected",
        "last_successful_raid_open_at": "2026-03-31T20:00:00",
        "activity": [
            {
                "timestamp": "2026-03-31T20:05:00",
                "action": "automation_succeeded",
                "url": "https://x.com/i/status/1",
                "reason": "automation_succeeded",
                "profile_directory": "Default",
            }
        ],
    }
    storage.state_path.write_text(json.dumps(raw), encoding="utf-8")
    state = storage.load_state()
    assert state.dashboard_metric_resets.legacy_local_time_migrated is True
    assert state.activity[0].timestamp.hour == 23
    assert state.last_successful_raid_open_at == "2026-03-31T23:00:00"
```

Use the current local-offset assumption from the desktop environment tests instead of inventing a new timezone source inside the test.

- [ ] **Step 2: Run the targeted storage tests to verify they fail**

Run:

```bash
python -m pytest -q tests\desktop\test_storage.py -k "dashboard_metric_reset_state or migrates_legacy_dashboard_timestamps_to_local_time_once"
```

Expected: FAIL because `DesktopAppState` does not yet persist reset baselines or migration markers.

- [ ] **Step 3: Add the reset-state model and storage migration**

In `raidbot/desktop/models.py`, add:

```python
@dataclass
class DashboardMetricResetState:
    avg_completion_reset_at: datetime | None = None
    avg_raids_per_hour_reset_at: datetime | None = None
    raids_completed_offset: int = 0
    raids_failed_offset: int = 0
    success_rate_completed_offset: int = 0
    success_rate_failed_offset: int = 0
    uptime_reset_at: datetime | None = None
    legacy_local_time_migrated: bool = False
```

Then attach it to `DesktopAppState` with:

```python
dashboard_metric_resets: DashboardMetricResetState = field(
    default_factory=DashboardMetricResetState
)
```

In `raidbot/desktop/storage.py`:

- serialize and deserialize the new dataclass in `_state_to_data` and `_state_from_data`
- add a one-time `_migrate_legacy_dashboard_timestamps_to_local_time(state)` helper
- run that migration from `_normalize_loaded_state`
- convert both:
  - each `ActivityEntry.timestamp`
  - `last_successful_raid_open_at`
- guard the migration with `legacy_local_time_migrated`

Use a deterministic local conversion path such as:

```python
legacy_utc = timestamp.replace(tzinfo=timezone.utc)
local_value = legacy_utc.astimezone().replace(tzinfo=None)
```

Do not touch new activity write paths in this task.

- [ ] **Step 4: Run the targeted storage tests to verify they pass**

Run:

```bash
python -m pytest -q tests\desktop\test_storage.py -k "dashboard_metric_reset_state or migrates_legacy_dashboard_timestamps_to_local_time_once"
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/desktop/models.py raidbot/desktop/storage.py tests/desktop/test_storage.py
git commit -m "feat: persist dashboard metric reset state"
```

### Task 2: Add Controller And Worker Support For Per-Metric Resets

**Files:**
- Modify: `raidbot/desktop/controller.py`
- Modify: `raidbot/desktop/worker.py`
- Test: `tests/desktop/test_controller.py`
- Test: `tests/desktop/test_worker.py`

- [ ] **Step 1: Write the failing controller and worker reset tests**

Add controller tests like:

```python
def test_controller_resets_dashboard_metric_through_worker_when_running(qtbot):
    storage = FakeStorage()
    created = {}

    def worker_factory(**kwargs):
        worker = FakeWorker(**kwargs)
        created["worker"] = worker
        return worker

    runner = SubmitExecutingRunner()
    controller = DesktopController(
        storage=storage,
        config=build_config(),
        worker_factory=worker_factory,
        runner_factory=lambda: runner,
    )
    controller.start_bot()
    controller.reset_dashboard_metric("raids_completed")
    assert created["worker"].reset_dashboard_metric_calls == ["raids_completed"]


def test_controller_resets_dashboard_metric_directly_when_idle(qtbot):
    storage = FakeStorageWithState(
        DesktopAppState(raids_completed=17)
    )
    controller = DesktopController(storage=storage, config=build_config())
    stats_payloads = []
    controller.statsChanged.connect(stats_payloads.append)
    controller.reset_dashboard_metric("raids_completed")
    assert storage.saved_states[-1].dashboard_metric_resets.raids_completed_offset == 17
    assert stats_payloads[-1].dashboard_metric_resets.raids_completed_offset == 17
```

Add worker tests like:

```python
def test_worker_reset_dashboard_metric_raids_completed_uses_current_counter():
    worker = build_worker(initial_state=DesktopAppState(raids_completed=31))
    worker.reset_dashboard_metric("raids_completed")
    assert worker.state.dashboard_metric_resets.raids_completed_offset == 31


def test_worker_reset_dashboard_metric_uptime_uses_current_clock():
    now = datetime(2026, 3, 31, 23, 50, 0)
    worker = build_worker(now=lambda: now)
    worker.reset_dashboard_metric("uptime")
    assert worker.state.dashboard_metric_resets.uptime_reset_at == now
```

Also cover `avg_raid_completion_time`, `avg_raids_per_hour`, and `success_rate`.

- [ ] **Step 2: Run the targeted controller/worker tests to verify they fail**

Run:

```bash
python -m pytest -q tests\desktop\test_controller.py -k dashboard_metric tests\desktop\test_worker.py -k reset_dashboard_metric
```

Expected: FAIL because no reset API exists yet.

- [ ] **Step 3: Implement the shared reset semantics**

In `raidbot/desktop/worker.py`, add:

```python
def reset_dashboard_metric(self, metric_key: str) -> None:
    resets = self.state.dashboard_metric_resets
    now = self.now()
    if metric_key == "avg_raid_completion_time":
        resets.avg_completion_reset_at = now
    elif metric_key == "avg_raids_per_hour":
        resets.avg_raids_per_hour_reset_at = now
    elif metric_key == "raids_completed":
        resets.raids_completed_offset = self.state.raids_completed
    elif metric_key == "raids_failed":
        resets.raids_failed_offset = self.state.raids_failed
    elif metric_key == "success_rate":
        resets.success_rate_completed_offset = self.state.raids_completed
        resets.success_rate_failed_offset = self.state.raids_failed
    elif metric_key == "uptime":
        resets.uptime_reset_at = now
    else:
        raise ValueError(f"Unknown dashboard metric: {metric_key}")
    self._persist_state_snapshot()
```

In `raidbot/desktop/controller.py`, add:

```python
def reset_dashboard_metric(self, metric_key: str) -> None:
    if self._worker is not None and self._runner is not None and self._runner.is_running():
        self._submit_to_runner(lambda: self._worker.reset_dashboard_metric(metric_key))
        return
    state = self.storage.load_state()
    updated_state = _apply_dashboard_metric_reset(state, metric_key, datetime.now())
    self.storage.save_state(updated_state)
    self.statsChanged.emit(updated_state)
```

To avoid duplication, factor the actual mutation into one small helper that both the controller and the worker use.

- [ ] **Step 4: Run the targeted controller/worker tests to verify they pass**

Run:

```bash
python -m pytest -q tests\desktop\test_controller.py -k dashboard_metric tests\desktop\test_worker.py -k reset_dashboard_metric
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/desktop/controller.py raidbot/desktop/worker.py tests/desktop/test_controller.py tests/desktop/test_worker.py
git commit -m "feat: add per-metric dashboard resets"
```

### Task 3: Add `R` Buttons To Metric Cards And Apply Reset Baselines In Dashboard Metrics

**Files:**
- Modify: `raidbot/desktop/main_window.py`
- Test: `tests/desktop/test_main_window.py`

- [ ] **Step 1: Write the failing main-window tests for reset buttons and isolated resets**

Add UI tests like:

```python
def test_main_window_metric_cards_expose_reset_buttons(qtbot):
    window = build_window(FakeController(), FakeStorage())
    qtbot.addWidget(window)
    reset_buttons = window.findChildren(QPushButton, "metricResetButton")
    assert len(reset_buttons) == 6


def test_main_window_metric_reset_button_resets_only_its_own_metric(qtbot):
    controller = FakeController()
    window = build_window(controller, FakeStorage())
    qtbot.addWidget(window)
    completed_button = window.metric_reset_buttons["raids_completed"]
    qtbot.mouseClick(completed_button, Qt.MouseButton.LeftButton)
    assert controller.dashboard_metric_reset_requests == ["raids_completed"]
```

Add display tests that inject `DesktopAppState` plus reset baselines and confirm:

- completed/failed subtract only their own offsets
- success rate uses delta completed/delta failed
- uptime uses `uptime_reset_at`
- avg cards use only successful runs after their reset timestamps

- [ ] **Step 2: Run the targeted main-window tests to verify they fail**

Run:

```bash
python -m pytest -q tests\desktop\test_main_window.py -k "metric_cards_expose_reset_buttons or metric_reset_button_resets_only_its_own_metric or dashboard_metrics_respect_reset_baselines"
```

Expected: FAIL because the cards do not yet render `R` buttons or apply reset baselines.

- [ ] **Step 3: Implement metric-card reset UI and baseline-aware calculations**

In `raidbot/desktop/main_window.py`:

- change `_build_metric_card` to accept `metric_key`
- add a small top-right reset button:

```python
reset_button = QPushButton("R")
reset_button.setObjectName("metricResetButton")
reset_button.clicked.connect(lambda: self.controller.reset_dashboard_metric(metric_key))
```

- keep a lookup:

```python
self.metric_reset_buttons[metric_key] = reset_button
```

- add a small helper:

```python
def _dashboard_resets(self):
    return self._latest_state.dashboard_metric_resets
```

- apply offsets in `_refresh_dashboard_metrics` and its helpers:
  - `raids_completed_display = max(0, raids_completed - resets.raids_completed_offset)`
  - `raids_failed_display = max(0, raids_failed - resets.raids_failed_offset)`
  - `success_rate` from delta completed/delta failed
  - `uptime` from `resets.uptime_reset_at or self._bot_session_started_at`
  - filter successful runs by `avg_completion_reset_at` and `avg_raids_per_hour_reset_at` before computing averages/rates

Do not remove the existing activity log or raw state values; only change displayed dashboard values.

- [ ] **Step 4: Run the targeted main-window tests to verify they pass**

Run:

```bash
python -m pytest -q tests\desktop\test_main_window.py -k "metric_cards_expose_reset_buttons or metric_reset_button_resets_only_its_own_metric or dashboard_metrics_respect_reset_baselines or dashboard_exposes_metric_cards_and_panels"
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/desktop/main_window.py tests/desktop/test_main_window.py
git commit -m "feat: add dashboard metric reset buttons"
```

### Task 4: Replace The Cumulative Chart Smoothing With A Stable Premium Renderer

**Files:**
- Modify: `raidbot/desktop/main_window.py`
- Test: `tests/desktop/test_main_window.py`

- [ ] **Step 1: Write the failing chart regression tests**

Add focused tests for the cumulative data and the chart subtitle:

```python
def test_main_window_builds_monotonic_cumulative_raid_series(qtbot):
    window = build_window(FakeController(), FakeStorage())
    qtbot.addWidget(window)
    series = window._build_recent_raid_activity_series([...])
    assert series == sorted(series)
    assert series[-1] == 6


def test_raid_activity_chart_accepts_sparse_cumulative_series(qtbot):
    chart = RaidActivityChart()
    qtbot.addWidget(chart)
    chart.set_series([0] * 20 + [1, 5, 18, 19])
    assert chart._series[-4:] == [1, 5, 18, 19]
```

Keep these tests data-focused; do not try to pixel-snapshot the widget.

- [ ] **Step 2: Run the targeted chart tests to verify current behavior is not yet covered**

Run:

```bash
python -m pytest -q tests\desktop\test_main_window.py -k "builds_monotonic_cumulative_raid_series or raid_activity_chart_accepts_sparse_cumulative_series"
```

Expected: FAIL until the new expectations are present and the chart path update is implemented.

- [ ] **Step 3: Implement the safer smooth cumulative renderer**

In `RaidActivityChart.paintEvent`:

- keep the current cumulative series input
- replace the current `quadTo(... midpoint)` loop with a safer smooth path builder that does not generate broken joins on steep late rises
- simplest acceptable shape:
  - compute ordered points
  - draw a smooth monotonic-ish cubic/quad path using neighbor-aware control points
  - never reverse x-order
- keep:
  - dark chart frame
  - subtle fill gradient
  - glow + main stroke
- soften grid contrast slightly so the line carries more of the visual weight

If the custom interpolation still risks artifacts, prefer a visually clean polyline with premium stroke/fill over another broken smoothing attempt.

- [ ] **Step 4: Run the targeted chart tests to verify they pass**

Run:

```bash
python -m pytest -q tests\desktop\test_main_window.py -k "builds_monotonic_cumulative_raid_series or raid_activity_chart_accepts_sparse_cumulative_series or dashboard_exposes_metric_cards_and_panels"
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/desktop/main_window.py tests/desktop/test_main_window.py
git commit -m "fix: polish cumulative raid activity chart"
```

### Task 5: Final Focused Verification

**Files:**
- Modify: none
- Test: `tests/desktop/test_storage.py`
- Test: `tests/desktop/test_controller.py`
- Test: `tests/desktop/test_worker.py`
- Test: `tests/desktop/test_main_window.py`

- [ ] **Step 1: Run the focused reset/migration slice**

Run:

```bash
python -m pytest -q tests\desktop\test_storage.py -k "dashboard_metric_reset_state or migrates_legacy_dashboard_timestamps_to_local_time_once" tests\desktop\test_controller.py -k dashboard_metric tests\desktop\test_worker.py -k reset_dashboard_metric
```

Expected: PASS

- [ ] **Step 2: Run the focused dashboard UI slice**

Run:

```bash
python -m pytest -q tests\desktop\test_main_window.py -k "metric_cards_expose_reset_buttons or metric_reset_button_resets_only_its_own_metric or dashboard_metrics_respect_reset_baselines or builds_monotonic_cumulative_raid_series or raid_activity_chart_accepts_sparse_cumulative_series"
```

Expected: PASS

- [ ] **Step 3: Run the broader desktop smoke slice**

Run:

```bash
python -m pytest -q tests\desktop\test_storage.py tests\desktop\test_controller.py tests\desktop\test_worker.py tests\desktop\test_main_window.py -k "dashboard_metric or activity_feed_row or initializes_from_persisted_state_and_updates_from_signals or dashboard_exposes_metric_cards_and_panels"
```

Expected: PASS, or if the existing Qt teardown hang reappears on the broader file set, capture that explicitly and keep the smaller passing slices as verification evidence.

- [ ] **Step 4: Commit the integrated change**

```bash
git add raidbot/desktop/models.py raidbot/desktop/storage.py raidbot/desktop/controller.py raidbot/desktop/worker.py raidbot/desktop/main_window.py tests/desktop/test_storage.py tests/desktop/test_controller.py tests/desktop/test_worker.py tests/desktop/test_main_window.py
git commit -m "feat: add dashboard metric resets and chart polish"
```
