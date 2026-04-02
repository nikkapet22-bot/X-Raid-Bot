# Headless Playwright Live Proof Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the headless Playwright side project into a live headed proof with real Telegram intake, real Like/Repost/Bookmark execution on X, and a responsive PySide6 status UI.

**Architecture:** Keep the existing `raidbot/headless` package and extend it with a background runtime controller, real listener lifecycle, real locator-based actions, and UI signal/log wiring. Explicitly skip reply-required raids as `unsupported_for_now`.

**Tech Stack:** Python, PySide6, Playwright, Telethon integration via existing listener/service path, pytest

---

## File Map

- Create: `raidbot/headless/runtime.py`
- Modify: `raidbot/headless/listener.py`
- Modify: `raidbot/headless/runner.py`
- Modify: `raidbot/headless/actions.py`
- Modify: `raidbot/headless/window.py`
- Modify: `raidbot/headless/app.py`
- Create: `tests/headless/test_runtime.py`
- Modify: `tests/headless/test_runner.py`
- Modify: `tests/headless/test_window.py`
- Modify: `tests/headless/test_listener.py`

### Task 1: Add runtime controller and start/stop lifecycle

**Files:**
- Create: `raidbot/headless/runtime.py`
- Test: `tests/headless/test_runtime.py`

- [ ] **Step 1: Write failing runtime tests**

Add tests for:

- runtime enters running state on start
- runtime exits running state on stop
- runtime emits log/status updates to the UI-facing callback layer

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest -q tests\headless\test_runtime.py`

Expected: FAIL because the runtime controller does not exist yet.

- [ ] **Step 3: Implement minimal runtime controller**

Create `raidbot/headless/runtime.py` with:

- background runtime object
- start/stop methods
- log/status callback hooks
- queue ownership

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest -q tests\headless\test_runtime.py`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/headless/runtime.py tests/headless/test_runtime.py
git commit -m "feat: add headless runtime controller"
```

### Task 2: Enforce unsupported reply-required raids and real runner semantics

**Files:**
- Modify: `raidbot/headless/runner.py`
- Modify: `tests/headless/test_runner.py`

- [ ] **Step 1: Write failing runner tests**

Add/update tests proving:

- reply-required raid returns `unsupported_for_now`
- supported raids still execute
- no partial execution occurs for reply-required jobs

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest -q tests\headless\test_runner.py -k unsupported_for_now`

Expected: FAIL because that skip logic does not exist yet.

- [ ] **Step 3: Implement skip logic in runner**

Update `raidbot/headless/runner.py` so:

- if a raid requires reply, return `unsupported_for_now`
- otherwise continue with supported actions

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest -q tests\headless\test_runner.py`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/headless/runner.py tests/headless/test_runner.py
git commit -m "feat: skip reply-required raids in headless proof"
```

### Task 3: Replace stub actions with real Playwright locator flows

**Files:**
- Modify: `raidbot/headless/actions.py`
- Modify: `tests/headless/test_runner.py`

- [ ] **Step 1: Write failing action-flow tests**

Add mocked-page tests proving:

- like flow uses the expected locator/click sequence
- repost flow opens menu and chooses repost
- bookmark flow clicks the bookmark locator

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest -q tests\headless\test_runner.py -k \"like or repost or bookmark\"`

Expected: FAIL because the action layer is still too minimal or does not verify the intended calls.

- [ ] **Step 3: Implement real locator-based action flows**

Update `raidbot/headless/actions.py` to use explicit Playwright locator calls for:

- Like
- Repost
- Bookmark

Keep this slice headed-first and locator-only.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest -q tests\headless\test_runner.py`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/headless/actions.py tests/headless/test_runner.py
git commit -m "feat: add live Playwright action flows"
```

### Task 4: Wire live Telegram intake into the runtime

**Files:**
- Modify: `raidbot/headless/listener.py`
- Modify: `tests/headless/test_listener.py`
- Modify: `tests/headless/test_runtime.py`

- [ ] **Step 1: Write failing listener/runtime integration tests**

Add tests proving:

- the listener can be built from shared config
- a detected job is handed to the runtime queue
- a rejected/non-matching message is logged or ignored without queueing

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest -q tests\headless\test_listener.py tests\headless\test_runtime.py -k listener`

Expected: FAIL because runtime/listener handoff is not wired yet.

- [ ] **Step 3: Implement live listener/runtime handoff**

Update `raidbot/headless/listener.py` and `raidbot/headless/runtime.py` so:

- runtime can start the real Telegram listener
- detected jobs enqueue for execution
- stop cleanly tears listener down

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest -q tests\headless\test_listener.py tests\headless\test_runtime.py`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/headless/listener.py raidbot/headless/runtime.py tests/headless/test_listener.py tests/headless/test_runtime.py
git commit -m "feat: wire headless runtime to live Telegram intake"
```

### Task 5: Wire UI buttons and status/log updates to the runtime

**Files:**
- Modify: `raidbot/headless/window.py`
- Modify: `raidbot/headless/app.py`
- Modify: `tests/headless/test_window.py`

- [ ] **Step 1: Write failing UI wiring tests**

Add/update tests for:

- `Start` triggers runtime start path
- `Stop` triggers runtime stop path
- runtime status/log updates reach the visible labels/log area

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest -q tests\headless\test_window.py -k \"start or stop or log\"`

Expected: FAIL because the UI is not yet runtime-driven.

- [ ] **Step 3: Implement UI/runtime wiring**

Update `raidbot/headless/app.py` and `raidbot/headless/window.py` so:

- buttons control the runtime
- auth/running/log/result updates flow back into the UI

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest -q tests\headless\test_window.py`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/headless/app.py raidbot/headless/window.py tests/headless/test_window.py
git commit -m "feat: connect headless UI to runtime"
```

### Task 6: Run focused live-proof verification

**Files:**
- Modify: only if regressions are found

- [ ] **Step 1: Run full headless test slice**

Run:

```bash
python -m pytest -q tests\headless
```

Expected: PASS

- [ ] **Step 2: Run shared parser/service regression slice**

Run:

```bash
python -m pytest -q tests\test_parser.py tests\test_service.py tests\desktop\test_storage.py -k "config or parse or sender or raid"
```

Expected: PASS

- [ ] **Step 3: Commit final live-proof baseline**

```bash
git add raidbot/headless tests/headless
git commit -m "feat: add live headed proof for headless raid runtime"
```
