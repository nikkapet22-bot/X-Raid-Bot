# Headless Playwright Side Project Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a separate Playwright-based headless proof-of-concept app in this repo that reuses the current bot’s Telegram/filtering config while owning its own X auth/runtime and small UI.

**Architecture:** Add a new `raidbot/headless` package with a small PySide6 app, shared-config loader, Playwright session manager, Telegram intake adapter, one-raid-at-a-time runner, and DOM-based X action layer. Keep the current desktop bot untouched.

**Tech Stack:** Python, PySide6, Playwright, existing Telegram/parser/config modules, pytest

---

## File Map

- Create: `raidbot/headless/__init__.py`
- Create: `raidbot/headless/app.py`
- Create: `raidbot/headless/window.py`
- Create: `raidbot/headless/config.py`
- Create: `raidbot/headless/models.py`
- Create: `raidbot/headless/session.py`
- Create: `raidbot/headless/listener.py`
- Create: `raidbot/headless/runner.py`
- Create: `raidbot/headless/actions.py`
- Create: `tests/headless/test_config.py`
- Create: `tests/headless/test_session.py`
- Create: `tests/headless/test_runner.py`
- Create: `tests/headless/test_window.py`
- Modify: `pyproject.toml`
  - add Playwright dependency and optional entrypoint if needed

### Task 1: Establish headless models and config loading

**Files:**
- Create: `raidbot/headless/models.py`
- Create: `raidbot/headless/config.py`
- Test: `tests/headless/test_config.py`

- [ ] **Step 1: Write failing config tests**

Add tests covering:

- loading shared Telegram/filtering config from the existing desktop config source
- loading/saving headless-only settings
- default headless action toggles and auth-state placeholders

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest -q tests\headless\test_config.py`

Expected: FAIL because the package/files do not exist yet.

- [ ] **Step 3: Implement minimal headless models**

Create `raidbot/headless/models.py` with small dataclasses for:

- headless settings
- auth status
- last result/log summary

- [ ] **Step 4: Implement config loading**

Create `raidbot/headless/config.py` to:

- read shared desktop config
- load/save a separate headless config/state file

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest -q tests\headless\test_config.py`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add raidbot/headless/models.py raidbot/headless/config.py tests/headless/test_config.py
git commit -m "feat: add headless config and models"
```

### Task 2: Add Playwright session bootstrap and auth validation

**Files:**
- Create: `raidbot/headless/session.py`
- Test: `tests/headless/test_session.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Write failing session tests**

Add tests for:

- bootstrap login flow entering headed bootstrap mode
- auth-state validation returning authenticated vs needs-login
- persistent context path ownership staying inside the headless project

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest -q tests\headless\test_session.py`

Expected: FAIL because session module does not exist yet.

- [ ] **Step 3: Add Playwright dependency**

Update `pyproject.toml` with the Playwright dependency needed for the side project.

- [ ] **Step 4: Implement session manager**

Create `raidbot/headless/session.py` with:

- Playwright persistent context bootstrap entry
- auth validation method
- simple lifecycle helpers

Use abstraction seams so tests can mock Playwright rather than launching a real browser.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest -q tests\headless\test_session.py`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml raidbot/headless/session.py tests/headless/test_session.py
git commit -m "feat: add headless Playwright session bootstrap"
```

### Task 3: Add one-raid-at-a-time runner and action orchestration seam

**Files:**
- Create: `raidbot/headless/actions.py`
- Create: `raidbot/headless/runner.py`
- Test: `tests/headless/test_runner.py`

- [ ] **Step 1: Write failing runner tests**

Add tests covering:

- one-raid-at-a-time execution
- enabled actions executing in order
- structured failure when auth/session unavailable
- structured failure when a DOM action cannot be completed

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest -q tests\headless\test_runner.py`

Expected: FAIL because runner/actions do not exist yet.

- [ ] **Step 3: Implement action interface**

Create `raidbot/headless/actions.py` with a locator-first action layer interface for:

- reply
- like
- repost
- bookmark

For this task, keep the implementation minimal and test-oriented; detailed selectors can evolve later.

- [ ] **Step 4: Implement runner**

Create `raidbot/headless/runner.py` with:

- one-raid-at-a-time queue/guard
- session handoff
- enabled-action filtering
- structured result objects

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest -q tests\headless\test_runner.py`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add raidbot/headless/actions.py raidbot/headless/runner.py tests/headless/test_runner.py
git commit -m "feat: add headless raid runner"
```

### Task 4: Add small PySide6 proof-of-concept UI

**Files:**
- Create: `raidbot/headless/window.py`
- Create: `raidbot/headless/app.py`
- Test: `tests/headless/test_window.py`

- [ ] **Step 1: Write failing UI tests**

Add tests covering:

- window exposes `Bootstrap Login`, `Start`, `Stop`
- action toggles exist for `Reply`, `Like`, `Repost`, `Bookmark`
- auth status and log area render initial state

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest -q tests\headless\test_window.py`

Expected: FAIL because the UI files do not exist yet.

- [ ] **Step 3: Implement minimal window**

Create `raidbot/headless/window.py` with:

- bootstrap button
- start/stop buttons
- action toggles
- auth status label
- last result/log area

- [ ] **Step 4: Implement app entry**

Create `raidbot/headless/app.py` as the small app entry point that wires the window and headless config/session objects.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest -q tests\headless\test_window.py`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add raidbot/headless/app.py raidbot/headless/window.py tests/headless/test_window.py
git commit -m "feat: add headless proof-of-concept UI"
```

### Task 5: Add Telegram intake adapter and focused integration slice

**Files:**
- Create: `raidbot/headless/listener.py`
- Modify: `tests/headless/test_runner.py` or add focused intake tests

- [ ] **Step 1: Write failing intake integration test**

Add a focused test that proves:

- shared config is read
- Telegram-side detection result is adapted into one headless raid job
- non-matching messages are ignored

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest -q tests\headless -k listener`

Expected: FAIL because the intake adapter does not exist yet.

- [ ] **Step 3: Implement listener adapter**

Create `raidbot/headless/listener.py` that:

- reuses shared Telegram config/session
- uses current parser/filtering path or adapts it
- emits normalized headless raid jobs into the runner

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest -q tests\headless -k listener`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/headless/listener.py tests/headless
git commit -m "feat: add headless Telegram intake adapter"
```

### Task 6: Run focused proof-of-concept verification

**Files:**
- Modify: only if regressions are found

- [ ] **Step 1: Run the headless test slice**

Run:

```bash
python -m pytest -q tests\headless
```

Expected: PASS

- [ ] **Step 2: Run a shared-config regression slice**

Run:

```bash
python -m pytest -q tests\test_parser.py tests\test_service.py tests\desktop\test_storage.py -k "config or parse or sender or raid"
```

Expected: PASS

- [ ] **Step 3: Commit final proof-of-concept baseline**

```bash
git add raidbot/headless pyproject.toml tests/headless
git commit -m "feat: add headless Playwright proof of concept"
```
