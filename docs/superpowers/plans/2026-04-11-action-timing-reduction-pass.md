# Action Timing Reduction Pass Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce visible automation hesitation by lowering move-click, scroll-settle, and click-confirmation timings across raid actions.

**Architecture:** Keep the change narrow and mechanical. Update the shared timing defaults in the input/runner/worker layers, then lock the new behavior with focused timing tests so reply, repost, and page-exit all inherit the faster timings safely.

**Tech Stack:** Python, PySide6 desktop app, pytest

---

### Task 1: Reduce Shared Input And Runner Timing Constants

**Files:**
- Modify: `raidbot/desktop/automation/input.py`
- Modify: `raidbot/desktop/automation/runner.py`
- Test: `tests/desktop/automation/test_input.py`
- Test: `tests/desktop/automation/test_runner.py`

- [ ] **Step 1: Write the failing timing tests**

Add focused tests that prove:
- generic `move_click()` now waits `0.25s`
- runner scroll settle now uses `0.5s`
- runner click confirmation window now uses `1.5s`
- slot 1 final reply click now uses `0.25s`
- repost retry timing now uses `0.25s` gaps

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest -q tests\desktop\automation\test_input.py tests\desktop\automation\test_runner.py -k "move_click or scroll_settle or click_confirmation or slot_1 or repost"`

Expected: FAIL because the old timing values are still in code.

- [ ] **Step 3: Write the minimal implementation**

Update:
- `raidbot/desktop/automation/input.py`
  - default `move_click(..., delay_seconds=0.25)`
- `raidbot/desktop/automation/runner.py`
  - `_SCROLL_SETTLE_SECONDS = 0.5`
  - `click_confirmation_seconds` default `1.5`
  - slot 1 reply open / final / retry `move_click(..., delay_seconds=0.25)`
  - repost click paths use `0.25s` timing

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest -q tests\desktop\automation\test_input.py tests\desktop\automation\test_runner.py -k "move_click or scroll_settle or click_confirmation or slot_1 or repost"`

Expected: PASS

- [ ] **Step 5: Commit**

Run:
- `git add raidbot/desktop/automation/input.py raidbot/desktop/automation/runner.py tests/desktop/automation/test_input.py tests/desktop/automation/test_runner.py`
- `git commit -m "feat: reduce action timing delays"`

### Task 2: Reduce Worker Page Exit Timing

**Files:**
- Modify: `raidbot/desktop/worker.py`
- Test: `tests/desktop/test_worker.py`

- [ ] **Step 1: Write the failing worker test**

Add or update a focused worker test that proves the `Page Exit` click uses `0.25s` move-click timing instead of the older delay.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest -q tests\desktop\test_worker.py -k "page_exit"`

Expected: FAIL because the worker still uses the old page-exit click delay.

- [ ] **Step 3: Write the minimal implementation**

Update `raidbot/desktop/worker.py` so `_click_page_exit_for_profile(...)` uses `move_click(..., delay_seconds=0.25)`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest -q tests\desktop\test_worker.py -k "page_exit"`

Expected: PASS

- [ ] **Step 5: Commit**

Run:
- `git add raidbot/desktop/worker.py tests/desktop/test_worker.py`
- `git commit -m "feat: reduce page exit click timing"`

### Task 3: Bump Version And Run Focused Verification

**Files:**
- Modify: `pyproject.toml`
- Modify: `raidbot/__init__.py`
- Modify: `tests/desktop/test_packaging.py`

- [ ] **Step 1: Bump the version**

Update:
- `pyproject.toml`
- `raidbot/__init__.py`
- `tests/desktop/test_packaging.py`

Use the next patch version after the current workspace version.

- [ ] **Step 2: Run focused verification**

Run: `python -m pytest -q tests\desktop\automation\test_input.py tests\desktop\automation\test_runner.py tests\desktop\test_worker.py tests\desktop\test_packaging.py -k "move_click or scroll_settle or click_confirmation or slot_1 or repost or page_exit or beta_zip_name or build_beta_readme"`

Expected: PASS

- [ ] **Step 3: Commit**

Run:
- `git add pyproject.toml raidbot/__init__.py tests/desktop/test_packaging.py`
- `git commit -m "chore: bump version for action timing pass"`
