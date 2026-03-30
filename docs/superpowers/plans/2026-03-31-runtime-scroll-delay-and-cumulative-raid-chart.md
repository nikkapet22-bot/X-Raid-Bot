# Runtime Scroll Delay And Cumulative Raid Activity Chart Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce normal runtime slot-search delay before scrolling from 8 seconds to 2 seconds and turn the dashboard raid activity chart into a cumulative premium-looking successful-profile trend.

**Architecture:** Keep the runtime change minimal by lowering only the normal bot-action search constant while leaving slot tests untouched. Rework the existing custom `RaidActivityChart` widget to render a more polished cumulative series without introducing any charting library or storage changes.

**Tech Stack:** Python, PySide6, pytest

---

## File Map

- `raidbot/desktop/bot_actions/sequence.py`
  - owns the normal runtime slot-search timing constants.
- `tests/desktop/bot_actions/test_sequence.py`
  - pins runtime vs test search timing behavior.
- `raidbot/desktop/main_window.py`
  - builds the raid activity series and renders the custom chart widget.
- `tests/desktop/test_main_window.py`
  - verifies chart semantics and dashboard rendering behavior.

### Task 1: Lower Normal Runtime Slot Search Delay To 2 Seconds

**Files:**
- Modify: `raidbot/desktop/bot_actions/sequence.py`
- Test: `tests/desktop/bot_actions/test_sequence.py`

- [ ] **Step 1: Write the failing timing expectation**

Update the existing runtime-sequence test expectation:

```python
assert all(step.max_search_seconds == 2.0 for step in sequence.steps)
```

Leave the slot-test assertion unchanged:

```python
assert [step.max_search_seconds for step in sequence.steps] == [1.0]
```

- [ ] **Step 2: Run the sequence tests to verify the runtime expectation fails**

Run:

```bash
python -m pytest -q tests\desktop\bot_actions\test_sequence.py
```

Expected: FAIL because runtime steps still use `8.0`.

- [ ] **Step 3: Implement the minimal timing change**

In `raidbot/desktop/bot_actions/sequence.py`, change:

```python
BOT_ACTION_STEP_SEARCH_SECONDS = 8.0
```

to:

```python
BOT_ACTION_STEP_SEARCH_SECONDS = 2.0
```

Do not change:

- `SLOT_TEST_STEP_SEARCH_SECONDS`
- `BOT_ACTION_SLOT_SCROLL_ATTEMPTS`
- slot-1 finish-image timing in the runner

- [ ] **Step 4: Run the sequence tests to verify they pass**

Run:

```bash
python -m pytest -q tests\desktop\bot_actions\test_sequence.py
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/desktop/bot_actions/sequence.py tests/desktop/bot_actions/test_sequence.py
git commit -m "feat: reduce runtime slot search delay"
```

### Task 2: Make Raid Activity Series Cumulative

**Files:**
- Modify: `raidbot/desktop/main_window.py`
- Test: `tests/desktop/test_main_window.py`

- [ ] **Step 1: Write the failing cumulative-series test**

Update the existing raid activity series test to assert cumulative behavior from successful profile raids:

```python
assert len(series) == 24
assert sum(series) > 0
assert series[-1] == 3
assert max(series) == 3
```

For the sample with one success 4 hours ago and two more around 1 hour ago, the later buckets should reflect the running total instead of independent hourly counts.

- [ ] **Step 2: Run the targeted main-window test to verify it fails**

Run:

```bash
python -m pytest -q tests\desktop\test_main_window.py -k builds_hourly_completed_raid_buckets_from_recent_activity
```

Expected: FAIL because the builder still returns raw hourly counts.

- [ ] **Step 3: Implement minimal cumulative-series conversion**

Keep the hourly bucketing first, then convert in-place:

```python
running_total = 0
for index, value in enumerate(series):
    running_total += value
    series[index] = running_total
```

Apply this in `_build_recent_raid_activity_series()` after the hourly success buckets are populated.

- [ ] **Step 4: Run the targeted test to verify it passes**

Run:

```bash
python -m pytest -q tests\desktop\test_main_window.py -k builds_hourly_completed_raid_buckets_from_recent_activity
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/desktop/main_window.py tests/desktop/test_main_window.py
git commit -m "feat: make raid activity chart cumulative"
```

### Task 3: Polish Raid Activity Chart Rendering

**Files:**
- Modify: `raidbot/desktop/main_window.py`
- Test: `tests/desktop/test_main_window.py`

- [ ] **Step 1: Write or adjust the chart-rendering safety test**

Use existing dashboard tests rather than image snapshot tests. Ensure the chart still mounts and receives the computed series:

```python
assert window.raid_activity_chart.objectName() == "raidActivityChart"
assert window.raid_activity_chart is not None
```

If there is already sufficient coverage for construction, do not add brittle pixel tests.

- [ ] **Step 2: Run the targeted dashboard tests to establish a baseline**

Run:

```bash
python -m pytest -q tests\desktop\test_main_window.py -k "dashboard_exposes_metric_cards_and_panels or uses_current_automation_activity_for_dashboard_metrics"
```

Expected: PASS before visual polish, proving semantics are stable.

- [ ] **Step 3: Implement the premium chart styling**

In `RaidActivityChart.paintEvent()`:

- soften the background/frame treatment
- reduce harsh grid contrast
- strengthen the primary line
- add a cleaner translucent fill under the line
- add a subtle accent/glow pass if it can be done simply with the existing painter workflow

Guidelines:

- do not change widget size or layout footprint
- do not add a dependency
- keep labels readable in the current theme

- [ ] **Step 4: Re-run the targeted dashboard tests**

Run:

```bash
python -m pytest -q tests\desktop\test_main_window.py -k "dashboard_exposes_metric_cards_and_panels or uses_current_automation_activity_for_dashboard_metrics or builds_hourly_completed_raid_buckets_from_recent_activity"
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/desktop/main_window.py tests/desktop/test_main_window.py
git commit -m "feat: polish raid activity chart styling"
```

### Task 4: Final Regression Pass

**Files:**
- Modify: none
- Test: `tests/desktop/bot_actions/test_sequence.py`
- Test: `tests/desktop/test_main_window.py`

- [ ] **Step 1: Run the focused regression suite**

Run:

```bash
python -m pytest -q tests\desktop\bot_actions\test_sequence.py tests\desktop\test_main_window.py -k "builds_hourly_completed_raid_buckets_from_recent_activity or uses_current_automation_activity_for_dashboard_metrics or dashboard_exposes_metric_cards_and_panels or places_slot_1_last or keeps_shorter_search_window"
```

Expected: PASS

- [ ] **Step 2: Run the full bot-action sequence file**

Run:

```bash
python -m pytest -q tests\desktop\bot_actions\test_sequence.py
```

Expected: PASS

- [ ] **Step 3: Run the broader main-window verification slice**

Run:

```bash
python -m pytest -q tests\desktop\test_main_window.py -k "initializes_from_persisted_state_and_updates_from_signals or builds_hourly_completed_raid_buckets_from_recent_activity or uses_current_automation_activity_for_dashboard_metrics or dashboard_exposes_metric_cards_and_panels"
```

Expected: PASS

- [ ] **Step 4: Commit the integrated change**

```bash
git add raidbot/desktop/bot_actions/sequence.py raidbot/desktop/main_window.py tests/desktop/bot_actions/test_sequence.py tests/desktop/test_main_window.py
git commit -m "feat: speed up slot scrolling and refresh raid chart"
```
