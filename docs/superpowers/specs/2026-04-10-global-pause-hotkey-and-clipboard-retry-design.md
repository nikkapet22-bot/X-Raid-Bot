# Global Pause Hotkey And Clipboard Retry Design

**Date:** 2026-04-10

## Goal

Add a system-wide pause/resume hotkey that the user configures from Settings, and harden reply image pasting so transient Windows clipboard locks do not fail a run immediately.

## Decisions

- The pause/resume hotkey is system-wide on Windows.
- The user configures the hotkey from the Settings page by clicking a capture field and pressing a combo.
- Only `Ctrl + key` combinations are accepted.
- Pressing the hotkey pauses immediately, even during an active raid.
- Pressing the same hotkey again resumes the interrupted run first, then continues queued raids.
- While paused, Telegram stays connected and newly detected raids are queued.
- The reply image clipboard path gets bounded retry logic.
- This is a minor feature release and should bump the app to `v2.2.0`.

## UI Changes

### Settings

Add a new Settings control for the global pause/resume hotkey:

- label: `Pause / Resume Hotkey`
- value: clickable capture field
- accepted input: `Ctrl + key`

Behavior:

1. User clicks the field.
2. The field enters capture mode.
3. The next valid `Ctrl + key` combo is stored and shown.
4. Invalid input is rejected clearly.

The chosen hotkey is saved in desktop config and restored on startup.

## Runtime Behavior

### Pause

When the registered hotkey is pressed while the bot is active:

1. The worker enters a hotkey-paused state.
2. The active automation runtime receives `request_stop()` immediately.
3. The interrupted current run is converted into a resumable worker-owned pause snapshot.
4. Telegram intake remains alive.
5. New raids continue to queue but do not execute.

### Resume

When the hotkey is pressed again:

1. The worker clears the hotkey-paused state.
2. If there is an interrupted run snapshot, that run resumes first.
3. Resume restarts from the last safe step boundary, not from the middle of a click, paste, or clipboard call.
4. After the interrupted run finishes or fails, queued raids continue normally.

## Pause Snapshot Model

To support true resume behavior, the worker needs a small persisted-in-memory pause snapshot containing:

- active URL
- active profile directory
- execution mode:
  - `auto_run`
  - `raid_now`
  - `warmup_browse`
  - `warmup_real_action`
- selected sequence id
- next safe step boundary to resume from
- active window handle or context if still usable
- marker that the pause came from the hotkey

If the paused window is no longer usable when the user resumes:

- the interrupted run fails normally
- the affected profile is updated through the normal failure path
- queued raids then continue

## Queue Semantics

The hotkey pause is separate from the existing auto-run processor paused state that is used for failures such as `auto_run_paused`.

During hotkey pause:

- the automation queue keeps accepting new detected raids
- queued work is not executed
- queue length and current URL state remain honest

Resume should not silently discard queued work.

## Hotkey Registration

Use native Windows global hotkey registration for the configured `Ctrl + key` combo.

Behavior:

- register on startup after config load
- unregister and re-register when the configured combo changes
- unregister on shutdown
- if registration fails, emit a clear UI error and keep the previous hotkey state unchanged

## Clipboard Retry Fix

The current reply image path can fail with `OpenClipboard Failed` after text has already pasted. The image step should not fail immediately on a transient lock.

Add bounded retry around Windows clipboard operations, especially:

- file-reference image clipboard paste
- text/image clipboard writes as shared hardening where sensible

Behavior:

- retry a small fixed number of times with short waits
- if clipboard access succeeds, continue normally
- if all retries fail, preserve the real failure reason and fail the profile normally

This is a runtime hardening fix, not a change to preset selection or reply sequencing.

## Failure Handling

The hotkey flow should fail clearly when:

- the configured hotkey cannot be registered
- the user enters an invalid combo
- the paused window/context no longer exists on resume
- the resumed run fails normally after resuming from the last safe step boundary

The clipboard retry path should fail clearly when:

- the preset image file is missing
- clipboard operations remain locked after all retries

## Testing

Add coverage for:

- Settings hotkey capture field accepts valid `Ctrl + key` combos
- invalid hotkey input is rejected
- config save/load round-trips the hotkey
- global hotkey registration updates when config changes
- worker toggles hotkey pause state
- hotkey pause stops an active run immediately
- queued raids keep accumulating while hotkey-paused
- resume continues the interrupted run first
- unusable paused window fails cleanly on resume
- image clipboard retry succeeds after transient clipboard lock
- image clipboard retry fails cleanly after retry exhaustion
- packaging/version assertions updated for `v2.2.0`
