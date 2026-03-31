# Focus Opened Window Before Page Ready Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure every newly opened raid window is actually focused before page-ready matching begins, and fail early with `window_not_focusable` if focus cannot be acquired.

**Architecture:** Keep the change narrow and local to the worker’s new-window normalization path. After opening and detecting the new Chrome window, maximize it, then reuse `WindowManager.ensure_interactable_window(...)` to force focus before continuing into the page-ready probe.

**Tech Stack:** Python, existing desktop worker/window-manager runtime, pytest

---

## File Map

- Modify: `raidbot/desktop/worker.py`
  - Require a successful focus step after maximize and before page-ready waiting
- Test: `tests/desktop/test_worker.py`
  - Add focused coverage for maximize → focus → page-ready order and early failure on focus refusal

### Task 1: Prove Focus Is Required Before Page Ready

**Files:**
- Modify: `tests/desktop/test_worker.py`

- [ ] **Step 1: Write the failing worker tests**

Add focused tests in `tests/desktop/test_worker.py` for:
- newly opened raid window is maximized and then focused before page-ready waiting starts
- page-ready wait is not called if focus fails
- focus failure returns `window_not_focusable`

Use the existing fake window manager/runtime helpers so the assertions prove the order, not just the final outcome.

- [ ] **Step 2: Run the focused worker tests to verify they fail**

Run:

```bash
python -m pytest -q tests\desktop\test_worker.py -k "page_ready and focus"
```

Expected: FAIL because the worker currently maximizes and then goes straight into page-ready waiting

- [ ] **Step 3: Commit test scaffolding if useful**

```bash
git add tests/desktop/test_worker.py
git commit -m "test: cover focus before page ready"
```

### Task 2: Enforce Focus Before Page Ready In Worker

**Files:**
- Modify: `raidbot/desktop/worker.py`
- Test: `tests/desktop/test_worker.py`

- [ ] **Step 1: Implement the minimal worker change**

In `raidbot/desktop/worker.py`:
- after the opened window is found and maximized
- call `window_manager.ensure_interactable_window(opened_window)` when available
- if it fails, return `window_not_focusable`
- if it succeeds, carry forward the returned normalized window into the page-ready path

Do not change slot-test behavior or page-ready matching semantics beyond this new precondition.

- [ ] **Step 2: Run the focused worker tests to verify they pass**

Run:

```bash
python -m pytest -q tests\desktop\test_worker.py -k "page_ready and focus"
```

Expected: PASS

- [ ] **Step 3: Run the broader page-ready worker slice**

Run:

```bash
python -m pytest -q tests\desktop\test_worker.py -k "page_ready or target_window_not_found or waits_for_page_ready_before_running_sequence"
```

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add raidbot/desktop/worker.py tests/desktop/test_worker.py
git commit -m "fix: focus opened raid window before page ready"
```

### Task 3: Final Verification

**Files:**
- Verify: `tests/desktop/test_worker.py`

- [ ] **Step 1: Run the focused verification slice**

Run:

```bash
python -m pytest -q tests\desktop\test_worker.py -k "page_ready or focus or target_window_not_found"
```

Expected: PASS

- [ ] **Step 2: Commit final polish if needed**

```bash
git add raidbot/desktop/worker.py tests/desktop/test_worker.py
git commit -m "fix: normalize focus before page ready"
```
