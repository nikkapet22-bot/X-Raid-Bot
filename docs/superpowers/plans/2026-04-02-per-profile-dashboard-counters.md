# Per-Profile Dashboard Counters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Switch `Raids Completed`, `Raids Failed`, and `Success Rate` to per-profile semantics and reset legacy whole-raid totals once.

**Architecture:** Keep the existing dashboard card UI, but change the runtime accounting so profile-level outcomes own the counters. Add a one-time state migration marker so persisted whole-raid totals are cleared before the new semantics begin.

**Tech Stack:** Python, PySide6 desktop app, dataclass-based state storage, pytest

---

## File Map

- Modify: `raidbot/desktop/models.py`
  - Add the one-time migration marker to persisted dashboard/state metadata.
- Modify: `raidbot/desktop/storage.py`
  - Reset legacy whole-raid completed/failed counters once during state load.
- Modify: `raidbot/desktop/worker.py`
  - Count completed/failed raids per profile and stop whole-raid summary helpers from mutating those counters.
- Modify: `tests/desktop/test_storage.py`
  - Cover the one-time migration reset behavior.
- Modify: `tests/desktop/test_worker.py`
  - Cover per-profile failure increments and whole-raid summary no longer touching counters.
- Modify: `tests/desktop/test_main_window.py`
  - Verify dashboard cards show the new per-profile totals and success-rate math after migration-aware state.

### Task 1: Add migration marker and reset legacy counters once

**Files:**
- Modify: `raidbot/desktop/models.py`
- Modify: `raidbot/desktop/storage.py`
- Test: `tests/desktop/test_storage.py`

- [ ] **Step 1: Write the failing storage test**

Add a test in `tests/desktop/test_storage.py` that loads legacy state data with:

- `raids_completed > 0`
- `raids_failed > 0`
- dashboard reset offsets set
- no new migration marker

and expects after load:

- `raids_completed == 0`
- `raids_failed == 0`
- related success-rate/completed/failed offsets reset to `0`
- new migration marker set to complete

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest -q tests\desktop\test_storage.py -k per_profile_counter`

Expected: FAIL because the migration marker/reset behavior does not exist yet.

- [ ] **Step 3: Add the migration marker**

Update `raidbot/desktop/models.py` to extend the persisted dashboard/state migration flags with a new boolean indicating the per-profile counter migration has completed.

- [ ] **Step 4: Implement the one-time reset in storage**

Update `raidbot/desktop/storage.py` load path to:

- detect legacy state without the new migration marker
- reset:
  - `raids_completed`
  - `raids_failed`
  - `raids_completed_offset`
  - `raids_failed_offset`
  - `success_rate_completed_offset`
  - `success_rate_failed_offset`
- set the migration marker

- [ ] **Step 5: Run the storage test to verify it passes**

Run: `python -m pytest -q tests\desktop\test_storage.py -k per_profile_counter`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add raidbot/desktop/models.py raidbot/desktop/storage.py tests/desktop/test_storage.py
git commit -m "feat: migrate dashboard counters to per-profile baseline"
```

### Task 2: Switch runtime counting to per-profile outcomes

**Files:**
- Modify: `raidbot/desktop/worker.py`
- Test: `tests/desktop/test_worker.py`

- [ ] **Step 1: Write the failing worker tests**

Add focused tests in `tests/desktop/test_worker.py` for:

- one failed profile in a multi-profile raid increments `raids_failed`
- `_record_whole_raid_completed()` no longer increments `raids_completed`
- `_record_whole_raid_failed()` no longer increments `raids_failed`

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest -q tests\desktop\test_worker.py -k per_profile_counter`

Expected: FAIL because whole-raid helpers still mutate counters and profile failure handling does not yet fully own failed counts.

- [ ] **Step 3: Update worker accounting**

Modify `raidbot/desktop/worker.py` so:

- individual profile failure paths increment `raids_failed`
- individual profile success paths continue to increment `raids_completed`
- `_record_whole_raid_completed()` no longer changes completed counters
- `_record_whole_raid_failed()` no longer changes failed counters

- [ ] **Step 4: Run worker tests to verify they pass**

Run: `python -m pytest -q tests\desktop\test_worker.py -k per_profile_counter`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/desktop/worker.py tests/desktop/test_worker.py
git commit -m "feat: count dashboard raid outcomes per profile"
```

### Task 3: Verify dashboard cards render the new semantics

**Files:**
- Modify: `tests/desktop/test_main_window.py`
- Modify: `raidbot/desktop/main_window.py` only if needed

- [ ] **Step 1: Write or update the failing dashboard test**

Add/update a main-window test so a state with:

- `raids_completed = 3`
- `raids_failed = 1`

renders:

- `Raids Completed = 3`
- `Raids Failed = 1`
- `Success Rate = 75.0%`

using the post-migration per-profile meaning.

- [ ] **Step 2: Run the dashboard test**

Run: `python -m pytest -q tests\desktop\test_main_window.py -k per_profile_counter`

Expected: FAIL only if current expectations still assume whole-raid semantics.

- [ ] **Step 3: Adjust UI expectation wiring if needed**

If the dashboard test fails because of stale expectations rather than code, update only the relevant test fixtures/assertions. Do not change `main_window.py` unless the UI path itself still assumes whole-raid math.

- [ ] **Step 4: Run the dashboard test to verify it passes**

Run: `python -m pytest -q tests\desktop\test_main_window.py -k per_profile_counter`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/desktop/test_main_window.py raidbot/desktop/main_window.py
git commit -m "test: align dashboard cards with per-profile counters"
```

### Task 4: Run focused regression verification

**Files:**
- Modify: none unless regressions are found

- [ ] **Step 1: Run focused regression suite**

Run:

```bash
python -m pytest -q tests\desktop\test_storage.py tests\desktop\test_worker.py tests\desktop\test_main_window.py -k "per_profile_counter or success_rate or dashboard_metric or successful_profile_runs"
```

Expected: PASS

- [ ] **Step 2: If a regression appears, fix the minimal affected file**

Only touch files directly implicated by the failure. Re-run the same command after the fix.

- [ ] **Step 3: Commit final verification-ready state**

```bash
git add raidbot/desktop/models.py raidbot/desktop/storage.py raidbot/desktop/worker.py tests/desktop/test_storage.py tests/desktop/test_worker.py tests/desktop/test_main_window.py
git commit -m "fix: align dashboard counters with per-profile raid outcomes"
```
