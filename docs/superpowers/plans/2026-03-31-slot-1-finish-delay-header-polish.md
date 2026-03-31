# Slot 1 Finish Delay Header Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Polish the slot 1 `Finish Delay` control so it looks like a clean inline header control instead of a dark detached block, while keeping the timing logic unchanged.

**Architecture:** Keep the existing slot-1-only field and persistence path intact. Limit changes to Bot Actions header layout/styling plus focused UI tests, so the feature behavior stays stable while the header visuals become transparent, compact, and legible.

**Tech Stack:** Python, PySide6, existing desktop theme stylesheet, pytest/pytest-qt

---

## File Map

- Modify: `raidbot/desktop/bot_actions/page.py`
  - tighten slot 1 header control layout without changing behavior
- Modify: `raidbot/desktop/theme.py`
  - add narrow styling for the slot 1 finish-delay label/input
- Test: `tests/desktop/bot_actions/test_page.py`
  - verify the slot 1 finish-delay field remains present and cleanly structured

### Task 1: Pin The Header Behavior In Tests

**Files:**
- Modify: `tests/desktop/bot_actions/test_page.py`

- [ ] **Step 1: Write the failing UI tests**

Add focused tests for:
- slot 1 finish-delay container staying transparent/no custom dark card wrapper
- slot 1 finish-delay input remaining a small visible field
- slot 1 finish-delay label and input remaining aligned in the header

- [ ] **Step 2: Run the focused page tests to verify they fail**

Run: `python -m pytest -q tests\desktop\bot_actions\test_page.py -k "finish_delay"`
Expected: FAIL because the current slot 1 finish-delay header still uses the ugly dark block treatment

- [ ] **Step 3: Commit**

```bash
git add tests/desktop/bot_actions/test_page.py
git commit -m "test: pin slot 1 finish delay header polish"
```

### Task 2: Polish The Slot 1 Header Control

**Files:**
- Modify: `raidbot/desktop/bot_actions/page.py`
- Modify: `raidbot/desktop/theme.py`

- [ ] **Step 1: Implement the minimal UI cleanup**

In `raidbot/desktop/bot_actions/page.py`:
- keep the existing slot 1 header position
- ensure the finish-delay container is just an inline widget, not a card-like block
- slightly widen the numeric field so values remain legible

In `raidbot/desktop/theme.py`:
- add a narrow selector for the slot 1 finish-delay input
- keep the container transparent
- make the input a small outlined field with centered readable text

- [ ] **Step 2: Run the focused page tests to verify they pass**

Run: `python -m pytest -q tests\desktop\bot_actions\test_page.py -k "finish_delay"`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add raidbot/desktop/bot_actions/page.py raidbot/desktop/theme.py tests/desktop/bot_actions/test_page.py
git commit -m "feat: polish slot 1 finish delay header"
```

### Task 3: Final Verification

**Files:**
- Verify: `tests/desktop/bot_actions/test_page.py`
- Verify: `tests/desktop/test_main_window.py`

- [ ] **Step 1: Run the focused Bot Actions verification**

Run: `python -m pytest -q tests\desktop\bot_actions\test_page.py`
Expected: PASS

- [ ] **Step 2: Run the related main window smoke slice**

Run: `python -m pytest -q tests\desktop\test_main_window.py -k "bot_actions or config"`
Expected: PASS or no relevant failures

- [ ] **Step 3: Commit final polish if needed**

```bash
git add raidbot/desktop/bot_actions/page.py raidbot/desktop/theme.py tests/desktop/bot_actions/test_page.py
git commit -m "feat: finalize slot 1 finish delay header polish"
```
