# Headless Playwright Side Project Design

## Summary

Create a separate side project inside this repo that proves X raid automation can run headlessly using Playwright and Chromium, without disturbing the user’s desktop session.

This side project is intentionally separate from the current desktop screen-automation bot. It should reuse the existing Telegram-side configuration and filtering rules, but it should own its own browser runtime, auth state, and UI.

## Goals

- Prove that X raid actions can be executed headlessly through DOM automation.
- Avoid real mouse movement, foreground window focus, and visible desktop disruption.
- Reuse the current bot’s Telegram credentials/session, whitelisted chats, allowed senders, and raid parsing logic.
- Provide a small UI for bootstrap, start/stop, action toggles, and status feedback.

## Non-Goals

- Replace the existing desktop bot.
- Add the headless engine into the current desktop app UI yet.
- Support multiple X accounts in v1.
- Reuse the user’s actively-open Chrome profile directly.
- Ship a polished production-ready release immediately.

## Product Shape

The side project should be a separate mini app in the same repo.

It is:

- a different runtime
- a different UI
- a different browser/auth state

It is not:

- a new mode inside the current desktop bot yet
- a retrofit of the current image-based automation path

## Architecture

### Shared With Current Bot

The headless side project should reuse the existing desktop bot’s Telegram-side configuration:

- Telegram API credentials
- Telegram session path
- whitelisted chat IDs
- allowed sender IDs
- raid parsing behavior

This avoids maintaining two separate intake/filtering configurations.

### Separate From Current Bot

The headless side project must maintain its own browser-side state:

- Playwright persistent user-data/auth directory
- headless-only settings
- its own runtime status/log state

It should not attempt to reuse the current desktop bot’s active Chrome profile directly.

## Runtime Flow

V1 runtime should be:

1. Load shared Telegram/filtering config from the existing bot config.
2. Load headless-only settings from its own config/state.
3. Start Telegram intake using the shared credentials/session.
4. Filter messages using the same allowed chats, allowed senders, and parser rules.
5. For each valid raid:
   - use a dedicated Playwright persistent context for one X account
   - navigate to the target X post
   - execute enabled actions in order:
     - Reply
     - Like
     - Repost
     - Bookmark
6. Record a structured result for each attempt.

V1 constraints:

- one X account only
- one raid at a time
- no multi-account fan-out
- no coordinate/image fallback

## X Automation Strategy

Use:

- Python
- Playwright
- Chromium persistent context

Action strategy:

- Reply:
  - open reply composer
  - enter reply text
  - submit
  - verify success through page state
- Like:
  - locate like button
  - click
  - verify liked state
- Repost:
  - click repost trigger
  - choose repost action
  - verify reposted state
- Bookmark:
  - click bookmark
  - verify bookmarked state

Important v1 rule:

- rely on DOM locators and page state only
- if the action cannot be found reliably, fail clearly
- do not reintroduce pixel matching or coordinate clicks

## Auth And Bootstrap

V1 should not automate X login.

Instead, provide a one-time bootstrap flow:

- user clicks `Bootstrap Login`
- app launches Playwright in headed mode
- user logs into the dedicated X account manually
- Playwright persistent state is saved

Normal runs then reuse that saved state.

If auth expires:

- runtime reports a clear auth failure
- user reruns bootstrap

No password handling or MFA automation is needed in v1.

## UI

Build a small separate PySide6 companion app for the proof-of-concept.

### Required Controls

- `Bootstrap Login`
- `Start`
- `Stop`
- action toggles:
  - Reply
  - Like
  - Repost
  - Bookmark

### Required Status

- X auth state:
  - `Authenticated`
  - `Needs Login`
- last detected raid
- last result
- simple status / error log

### Not Needed Yet

- charts
- multi-account management
- profile cards
- packaging polish
- integration into the existing desktop UI

## Repo Layout

Recommended new package:

- `raidbot/headless`

Suggested responsibilities:

- `raidbot/headless/app.py`
  - separate app entry point
- `raidbot/headless/window.py`
  - minimal PySide6 UI
- `raidbot/headless/config.py`
  - shared desktop config loading plus headless-only config/state
- `raidbot/headless/models.py`
  - headless app state/result dataclasses
- `raidbot/headless/session.py`
  - Playwright persistent context lifecycle and auth validation
- `raidbot/headless/listener.py`
  - Telegram intake wiring using shared credentials/config
- `raidbot/headless/runner.py`
  - one-raid-at-a-time execution orchestration
- `raidbot/headless/actions.py`
  - X DOM action flows

## Error Handling

The side project should fail clearly, not guess.

Expected error classes:

- shared bot config missing or invalid
- Telegram auth/session unavailable
- X auth missing or expired
- locator/action not found
- action state verification failed
- navigation timeout

For v1:

- surface errors in the small UI log/status area
- keep reason codes structured enough for later diagnostics

## Testing Strategy

Focus on isolated tests first:

- config loading and shared config reuse
- headless-only config persistence
- start/stop queue behavior
- action toggle state
- session bootstrap/auth-state behavior with mocked Playwright
- runner result semantics with mocked Playwright page/session layer

Do not rely on live X in automated tests for v1.

## Migration / Future Expansion

If the proof works, the next expansions can be:

- multi-account fan-out
- integration into the main desktop app as a second engine
- more robust selector strategy and fallback verification
- shipping/packaging the headless app

Those are explicitly future phases, not part of this first proof-of-concept.
