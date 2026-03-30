# Dashboard Chart And Sidebar Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a compact 24-hour raid activity chart, tighten the sidebar/dashboard layout, simplify Recent Activity, and normalize dashboard text/metric formatting without changing runtime behavior.

**Architecture:** Keep this pass localized to the desktop shell. `raidbot/desktop/main_window.py` remains the place that builds the dashboard, sidebar, metrics, and activity feed, while `raidbot/desktop/theme.py` provides the visual polish. Tests stay concentrated in `tests/desktop/test_main_window.py` so the UI refresh is covered end-to-end without touching runtime code.

**Tech Stack:** PySide6 widgets/painting, existing desktop theme system, pytest + pytest-qt

---

## File Structure

- Modify: `raidbot/desktop/main_window.py`
  - Remove duplicate command-strip status labels
  - Add the raid activity chart widget and chart-data summarization
  - Tighten sidebar/dashboard layout
  - Simplify Recent Activity rows and title-case visible status strings
  - Change zero-data metric formatting from `—` to numeric zeroes
- Modify: `raidbot/desktop/theme.py`
  - Reduce sidebar width
  - Tighten nav buttons, footer cards, activity pills, and command buttons
  - Add chart styling and stronger dashboard error-card styling
- Modify: `tests/desktop/test_main_window.py`
  - Cover the chart data builder/formatters
  - Cover removed duplicate labels
  - Cover Recent Activity filtering/rendering changes
  - Cover updated sidebar/dashboard text

## Task 1: Lock Down Metric And Activity Rules In Tests

**Files:**
- Modify: `tests/desktop/test_main_window.py`
- Reference: `raidbot/desktop/main_window.py`

- [ ] **Step 1: Add a failing test for zero-data metric formatting**

```python
def test_main_window_formats_zero_dashboard_metrics_without_em_dash(qtbot) -> None:
    window = build_window(FakeController(), FakeStorage())
    qtbot.addWidget(window)

    assert window._format_average_completion_time([]) == "0s"
    assert window._format_raids_per_hour(0) == "0.0/hr"
    assert window._format_success_rate(0, 0) == "0%"
```

- [ ] **Step 2: Run the focused test to confirm current behavior fails**

Run: `python -m pytest -q tests\desktop\test_main_window.py -k "zero_dashboard_metrics_without_em_dash"`

Expected: FAIL because the formatters currently return `—`.

- [ ] **Step 3: Add a failing test for Recent Activity filtering and reason-column removal**

```python
def test_main_window_hides_chat_rejected_and_activity_reason_column_noise(qtbot) -> None:
    window = build_window(FakeController(), FakeStorage())
    qtbot.addWidget(window)

    assert window._should_display_activity("chat_rejected") is False
    assert "activityReason" not in window._build_activity_row(...).objectName()
```
```

Use the real helper names that already exist in `main_window.py`; if there is no row helper yet, assert against the constructed `ActivityFeedRow` child labels instead.

- [ ] **Step 4: Add a failing test for the sidebar/dashboard text cleanup**

```python
def test_main_window_uses_title_case_dashboard_labels(qtbot) -> None:
    window = build_window(FakeController(), FakeStorage())
    qtbot.addWidget(window)

    window._update_bot_state("running")
    window._update_connection_state("connected")

    assert window.bot_state_label.text() == ""
    assert window.connection_state_label.text() == ""
    assert window.command_bot_state_label.text() == ""
    assert window.command_connection_state_label.text() == ""
    assert window.sidebar_success_rate_title_label.text() == "Success Rate"
```
```

Adjust the expectations to the actual widget names after removing the duplicate command-row labels.

- [ ] **Step 5: Run the focused dashboard test slice**

Run: `python -m pytest -q tests\desktop\test_main_window.py -k "zero_dashboard_metrics_without_em_dash or chat_rejected or title_case_dashboard_labels"`

Expected: FAIL with the old formatting/filtering/layout assumptions.

- [ ] **Step 6: Commit the failing tests**

```bash
git add tests/desktop/test_main_window.py
git commit -m "test: pin dashboard chart sidebar polish behavior"
```

## Task 2: Implement Dashboard Metrics, Status Cleanup, And Activity Feed Simplification

**Files:**
- Modify: `raidbot/desktop/main_window.py`
- Test: `tests/desktop/test_main_window.py`

- [ ] **Step 1: Remove duplicate command-strip runtime labels**

Delete the top-right duplicate status labels near `Start` / `Stop`, but keep `System Status` as the source of truth.

The command row should end with centered `Start` / `Stop` buttons only.

- [ ] **Step 2: Title-case the visible status text**

Use a tiny formatter rather than raw internal state strings:

```python
def _format_status_caption(value: str) -> str:
    return value.replace("_", " ").title()
```

Use it where the dashboard shows:
- `Running`
- `Connected`

Do not change internal state values or runtime logic.

- [ ] **Step 3: Change metric formatters to return zero values**

Update these helpers in `main_window.py`:

```python
def _format_average_completion_time(self, durations: list[float]) -> str:
    if not durations:
        return "0s"

def _format_raids_per_hour(self, completed_count: int) -> str:
    if completed_count <= 0:
        return "0.0/hr"

def _format_success_rate(self, completed_count: int, opened_count: int) -> str:
    if opened_count <= 0:
        return "0%"
```

- [ ] **Step 4: Simplify `ActivityFeedRow`**

Reshape the row to:
- timestamp
- smaller pill
- URL
- optional reason only when it is actually useful

Remove the far-right raw action/status text column entirely.

If a reason is missing or redundant with the badge, hide that label instead of showing placeholder noise.

- [ ] **Step 5: Extend activity filtering**

Ensure `_should_display_activity()` also hides:

```python
{"duplicate", "sender_rejected", "chat_rejected"}
```

- [ ] **Step 6: Run focused dashboard/activity tests**

Run: `python -m pytest -q tests\desktop\test_main_window.py -k "dashboard or activity or status"`

Expected: PASS for the new formatting/filtering rules.

- [ ] **Step 7: Commit the dashboard/feed logic cleanup**

```bash
git add raidbot/desktop/main_window.py tests/desktop/test_main_window.py
git commit -m "feat: simplify dashboard metrics and activity feed"
```

## Task 3: Add The Raid Activity Chart And Rebalance The Dashboard Layout

**Files:**
- Modify: `raidbot/desktop/main_window.py`
- Test: `tests/desktop/test_main_window.py`

- [ ] **Step 1: Add a failing test for 24-hour hourly bucket generation**

```python
def test_main_window_builds_hourly_completed_raid_buckets_from_recent_activity(qtbot) -> None:
    window = build_window(FakeController(), FakeStorage())
    qtbot.addWidget(window)

    buckets = window._build_recent_raid_activity_series([...])

    assert len(buckets) == 24
    assert sum(buckets) == 3
```

- [ ] **Step 2: Run the new chart-data test**

Run: `python -m pytest -q tests\desktop\test_main_window.py -k "hourly_completed_raid_buckets"`

Expected: FAIL because the chart-series helper/widget does not exist yet.

- [ ] **Step 3: Add a focused chart widget in `main_window.py`**

Keep it local and lightweight:

```python
class RaidActivityChart(QFrame):
    def set_series(self, values: list[int]) -> None: ...
    def paintEvent(self, event) -> None: ...
```

Requirements:
- 24 buckets
- compact dark grid
- smooth line/filled area style
- no dependency on external chart libraries

- [ ] **Step 4: Add a chart-series summarizer**

Build completed-raid buckets from recent activity keyed by whole raid URL:

```python
def _build_recent_raid_activity_series(self, entries: list[ActivityEntry]) -> list[int]:
    ...
```

Count only completed whole raids in the rolling last 24 hours.

- [ ] **Step 5: Rework the `System Status` surface layout**

Update the dashboard section so it becomes a two-column surface:
- left: existing system status content
- right: `Raid Activity` chart block

Do not add a second outer card; keep it visually integrated.

- [ ] **Step 6: Run the focused chart/dashboard tests**

Run: `python -m pytest -q tests\desktop\test_main_window.py -k "raid_activity or hourly_completed_raid_buckets or system_status"`

Expected: PASS with the new chart and layout.

- [ ] **Step 7: Commit the chart/layout work**

```bash
git add raidbot/desktop/main_window.py tests/desktop/test_main_window.py
git commit -m "feat: add raid activity chart to dashboard"
```

## Task 4: Tighten Sidebar, Buttons, Pills, And Error Card Styling

**Files:**
- Modify: `raidbot/desktop/theme.py`
- Modify: `raidbot/desktop/main_window.py`
- Test: `tests/desktop/test_main_window.py`

- [ ] **Step 1: Add a failing UI-structure test for the tighter sidebar**

```python
def test_main_window_uses_compact_sidebar_width_and_footer_copy(qtbot) -> None:
    window = build_window(FakeController(), FakeStorage())
    qtbot.addWidget(window)

    assert window.sidebar.width() < 210
    assert window.sidebar_success_rate_title_label.text() == "Success Rate"
    assert window.sidebar.findChildren(QLabel, "sidebarMetricSubtitle")[0].text() == "Last 24 Hours"
```
```

Adapt the exact assertions to the final widget exposure.

- [ ] **Step 2: Tighten theme constants and sidebar/button styling**

Update `theme.py` to:
- reduce `NAV_SIDEBAR_WIDTH`
- reduce nav button min-height/padding
- reduce footer card padding
- center nav/button text cleanly
- tighten activity pill height/padding
- style the dashboard error section more like a deliberate status card

- [ ] **Step 3: Update sidebar/footer copy in `main_window.py`**

Use:
- `Success Rate`
- `Last 24 Hours`
- `Uptime`
- `Uptime Since Last Start`

- [ ] **Step 4: Run the focused sidebar/theme tests**

Run: `python -m pytest -q tests\desktop\test_main_window.py -k "compact_sidebar or footer_copy or dashboard"`

Expected: PASS with the compressed sidebar and corrected copy.

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest -q`

Expected: PASS

- [ ] **Step 6: Commit the polish pass**

```bash
git add raidbot/desktop/main_window.py raidbot/desktop/theme.py tests/desktop/test_main_window.py
git commit -m "feat: polish dashboard sidebar and chart layout"
```

## Notes For The Implementer

- Keep all metric derivation keyed to whole raid URLs, never per-profile attempts.
- Do not change worker/controller/runtime code in this pass.
- Reuse existing dashboard helpers where possible; avoid creating a second metrics subsystem.
- Prefer small local helper methods and one local chart widget over introducing a new charts module.
- If the `Last Error` area is currently a bare label, wrap it in a stronger card surface rather than inventing new state.
