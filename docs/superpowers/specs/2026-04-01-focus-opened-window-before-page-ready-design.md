# Focus Opened Window Before Page Ready Design

## Goal

Make sure a newly opened raid window is actually focused before `Page Ready` matching begins.

## Current Problem

The runtime currently opens the raid window, detects it, and force-maximizes it before starting the `Page Ready` probe. Maximizing the window does not guarantee that Windows has given it foreground focus.

On some machines, the raid window can therefore:

- open successfully
- maximize successfully
- remain in the background

That creates a bad precondition for the rest of the raid flow, because the bot starts `Page Ready` and later slot interaction against a window that is not truly foreground/interactable yet.

## Decision

Normalize the opened raid window fully before `Page Ready` begins:

- open the raid window
- detect the newly opened Chrome window
- maximize it
- force focus using the existing `ensure_interactable_window(...)` path
- only then start `Page Ready`

If focus cannot be acquired, fail the profile immediately with `window_not_focusable`.

## Scope

In scope:

- real raid runtime
- replay-on-restart runtime if it uses the same new-window path
- failing early with `window_not_focusable` when focus cannot be acquired

Out of scope:

- slot `Test`
- user-managed Chrome windows outside the bot
- changing page-ready matching logic itself
- adding new settings or delays

## Implementation Notes

- Apply the focus check in `raidbot/desktop/worker.py` after the opened window is found and maximized
- Reuse the existing `WindowManager.ensure_interactable_window(...)` logic instead of introducing a second focus mechanism
- Carry forward the normalized/focused window returned from that interaction outcome

The important distinction is that maximize and focus are different states on Windows. This change makes foreground focus a required precondition before page-ready matching starts.

## Testing

Add focused coverage for:

- newly opened raid window is maximized before focus is attempted
- newly opened raid window must be focusable before page-ready waiting starts
- focus failure returns `window_not_focusable`
- page-ready wait only runs after focus succeeds
- slot `Test` behavior remains unchanged
