# CLDF Troubleshoot Section Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the first `Troubleshoot` UI section to the Bot Actions page with a `CLDF` group that renders 3 troubleshoot cards (`1`, `2`, `3`) with preview, `Capture`, and `Test`.

**Architecture:** Extend the existing `BotActionsPage` in place so the new troubleshoot surface follows the current page’s structure, styling, and signal model. Keep this first slice UI-only: render the cards, expose capture/test signals, and add focused page tests without introducing worker/runtime troubleshooting logic yet.

**Tech Stack:** PySide6 widgets, existing Bot Actions preview helpers, pytest/qtbot UI tests

---

### Task 1: Add failing UI tests for the Troubleshoot CLDF section

**Files:**
- Modify: `tests/desktop/bot_actions/test_page.py`
- Reference: `raidbot/desktop/bot_actions/page.py`

- [ ] **Step 1: Add a failing test that the Troubleshoot section renders**

Add a focused page test that creates `BotActionsPage` and asserts:
- a `QGroupBox` titled `Troubleshoot` exists
- a subgroup titled `CLDF` exists inside it

- [ ] **Step 2: Add a failing test that CLDF renders 3 troubleshoot cards**

Assert the page exposes 3 troubleshoot cards in order:
- label `1`
- label `2`
- label `3`

Each card should exist as a full mini preview block, not just a bare button row.

- [ ] **Step 3: Add a failing test that each CLDF card has preview, Capture, and Test only**

For each troubleshoot card, assert:
- preview label exists
- `Capture` button exists
- `Test` button exists
- no enable toggle exists
- no presets button exists
- no finish-delay control exists

- [ ] **Step 4: Add failing signal tests for troubleshoot capture/test**

Add tests proving:
- clicking troubleshoot card `Capture` emits `troubleshootCaptureRequested("cldf", index)`
- clicking troubleshoot card `Test` emits `troubleshootTestRequested("cldf", index)`

- [ ] **Step 5: Run the focused page tests to verify failure**

Run: `python -m pytest -q tests\desktop\bot_actions\test_page.py -k "troubleshoot or cldf"`

Expected:
- FAIL because the page does not yet render the new section or emit those signals

- [ ] **Step 6: Commit the failing tests**

```bash
git add tests/desktop/bot_actions/test_page.py
git commit -m "test: cover CLDF troubleshoot section"
```

### Task 2: Implement the Troubleshoot -> CLDF section in BotActionsPage

**Files:**
- Modify: `raidbot/desktop/bot_actions/page.py`
- Test: `tests/desktop/bot_actions/test_page.py`

- [ ] **Step 1: Add troubleshoot page-level signals**

Add two new `BotActionsPage` signals:
- `troubleshootCaptureRequested = Signal(str, int)`
- `troubleshootTestRequested = Signal(str, int)`

Use group key:
- `cldf`

- [ ] **Step 2: Add a small troubleshoot card widget in page.py**

Create a focused card widget in `page.py` for troubleshoot items that mirrors the current slot-card visual language but only includes:
- title label
- preview label
- `Capture` button
- `Test` button
- muted template status label

Do not include:
- toggle
- presets
- finish-delay input

- [ ] **Step 3: Reuse the existing preview-loading helper**

Use the existing `_set_preview_label(...)` helper for troubleshoot previews so:
- same-path overwrites refresh correctly
- empty state stays consistent with Bot Actions

- [ ] **Step 4: Build the Troubleshoot section in `_build_layout()`**

Add:
- `QGroupBox("Troubleshoot")`
- inside it, a `QGroupBox("CLDF")`
- inside `CLDF`, a horizontal row of 3 troubleshoot cards

Card labels should be:
- `1`
- `2`
- `3`

- [ ] **Step 5: Store troubleshoot cards on the page for later sync**

Expose a stable structure on the page such as:
- `self.troubleshoot_groups["cldf"]`
- or `self.cldf_boxes`

This should make future sync/runtime wiring straightforward.

- [ ] **Step 6: Wire capture/test buttons to the new signals**

For each CLDF card index:
- `Capture` emits `("cldf", index)`
- `Test` emits `("cldf", index)`

Also update page status text the same way Bot Actions currently does for capture/test initiation.

- [ ] **Step 7: Run the focused tests to verify they now pass**

Run: `python -m pytest -q tests\desktop\bot_actions\test_page.py -k "troubleshoot or cldf"`

Expected:
- PASS

- [ ] **Step 8: Commit the UI implementation**

```bash
git add raidbot/desktop/bot_actions/page.py tests/desktop/bot_actions/test_page.py
git commit -m "feat: add CLDF troubleshoot section"
```

### Task 3: Run the broader Bot Actions regression slice

**Files:**
- Verify: `raidbot/desktop/bot_actions/page.py`
- Verify: `tests/desktop/bot_actions/test_page.py`
- Verify: `tests/desktop/test_main_window.py`

- [ ] **Step 1: Run the full Bot Actions page test file**

Run: `python -m pytest -q tests\desktop\bot_actions\test_page.py`

Expected:
- PASS

- [ ] **Step 2: Run the Bot Actions main-window integration slice**

Run: `python -m pytest -q tests\desktop\test_main_window.py -k "bot_actions or config"`

Expected:
- PASS

- [ ] **Step 3: Review the final diff for scope**

Confirm the change is still limited to:
- Bot Actions page UI
- focused tests

No worker/controller troubleshooting runtime should be included in this slice.

- [ ] **Step 4: Commit the verification pass**

```bash
git add raidbot/desktop/bot_actions/page.py tests/desktop/bot_actions/test_page.py
git commit -m "test: verify CLDF troubleshoot UI slice"
```
