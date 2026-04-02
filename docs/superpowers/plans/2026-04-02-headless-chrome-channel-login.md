# Headless Chrome Channel Login Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Switch the headless Playwright proof from bundled Chromium to branded Chrome channel for both bootstrap login and runtime sessions.

**Architecture:** Keep the existing `PlaywrightSessionManager` and persistent-profile model, but thread `channel="chrome"` into persistent context launch so headed bootstrap and headless runtime use the same browser family. Preserve the current cleanup and bootstrap error-reporting behavior.

**Tech Stack:** Python, Playwright, pytest

---

## File Map

- Modify: `raidbot/headless/session.py`
- Modify: `tests/headless/test_session.py`
- Modify: `tests/headless/test_app.py`

### Task 1: Launch persistent contexts through Chrome channel

**Files:**
- Modify: `tests/headless/test_session.py`
- Modify: `raidbot/headless/session.py`
- Modify: `tests/headless/test_app.py`

- [ ] **Step 1: Extend the failing session tests**

Update `tests/headless/test_session.py` so the fake Chromium launcher captures `channel`, then assert:

- bootstrap launch passes `headless=False` and `channel="chrome"`
- runtime launch passes `headless=True` and `channel="chrome"`
- Playwright manager cleanup still occurs on session close

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest -q tests\headless\test_session.py -k "chrome_channel or releases_playwright_manager"`

Expected: FAIL because `session.py` does not pass a browser channel yet.

- [ ] **Step 3: Implement the minimal session change**

Update `raidbot/headless/session.py` to:

- add a configurable browser channel with default `"chrome"`
- pass `channel=self._browser_channel` into `launch_persistent_context(...)`
- keep headed bootstrap vs headless runtime unchanged
- keep existing session cleanup behavior intact

- [ ] **Step 4: Run session tests to verify they pass**

Run: `python -m pytest -q tests\headless\test_session.py`

Expected: PASS

- [ ] **Step 5: Verify bootstrap error logging still works**

Run: `python -m pytest -q tests\headless\test_app.py -k "logs_bootstrap_failure"`

Expected: PASS

- [ ] **Step 6: Run the full headless regression slice**

Run: `python -m pytest -q tests\headless`

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add raidbot/headless/session.py tests/headless/test_session.py tests/headless/test_app.py
git commit -m "feat: use Chrome channel for headless Playwright sessions"
```
