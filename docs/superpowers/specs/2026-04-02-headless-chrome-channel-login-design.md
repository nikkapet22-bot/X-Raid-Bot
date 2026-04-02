## Headless Chrome Channel Login Design

### Goal

Improve the headless Playwright proof's X login compatibility by switching from Playwright's bundled Chromium build to branded Google Chrome.

### Problem

The current bootstrap login flow launches a Playwright-controlled Chromium persistent context. X is rejecting login attempts with a generic "Could not log you in now. Please try again later" message. The most likely cause is the browser choice, not the app's local login wiring.

### Decision

Use Playwright `channel="chrome"` for both:

- headed bootstrap login
- headless runtime sessions

This keeps login and runtime on the same browser family and preserves headless execution capability.

### Behavior

- `Bootstrap Login` launches branded Google Chrome in headed mode
- normal runtime sessions launch branded Google Chrome in headless mode
- the dedicated Playwright persistent profile remains unchanged
- if Chrome channel launch fails, the app continues surfacing a clear error to the UI log

### Scope

In scope:

- `raidbot/headless/session.py`
- focused session/bootstrap tests

Out of scope:

- selector changes
- Telegram intake changes
- multi-account support
- reuse of the desktop bot's active Chrome profile

### Testing

- verify headed bootstrap launch passes `channel="chrome"`
- verify headless runtime launch passes `channel="chrome"`
- verify session cleanup still releases the Playwright manager
- keep bootstrap failure logging green
