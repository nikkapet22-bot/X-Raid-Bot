## Headless Auth Import Design

### Goal

Replace the fragile Playwright login bootstrap with an auth import flow that pulls X authentication from the same dedicated Chrome raid profile already configured in the desktop bot.

### Problem

X is rejecting direct login attempts from the headless Playwright bootstrap flow, even when the browser channel is switched to branded Chrome. The current bootstrap path is therefore not a reliable way to establish headless auth.

### Decision

The headless app will no longer ask the user to log into X inside Playwright. Instead it will:

- read the desktop bot's configured Chrome raid profile
- require Chrome windows using that profile to be fully closed
- launch a one-time import bridge against that profile
- export headless-owned Playwright auth state
- use only that exported auth state during normal headless runtime

### UX

The current `Bootstrap Login` button should become `Import X Auth`.

When pressed:

1. the app attempts to locate the same Chrome user-data directory and profile selected by the desktop bot
2. if Chrome is still open or the profile cannot be found, the app logs a clear error
3. if import succeeds, the headless app updates auth state to `Authenticated`

The import is explicit and one-way. The headless runtime never keeps operating on the live desktop Chrome profile.

### Architecture

Reuse existing Chrome discovery from `raidbot/desktop/chrome_profiles.py` to locate:

- `chrome.exe`
- Chrome user-data directory
- available profile directories

The import flow will target the desktop bot's configured `chrome_profile_directory` inside that environment.

The headless project will keep its own auth artifact in the headless data directory. That artifact becomes the runtime source of truth for Playwright authentication.

### Safety Constraints

- Chrome must be fully closed during import
- import failure must not overwrite an existing working headless auth artifact
- runtime must not point at the live desktop Chrome profile after import completes

### Scope

In scope:

- headless config/session/bootstrap UI behavior
- auth import plumbing
- focused tests around import success/failure and runtime auth reuse

Out of scope:

- selector changes
- Telegram intake changes
- multi-account support
- using the live Chrome profile directly during headless runtime

### Testing

- verify import resolves the desktop bot's configured Chrome raid profile
- verify import fails clearly when Chrome/profile resolution is unavailable
- verify import writes a headless-owned auth artifact
- verify runtime auth checks use the imported headless artifact instead of the live Chrome profile
