# Auto CLDF Troubleshoot Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automatically enter the CLDF troubleshoot path when `Page Ready` times out, recover the profile if CLDF succeeds, and leave it red if CLDF fails.

**Architecture:** Keep the behavior worker-owned. The worker already owns page-ready timeout handling, profile state transitions, and active Chrome window cleanup, so the new CLDF recovery path should be inserted directly into the existing page-ready timeout branch. Manual CLDF capture/test UI remains unchanged and is not reused for orchestration beyond providing the saved template files.

**Tech Stack:** Python, PySide6 desktop app, existing desktop automation runtime, pytest

---

### Task 1: Add worker tests for CLDF recovery entry and outcomes

**Files:**
- Modify: `tests/desktop/test_worker.py`
- Reference: `raidbot/desktop/worker.py`

- [ ] **Step 1: Write a failing test for successful CLDF recovery after page-ready timeout**

Add a worker test near the existing page-ready timeout coverage that:

- configures `page_ready_template_path`
- makes `_wait_for_page_ready()` fail with `page_ready_not_found`
- provides existing CLDF capture files under `tmp_path/bot_actions/troubleshoot`
- uses a fake runtime that:
  - fails the page-ready probe
  - then succeeds on all three CLDF step probes/runs
- expects:
  - no normal bot-action sequence run for the current raid
  - active Chrome window closed once
  - profile state becomes `green`
  - `last_error=None`
  - `raids_completed` stays unchanged
  - current raid is not counted as success

- [ ] **Step 2: Run the new test to verify it fails**

Run: `python -m pytest -q tests\desktop\test_worker.py -k "cldf and page_ready"`

Expected: FAIL because CLDF auto-recovery does not exist yet.

- [ ] **Step 3: Write a failing test for missing CLDF step template**

Add a worker test that:

- triggers `page_ready_not_found`
- omits `cldf_1.png`
- expects:
  - immediate failure
  - profile remains `red`
  - `last_error` reflects missing CLDF step

- [ ] **Step 4: Run the focused tests again**

Run: `python -m pytest -q tests\desktop\test_worker.py -k "cldf and page_ready"`

Expected: FAIL with both CLDF recovery tests red.

- [ ] **Step 5: Write a failing test for CLDF step match failure mid-sequence**

Add a worker test that:

- provides all three CLDF template files
- makes `CLDF 1` succeed
- makes `CLDF 2` fail to match
- expects:
  - profile remains `red`
  - window not treated as recovered
  - failure reason points at CLDF step 2

- [ ] **Step 6: Run the focused tests once more**

Run: `python -m pytest -q tests\desktop\test_worker.py -k "cldf and page_ready"`

Expected: FAIL with the new CLDF failure-case tests.

- [ ] **Step 7: Commit the failing tests**

```bash
git add tests/desktop/test_worker.py
git commit -m "test: add CLDF troubleshoot recovery worker coverage"
```

### Task 2: Implement worker-owned CLDF recovery path

**Files:**
- Modify: `raidbot/desktop/worker.py`
- Reference: `raidbot/desktop/automation/runtime.py`
- Test: `tests/desktop/test_worker.py`

- [ ] **Step 1: Reduce page-ready timeout to 5 seconds**

In `raidbot/desktop/worker.py`, update the page-ready probe step construction so:

- `max_search_seconds=5.0`

and nowhere else in the worker should still assume the previous `8.0s` timeout for page-ready.

- [ ] **Step 2: Add fixed CLDF troubleshoot template path helpers**

In `raidbot/desktop/worker.py`, add small focused helpers:

- `_troubleshoot_template_relative_path(group_key: str, item_index: int) -> Path`
- `_troubleshoot_template_path(group_key: str, item_index: int) -> Path`

These should resolve:

- `cldf`, `0` -> `base_dir/bot_actions/troubleshoot/cldf_1.png`
- `cldf`, `1` -> `.../cldf_2.png`
- `cldf`, `2` -> `.../cldf_3.png`

Use the worker’s storage base dir pattern already used elsewhere in the desktop app.

- [ ] **Step 3: Add a single CLDF step executor helper**

Implement a helper in `raidbot/desktop/worker.py`, for example:

```python
def _run_troubleshoot_step(
    self,
    runtime: Any,
    opened_window: Any,
    *,
    group_key: str,
    item_index: int,
    settle_seconds: float = 5.0,
) -> str | None:
    ...
```

Behavior:

- resolve the fixed template path
- if missing: return `troubleshoot_cldf_<n>_missing`
- call `runtime.wait_for_step_match(...)` against the currently opened Chrome window
- if no match: return `troubleshoot_cldf_<n>_not_found`
- if match succeeds:
  - move/click through the same runtime path used by automation
  - wait `5.0` seconds
  - return `None`

Keep this helper focused on one required troubleshoot step.

- [ ] **Step 4: Add a CLDF sequence helper**

Implement a helper in `raidbot/desktop/worker.py`, for example:

```python
def _run_cldf_troubleshoot(
    self,
    runtime: Any,
    opened_window: Any,
) -> str | None:
    ...
```

Behavior:

- call `_run_troubleshoot_step(..., "cldf", 0)`
- then step 1
- then step 2
- fail fast on the first non-`None` reason
- return `None` only if all three steps succeed

- [ ] **Step 5: Insert CLDF recovery into the page-ready timeout branch**

In `_execute_raid_for_profile(...)`, replace the current immediate failure behavior for `page_ready_not_found` with:

- call `_run_cldf_troubleshoot(...)`
- if it returns `None`:
  - close the automation window
  - set profile state back to `green`
  - clear `last_error`
  - return `(False, True, None)` or equivalent non-success recovery result
- if it returns a reason:
  - record normal profile failure with that reason
  - leave profile `red`

Important:

- this branch must not call `_record_raid_profile_success(...)`
- it must not increment success counters
- it must not continue into the normal bot-action sequence

- [ ] **Step 6: Run the focused CLDF tests**

Run: `python -m pytest -q tests\desktop\test_worker.py -k "cldf and page_ready"`

Expected: PASS.

- [ ] **Step 7: Commit the worker implementation**

```bash
git add raidbot/desktop/worker.py tests/desktop/test_worker.py
git commit -m "feat: add auto CLDF troubleshoot recovery"
```

### Task 3: Verify surrounding worker behavior still holds

**Files:**
- Test: `tests/desktop/test_worker.py`
- Test: `tests/desktop/test_controller.py`
- Reference: `raidbot/desktop/main_window.py`

- [ ] **Step 1: Run the page-ready and profile-state worker slice**

Run:

`python -m pytest -q tests\desktop\test_worker.py -k "page_ready or restart_raid_profile or skips_failed_profile_until_restarted"`

Expected: PASS.

- [ ] **Step 2: Run the Bot Actions page/main-window slice that already covers troubleshoot capture/test**

Run:

`python -m pytest -q tests\desktop\test_main_window.py -k "troubleshoot or bot_actions or capture_updates or slot_test" tests\desktop\bot_actions\test_page.py`

Expected: PASS.

- [ ] **Step 3: Run a compact controller slice to ensure manual slot test behavior still passes after worker changes**

Run:

`python -m pytest -q tests\desktop\test_controller.py -k "slot_test or troubleshoot_test"`

Expected: PASS.

- [ ] **Step 4: Commit the verification state**

```bash
git add raidbot/desktop/worker.py tests/desktop/test_worker.py
git commit -m "test: verify CLDF recovery integration"
```

### Task 4: Optional polish if verification reveals ambiguous failure reasons

**Files:**
- Modify: `raidbot/desktop/worker.py`
- Test: `tests/desktop/test_worker.py`

- [ ] **Step 1: Only if needed, normalize CLDF failure reasons**

If the verification output shows vague reasons like `match_not_found`, add explicit reason mapping in the worker so CLDF failures produce user-meaningful reasons:

- `troubleshoot_cldf_1_missing`
- `troubleshoot_cldf_1_not_found`
- `troubleshoot_cldf_2_not_found`
- `troubleshoot_cldf_3_not_found`
- `troubleshoot_window_close_failed`

- [ ] **Step 2: Add or update one worker test for the normalized reason**

Run:

`python -m pytest -q tests\desktop\test_worker.py -k "troubleshoot_cldf"`

Expected: PASS.

- [ ] **Step 3: Commit only if this polish was necessary**

```bash
git add raidbot/desktop/worker.py tests/desktop/test_worker.py
git commit -m "fix: normalize CLDF troubleshoot failure reasons"
```
