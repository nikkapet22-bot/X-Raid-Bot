# Close Confirmation Foreground Design

## Goal

When the app is minimized from the taskbar and the user closes it from the taskbar while the bot is still running, the close confirmation popup must come to the foreground immediately.

## Current Problem

- `MainWindow.closeEvent()` calls `confirm_close()` when shutdown must wait.
- If the main window is hidden or minimized, `_confirm_close()` currently falls back to `_show_centered_close_confirmation()`.
- That fallback builds a detached `QMessageBox(None)`.
- Because the main window is still minimized/hidden, the dialog can appear without restoring the app to the foreground, so the user does not see it until they manually restore the window.

## Chosen Approach

Restore and foreground the main window before showing the hidden-window confirmation dialog.

This is preferred over trying to force a detached message box topmost, because it matches normal Windows behavior and reuses the existing restore path already used for tray restore.

## Behavior

- If the app is visible when close is requested:
  - keep the current `QMessageBox.question(self, ...)` path unchanged.
- If the app is hidden or minimized when close is requested:
  - restore the main window into a visible normal state
  - raise and activate it
  - then show the close confirmation dialog

## Implementation Shape

### `raidbot/desktop/main_window.py`

- Add a small helper that ensures the main window is visible and foregrounded for close confirmation.
- Use it from the hidden-window branch in `_confirm_close()`.
- Parent the fallback confirmation dialog to the main window instead of using `QMessageBox(None)`.

### `tests/desktop/test_main_window.py`

- Update the hidden-window close confirmation test to assert the dialog path restores/foregrounds the window before prompting.
- Keep the visible-window confirmation behavior unchanged.

## Non-Goals

- No change to tray restore behavior.
- No change to normal visible close confirmation behavior.
- No new settings or user-facing controls.
