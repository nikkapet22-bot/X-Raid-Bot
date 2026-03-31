# Immediate Capture Preview Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make all Bot Actions capture previews refresh immediately when a capture overwrites the same file path, and show slot 1's finish-image preview directly on the slot 1 card.

**Architecture:** Fix the root cause in the preview rendering layer by stopping path-based pixmap reloads and instead loading the latest image bytes from disk for every preview update. Keep the controller/capture flow unchanged, and extend slot 1's card UI to render both the main capture preview and the finish-image preview from config sync.

**Tech Stack:** Python, PySide6, existing desktop Bot Actions UI, pytest/pytest-qt

---

## File Map

- Modify: `raidbot/desktop/bot_actions/page.py`
  - Replace cached preview loading with fresh-from-disk image loading
  - Add slot 1 finish-image preview tile beside the main preview
- Modify: `raidbot/desktop/main_window.py`
  - Keep capture handlers narrow, but ensure the slot 1 finish capture path still reaches the updated card preview through normal sync
- Test: `tests/desktop/bot_actions/test_page.py`
  - Cover direct preview rendering behavior and slot 1 finish preview empty/rendered states
- Test: `tests/desktop/test_main_window.py`
  - Cover immediate same-path preview refresh for slot/page-ready/slot-1-finish capture flows

### Task 1: Prove Same-Path Preview Refresh Works At The Widget Layer

**Files:**
- Modify: `raidbot/desktop/bot_actions/page.py`
- Test: `tests/desktop/bot_actions/test_page.py`

- [ ] **Step 1: Write the failing page-level tests**

Add focused tests in `tests/desktop/bot_actions/test_page.py` for:
- reloading a preview after overwriting the same file path shows the new image content
- slot 1 shows a second finish-image preview tile
- slot 1 finish preview shows a neutral empty state when no finish image exists

- [ ] **Step 2: Run the focused page tests to verify they fail**

Run:

```bash
python -m pytest -q tests\desktop\bot_actions\test_page.py -k "preview or finish"
```

Expected: FAIL because preview loads still use cached path-based pixmaps and slot 1 has no finish preview tile yet

- [ ] **Step 3: Implement the minimal preview loader + slot 1 finish preview**

In `raidbot/desktop/bot_actions/page.py`:
- replace the current `QPixmap(str(path))` preview load path with a fresh image load that reads current bytes from disk every time
- keep stable file paths; do not rename capture files
- add a second preview label for slot 1 finish image only
- update `SlotBox.set_slot()` so slot 1 refreshes both:
  - `template_path`
  - `finish_template_path`

- [ ] **Step 4: Run the focused page tests to verify they pass**

Run:

```bash
python -m pytest -q tests\desktop\bot_actions\test_page.py -k "preview or finish"
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/desktop/bot_actions/page.py tests/desktop/bot_actions/test_page.py
git commit -m "fix: refresh bot action previews immediately"
```

### Task 2: Prove Main Window Capture Flows Refresh The Updated Previews Immediately

**Files:**
- Modify: `raidbot/desktop/main_window.py`
- Test: `tests/desktop/test_main_window.py`

- [ ] **Step 1: Write the failing main-window tests**

Add focused tests in `tests/desktop/test_main_window.py` for:
- capturing a slot image over the same path refreshes the visible slot thumbnail immediately
- capturing page-ready over the same path refreshes the page-ready preview immediately
- capturing slot 1 finish image updates the new on-card finish preview immediately

Use real temporary image files with distinct pixels/colors so the tests prove the preview content changed, not just the path text.

- [ ] **Step 2: Run the focused main-window tests to verify they fail**

Run:

```bash
python -m pytest -q tests\desktop\test_main_window.py -k "capture_updates or finish_preview"
```

Expected: FAIL because same-path overwrites still show stale preview content and slot 1 card does not yet mirror the finish image

- [ ] **Step 3: Implement the minimal main-window sync support**

In `raidbot/desktop/main_window.py`:
- keep the capture handlers narrow
- make only the minimal changes needed so the updated Bot Actions page refresh path is exercised immediately after:
  - slot capture
  - page-ready capture
  - slot 1 finish capture

Do not add new controller/storage behavior unless a test proves it is needed.

- [ ] **Step 4: Run the focused main-window tests to verify they pass**

Run:

```bash
python -m pytest -q tests\desktop\test_main_window.py -k "capture_updates or finish_preview"
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/desktop/main_window.py tests/desktop/test_main_window.py
git commit -m "fix: refresh capture previews on overwrite"
```

### Task 3: Final Verification

**Files:**
- Verify: `tests/desktop/bot_actions/test_page.py`
- Verify: `tests/desktop/test_main_window.py`

- [ ] **Step 1: Run the full focused verification slice**

Run:

```bash
python -m pytest -q tests\desktop\bot_actions\test_page.py tests\desktop\test_main_window.py -k "preview or capture or finish"
```

Expected: PASS

- [ ] **Step 2: Run the broader Bot Actions/UI smoke slice**

Run:

```bash
python -m pytest -q tests\desktop\bot_actions\test_page.py tests\desktop\test_main_window.py -k "bot_actions or config"
```

Expected: PASS or no relevant failures

- [ ] **Step 3: Commit final polish if needed**

```bash
git add raidbot/desktop/bot_actions/page.py raidbot/desktop/main_window.py tests/desktop/bot_actions/test_page.py tests/desktop/test_main_window.py
git commit -m "fix: show latest capture previews immediately"
```
