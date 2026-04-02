# Headless Auth Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the headless Playwright login bootstrap with a one-time auth import from the desktop bot's configured Chrome raid profile.

**Architecture:** Reuse the desktop bot's Chrome profile discovery to locate the configured raid profile, run a one-time import bridge against that profile while Chrome is closed, export a headless-owned auth artifact, and keep normal headless runtime isolated from the live profile.

**Tech Stack:** Python, Playwright, PySide6, pytest

---

## File Map

- Modify: `raidbot/headless/config.py`
- Modify: `raidbot/headless/session.py`
- Modify: `raidbot/headless/app.py`
- Modify: `raidbot/headless/window.py`
- Modify: `tests/headless/test_config.py`
- Modify: `tests/headless/test_session.py`
- Modify: `tests/headless/test_app.py`

### Task 1: Add headless auth artifact/config plumbing

**Files:**
- Modify: `raidbot/headless/config.py`
- Modify: `tests/headless/test_config.py`

- [ ] **Step 1: Write failing config tests**

Add tests proving:

- the headless store exposes a stable auth-state artifact path
- that artifact lives in the headless data directory, not the desktop Chrome profile

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest -q tests\headless\test_config.py -k "auth_state"`

Expected: FAIL because no dedicated auth-state path exists yet.

- [ ] **Step 3: Implement the minimal config change**

Update `raidbot/headless/config.py` to expose the headless-owned auth-state artifact path.

- [ ] **Step 4: Run config tests to verify they pass**

Run: `python -m pytest -q tests\headless\test_config.py`

Expected: PASS

### Task 2: Add Chrome-profile auth import to the session manager

**Files:**
- Modify: `raidbot/headless/session.py`
- Modify: `tests/headless/test_session.py`

- [ ] **Step 1: Write failing session tests**

Add tests proving:

- auth import resolves the desktop bot's configured raid profile
- import requires Chrome/profile access and fails clearly when unavailable
- successful import writes a headless-owned auth artifact
- runtime auth checks can use that imported artifact without touching the live desktop profile

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest -q tests\headless\test_session.py -k "import_auth or auth_artifact"`

Expected: FAIL because the import path does not exist yet.

- [ ] **Step 3: Implement the minimal session import flow**

Update `raidbot/headless/session.py` to:

- detect the desktop Chrome environment/profile using the existing desktop helper
- add an `import_auth_from_desktop_profile(...)` path
- export a headless-owned auth artifact
- keep runtime on headless-owned auth only

- [ ] **Step 4: Run session tests to verify they pass**

Run: `python -m pytest -q tests\headless\test_session.py`

Expected: PASS

### Task 3: Replace bootstrap login with Import X Auth in the app/UI

**Files:**
- Modify: `raidbot/headless/window.py`
- Modify: `raidbot/headless/app.py`
- Modify: `tests/headless/test_app.py`

- [ ] **Step 1: Write failing UI/app tests**

Add tests proving:

- button text is now `Import X Auth`
- import success updates auth state/logs
- import failure logs a clear error and preserves the previous headless auth artifact

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest -q tests\headless\test_app.py -k "import_x_auth or bootstrap"`

Expected: FAIL because the app still uses the old bootstrap login flow.

- [ ] **Step 3: Implement the minimal app/UI change**

Update:

- `raidbot/headless/window.py` to rename the button
- `raidbot/headless/app.py` to call the new import path instead of direct Playwright login

- [ ] **Step 4: Run app tests to verify they pass**

Run: `python -m pytest -q tests\headless\test_app.py`

Expected: PASS

### Task 4: Run full headless verification

**Files:**
- Modify: only if regressions are found

- [ ] **Step 1: Run the full headless slice**

Run: `python -m pytest -q tests\headless`

Expected: PASS

- [ ] **Step 2: Commit**

```bash
git add raidbot/headless tests/headless
git commit -m "feat: import headless X auth from desktop Chrome profile"
```
