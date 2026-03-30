# Local Activity Timestamps And Recent Activity Reason Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make new dashboard activity timestamps match local PC time and stop clipping activity reasons when the row has available horizontal space.

**Architecture:** Keep the timestamp fix at the source by switching the worker’s default clock from UTC to local time, and keep the UI fix local to `ActivityFeedRow` by removing the hard width cap on the reason label while preserving right alignment and stable parenting.

**Tech Stack:** Python, PySide6, pytest

---

## File Map

- `raidbot/desktop/worker.py`
  - owns the default activity timestamp source for newly recorded desktop events.
- `tests/desktop/test_worker.py`
  - verifies worker activity timestamps and behavior under a deterministic injected clock.
- `raidbot/desktop/main_window.py`
  - builds `ActivityFeedRow` and controls Recent Activity row layout.
- `tests/desktop/test_main_window.py`
  - verifies the activity row layout and protects against flashing top-level reason labels.

### Task 1: Switch Worker Default Activity Clock To Local Time

**Files:**
- Modify: `raidbot/desktop/worker.py`
- Test: `tests/desktop/test_worker.py`

- [ ] **Step 1: Write the failing worker test for the default clock**

Add a small targeted test that monkeypatches `raidbot.desktop.worker.datetime` and verifies the default worker records local time:

```python
def test_worker_defaults_activity_clock_to_local_time(monkeypatch):
    class FakeDateTime:
        @staticmethod
        def now():
            return datetime(2026, 3, 31, 23, 6, 19)

        @staticmethod
        def utcnow():
            return datetime(2026, 3, 31, 20, 6, 19)

    monkeypatch.setattr(worker_module, "datetime", FakeDateTime)
    worker = worker_module.DesktopBotWorker(...)
    assert worker.now() == datetime(2026, 3, 31, 23, 6, 19)
```

Keep existing deterministic worker tests that pass `now=...` untouched.

- [ ] **Step 2: Run the targeted worker test to verify it fails**

Run:

```bash
python -m pytest -q tests\desktop\test_worker.py -k defaults_activity_clock_to_local_time
```

Expected: FAIL because the worker still defaults to `datetime.utcnow`.

- [ ] **Step 3: Implement the minimal clock-source change**

In `raidbot/desktop/worker.py`, change the constructor default:

```python
now: NowFactory = datetime.utcnow
```

to:

```python
now: NowFactory = datetime.now
```

Do not change explicit `now=` injections in tests or production wiring.

- [ ] **Step 4: Run the targeted worker test to verify it passes**

Run:

```bash
python -m pytest -q tests\desktop\test_worker.py -k defaults_activity_clock_to_local_time
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/desktop/worker.py tests/desktop/test_worker.py
git commit -m "fix: use local time for desktop activity"
```

### Task 2: Remove The Hard Reason Width In Recent Activity

**Files:**
- Modify: `raidbot/desktop/main_window.py`
- Test: `tests/desktop/test_main_window.py`

- [ ] **Step 1: Write the failing Recent Activity row test**

Add a small layout-focused test:

```python
def test_activity_feed_row_reason_label_is_not_hard_limited(qtbot):
    row = ActivityFeedRow(
        title="Automation Failed",
        tone="error",
        timestamp_text="23:06:03",
        url="https://x.com/i/status/1",
        reason_text="window_not_focusable",
    )
    qtbot.addWidget(row)
    reason_label = row.findChild(QLabel, "activityReason")
    assert reason_label.maximumWidth() >= 16777215
    assert reason_label.text() == "window_not_focusable"
```

Do not replace the existing flash-regression test; keep it.

- [ ] **Step 2: Run the targeted main-window tests to verify the new layout expectation fails**

Run:

```bash
python -m pytest -q tests\desktop\test_main_window.py -k "activity_feed_row_reason_label_is_not_hard_limited or activity_feed_row_does_not_flash_reason_label_as_top_level_window"
```

Expected: FAIL because the row still uses `reason_label.setFixedWidth(96)`.

- [ ] **Step 3: Implement the minimal row-layout fix**

In `ActivityFeedRow`:

- remove the `setFixedWidth(96)` call on `reason_label`
- keep:
  - right alignment
  - tooltip
  - explicit parenting before visibility
- if needed, use `setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)` so the reason label sizes naturally without stretching

Do not change the reason truncation helper in this task.

- [ ] **Step 4: Run the targeted main-window tests to verify they pass**

Run:

```bash
python -m pytest -q tests\desktop\test_main_window.py -k "activity_feed_row_reason_label_is_not_hard_limited or activity_feed_row_does_not_flash_reason_label_as_top_level_window"
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/desktop/main_window.py tests/desktop/test_main_window.py
git commit -m "fix: allow recent activity reasons to size naturally"
```

### Task 3: Final Focused Verification

**Files:**
- Modify: none
- Test: `tests/desktop/test_worker.py`
- Test: `tests/desktop/test_main_window.py`

- [ ] **Step 1: Run the focused verification slice**

Run:

```bash
python -m pytest -q tests\desktop\test_worker.py -k "defaults_activity_clock_to_local_time or records_sender_rejected_detection" tests\desktop\test_main_window.py -k "activity_feed_row_reason_label_is_not_hard_limited or activity_feed_row_does_not_flash_reason_label_as_top_level_window"
```

Expected: PASS

- [ ] **Step 2: Run the broader UI/worker smoke slice**

Run:

```bash
python -m pytest -q tests\desktop\test_worker.py tests\desktop\test_main_window.py -k "records_sender_rejected_detection or initializes_from_persisted_state_and_updates_from_signals or activity_feed_row"
```

Expected: PASS or, if the existing Qt teardown hang appears again on the broader file, capture that explicitly and keep the smaller passing commands as verification evidence.

- [ ] **Step 3: Commit the integrated change**

```bash
git add raidbot/desktop/worker.py raidbot/desktop/main_window.py tests/desktop/test_worker.py tests/desktop/test_main_window.py
git commit -m "fix: align activity time and reason layout"
```
