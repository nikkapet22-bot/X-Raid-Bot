# Mock Dashboard Preview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a disposable preview launcher that opens the real desktop app with seeded fake dashboard data so the chart and metrics can be reviewed safely.

**Architecture:** Add one standalone script in `scripts/` that creates temporary app-data, seeds a fake `DesktopAppState`, and launches the real desktop UI against it. Keep the production app unchanged and remove the preview script after validation is complete.

**Tech Stack:** Python, existing desktop models/storage, temporary directories, subprocess/process launching

---

### Task 1: Add scenario seeding helpers

**Files:**
- Create: `scripts/mock_dashboard_preview.py`
- Test: `tests/desktop/test_mock_dashboard_preview.py`

- [ ] **Step 1: Write the failing tests for scenario generation**

Add tests that assert the script can build at least:
- `steady-4p`
- `burst-4p`
- `mixed-failures`

Expected checks:
- each scenario returns `DesktopAppState`
- each scenario includes seeded `successful_profile_runs`
- each scenario includes seeded `activity`

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest -q tests\desktop\test_mock_dashboard_preview.py -k "scenario"`
Expected: FAIL because the script/module does not exist yet

- [ ] **Step 3: Implement minimal scenario builders**

In `scripts/mock_dashboard_preview.py`, add:
- scenario registry
- helper for local timestamps
- seeded `DesktopAppState` builders

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest -q tests\desktop\test_mock_dashboard_preview.py -k "scenario"`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/mock_dashboard_preview.py tests/desktop/test_mock_dashboard_preview.py
git commit -m "feat: add mock dashboard preview scenarios"
```

### Task 2: Add temporary app-data seeding and launch wiring

**Files:**
- Modify: `scripts/mock_dashboard_preview.py`
- Test: `tests/desktop/test_mock_dashboard_preview.py`

- [ ] **Step 1: Write the failing tests for temp app-data seeding**

Add tests that assert:
- preview writes seeded config/state into a temp app-data folder
- preview does not target the real `%APPDATA%\RaidBot`
- preview resolves the real desktop entrypoint

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest -q tests\desktop\test_mock_dashboard_preview.py -k "appdata or launch"`
Expected: FAIL because seeding/launch helpers are incomplete

- [ ] **Step 3: Implement minimal temp app-data seeding and launch helpers**

Add code that:
- creates temp folders
- writes a minimal valid `DesktopAppConfig`
- writes the seeded `DesktopAppState`
- launches `raidbot.desktop.app` with env overrides

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest -q tests\desktop\test_mock_dashboard_preview.py -k "appdata or launch"`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/mock_dashboard_preview.py tests/desktop/test_mock_dashboard_preview.py
git commit -m "feat: wire mock dashboard preview launcher"
```

### Task 3: Add CLI and disposable usage flow

**Files:**
- Modify: `scripts/mock_dashboard_preview.py`
- Test: `tests/desktop/test_mock_dashboard_preview.py`

- [ ] **Step 1: Write the failing tests for CLI behavior**

Add tests that assert:
- `--scenario` is required or defaults cleanly
- invalid scenarios fail clearly
- usage/help text lists the supported scenarios

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest -q tests\desktop\test_mock_dashboard_preview.py -k "cli"`
Expected: FAIL because CLI behavior is incomplete

- [ ] **Step 3: Implement minimal CLI behavior**

Add:
- `argparse`
- supported scenario names
- clear launch message

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest -q tests\desktop\test_mock_dashboard_preview.py -k "cli"`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/mock_dashboard_preview.py tests/desktop/test_mock_dashboard_preview.py
git commit -m "feat: add mock dashboard preview cli"
```

### Task 4: Smoke-run the preview and then remove it after validation

**Files:**
- Modify: `scripts/mock_dashboard_preview.py` (only if smoke issues appear)
- Optionally delete later: `scripts/mock_dashboard_preview.py`
- Optionally delete later: `tests/desktop/test_mock_dashboard_preview.py`

- [ ] **Step 1: Run the preview for visual validation**

Run:
`python scripts\mock_dashboard_preview.py --scenario steady-4p`

Expected:
- real app window opens
- chart and metric cards show fake seeded data
- real `%APPDATA%\RaidBot` remains untouched

- [ ] **Step 2: Repeat for the burst scenario if needed**

Run:
`python scripts\mock_dashboard_preview.py --scenario burst-4p`

- [ ] **Step 3: After user approval, remove the disposable preview files**

Delete:
- `scripts/mock_dashboard_preview.py`
- `tests/desktop/test_mock_dashboard_preview.py`

- [ ] **Step 4: Run tests after cleanup**

Run:
`python -m pytest -q tests\desktop\test_storage.py tests\desktop\test_worker.py tests\desktop\test_main_window.py`

- [ ] **Step 5: Commit cleanup**

```bash
git add -A
git commit -m "chore: remove mock dashboard preview tooling"
```
