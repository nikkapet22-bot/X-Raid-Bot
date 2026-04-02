# Headless Playwright Live Proof Design

## Summary

Build the next slice of the headless Playwright side project so it becomes a real live proof-of-concept:

- live Telegram intake
- real Playwright execution on X
- small PySide6 UI with start/stop, auth status, and logs

This slice should run in headed mode first for debugging.

## Goals

- Turn the headless side project from scaffolding into a working live runtime.
- Keep the UI responsive while the runtime listens and executes in the background.
- Execute real X actions for:
  - Like
  - Repost
  - Bookmark
- Skip raids that require Reply with a clear `unsupported_for_now` result.

## Non-Goals

- Headless-first execution.
- Reply automation in this slice.
- Multiple X accounts.
- Integration into the existing desktop bot UI.
- Production hardening or packaging.

## Runtime Model

Use a background runtime controller behind the small PySide6 UI.

### Bootstrap Login

- launches headed Playwright persistent context
- user logs into the dedicated X account manually
- saved auth state is reused later

### Start

- validate shared Telegram config
- validate X auth state
- start live Telegram intake in background
- queue valid raid jobs one at a time

### Stop

- stop live Telegram intake
- stop/drain runtime cleanly
- update UI/log state

## Execution Rules

Supported actions in this slice:

- Like
- Repost
- Bookmark

Unsupported in this slice:

- Reply

If a detected raid requires `Reply`:

- do not partially execute it
- return `unsupported_for_now`
- record/log that result clearly

This keeps the proof honest: either the supported action set handles the raid, or it is explicitly skipped.

## X Automation Strategy

Use real Playwright locator flows in headed Chromium.

### Like

- navigate to post
- locate like button
- click it
- verify liked state

### Repost

- locate repost control
- open repost menu
- click repost action
- verify reposted state

### Bookmark

- locate bookmark control
- click it
- verify bookmarked state

No image matching, coordinate clicking, or desktop automation fallback is allowed.

## UI Behavior

The existing small headless UI should show:

- auth state:
  - Authenticated
  - Needs Login
- runtime state:
  - Running
  - Stopped
- last detected raid
- last result
- scrolling logs

Buttons:

- `Bootstrap Login`
- `Start`
- `Stop`

Action toggles remain visible, but real execution only applies to the supported action set in this slice.

## Architecture

### New / Expanded Components

- `raidbot/headless/runtime.py`
  - background runtime controller/service
  - listener lifecycle
  - queueing
  - stop signaling

- `raidbot/headless/listener.py`
  - build and run the real Telegram listener
  - adapt detected raids into runtime jobs

- `raidbot/headless/runner.py`
  - enforce one-at-a-time execution
  - reject reply-required raids as `unsupported_for_now`

- `raidbot/headless/actions.py`
  - real Playwright locator flows for Like/Repost/Bookmark

- `raidbot/headless/window.py`
  - log/status updates from runtime
  - running-state feedback

- `raidbot/headless/app.py`
  - wire window and runtime controller together

## Error Handling

Expected surfaced errors:

- missing shared config
- Telegram listener startup failure
- X auth missing/expired
- unsupported reply-required raid
- Playwright navigation failure
- locator/action verification failure

UI should surface these as:

- last result reason
- scrolling log entries
- auth/runtime state updates

## Testing Strategy

Focused automated tests should cover:

- runtime start/stop lifecycle
- UI log/status updates from runtime events
- reply-required raid skips with `unsupported_for_now`
- action executor calling the expected Playwright locator flow via mocked page objects
- listener-to-runner handoff with mocked listener/session layer

Live X behavior remains manual debugging territory for this slice.

## Future Work

After this slice is stable:

- add Reply automation
- switch from headed-first debugging to optional headless mode
- harden selectors and retry behavior
- consider multi-account execution later
