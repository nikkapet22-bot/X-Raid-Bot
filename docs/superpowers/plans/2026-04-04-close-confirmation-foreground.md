# Close Confirmation Foreground Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore and foreground the main window before showing the running-bot close confirmation when the app is minimized or hidden.

**Architecture:** Keep the visible-window confirmation path unchanged, but route the hidden/minimized fallback through a small restore-and-activate helper before showing the dialog. Parent the fallback dialog to the main window so the prompt follows the restored window instead of appearing detached.

**Tech Stack:** PySide6, pytest, existing desktop main-window tests

---

### Task 1: Restore Window Before Hidden Close Confirmation

**Files:**
- Modify: `raidbot/desktop/main_window.py`
- Test: `tests/desktop/test_main_window.py`

- [ ] **Step 1: Write/update the failing hidden-close test**

Update the hidden-close confirmation test in `tests/desktop/test_main_window.py` so it expects:
- the hidden/minimized fallback path to restore/foreground the window before prompting
- the fallback confirmation dialog to be parented to the main window instead of `None`

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `python -m pytest -q tests\desktop\test_main_window.py -k "hidden_window_close_confirmation_centers_dialog_on_screen or close_while_running_uses_default_confirmation_dialog"`

Expected: FAIL because the hidden fallback currently uses `QMessageBox(None)` without restoring the window first.

- [ ] **Step 3: Implement the minimal close-confirmation fix**

In `raidbot/desktop/main_window.py`:
- add a small helper that restores/shows the main window and brings it to the foreground for close confirmation
- call that helper from the hidden/minimized branch in `_confirm_close()`
- update `_show_centered_close_confirmation()` to parent the dialog to `self`
- keep the visible-window `QMessageBox.question(self, ...)` path unchanged

- [ ] **Step 4: Run the focused tests to verify they pass**

Run: `python -m pytest -q tests\desktop\test_main_window.py -k "hidden_window_close_confirmation_centers_dialog_on_screen or close_while_running_uses_default_confirmation_dialog"`

Expected: PASS

- [ ] **Step 5: Run a small broader close/minimize regression slice**

Run: `python -m pytest -q tests\desktop\test_main_window.py -k "close_while_running or hidden_window_close_confirmation or running_window_minimizes_to_tray_on_minimize or restore_from_tray"`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add raidbot/desktop/main_window.py tests/desktop/test_main_window.py
git commit -m "fix: foreground close confirmation from minimized window"
```
