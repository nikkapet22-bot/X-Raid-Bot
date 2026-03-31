# Last Successful Raid Display Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the raw `Last successful raid` ISO timestamp with a readable dashboard label such as `Today, 18:42` or `Yesterday, 18:42`.

**Architecture:** Keep the existing `System Status` row layout and only change how the value is formatted before it is assigned to `last_successful_label`. Add a small formatter in the main window and cover the display cases with focused UI tests.

**Tech Stack:** Python, PySide6, pytest, pytest-qt

---

### Task 1: Add Display Formatting Tests

**Files:**
- Modify: `tests/desktop/test_main_window.py`
- Modify: `raidbot/desktop/main_window.py`

- [ ] **Step 1: Write the failing tests**

Add focused tests for:
- same-day timestamp -> `Today, HH:MM`
- yesterday timestamp -> `Yesterday, HH:MM`
- older this year -> `Mon DD, HH:MM`
- older previous year -> `Mon DD, YYYY, HH:MM`
- empty value -> `No successful raid yet`
- invalid string -> original string

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest -q tests\desktop\test_main_window.py -k "last_successful_raid"`

Expected: FAIL because the dashboard still renders the raw stored string.

- [ ] **Step 3: Write the minimal implementation**

Add a helper in `raidbot/desktop/main_window.py` that:
- parses ISO timestamps safely
- compares against local `datetime.now()`
- returns the desired label format
- falls back to the original string if parsing fails

Wire it into the existing `last_successful_label` assignment path.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest -q tests\desktop\test_main_window.py -k "last_successful_raid"`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/desktop/main_window.py tests/desktop/test_main_window.py
git commit -m "feat: format last successful raid display"
```

### Task 2: Run Focused Dashboard Verification

**Files:**
- Verify: `tests/desktop/test_main_window.py`

- [ ] **Step 1: Run dashboard smoke slice**

Run: `python -m pytest -q tests\desktop\test_main_window.py -k "initializes_from_persisted_state_and_updates_from_signals or dashboard_exposes_metric_cards_and_panels"`

Expected: PASS

- [ ] **Step 2: Confirm no extra UI changes leaked in**

Check that only the `Last successful raid` display changed and the rest of `System Status` remains unchanged.

- [ ] **Step 3: Commit if verification required additional adjustments**

```bash
git add raidbot/desktop/main_window.py tests/desktop/test_main_window.py
git commit -m "test: verify last successful raid dashboard formatting"
```
