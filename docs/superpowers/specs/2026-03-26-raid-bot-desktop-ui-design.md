# Raid Bot Desktop UI Design

## Goal

Build a single Windows desktop application that wraps the existing raid bot in a native GUI. The app should guide first-time setup through a step-by-step wizard, provide a normal settings page after setup, show live bot statistics and recent activity, and allow the running app to be minimized to the system tray.

## Relationship To Existing Bot

The current project already contains a working headless bot with:

- Telegram user-account connectivity
- raid message parsing
- in-memory deduplication
- Chrome profile launching
- runtime wiring and tests

This desktop UI is a second layer around that bot. The design should preserve the current bot logic as a reusable non-UI runtime and add a Qt desktop shell around it rather than rewriting the bot into window code.

## Scope

### In scope

- Native Windows desktop application
- Single-app architecture
- First-run onboarding wizard
- Normal settings page after setup
- One-time in-app Telegram authorization with later session reuse
- Automatic Telegram chat discovery during setup
- Automatic `Raidar` sender discovery/confirmation during setup
- Automatic Chrome profile detection and selection during setup
- Start and stop controls for the bot
- Live status, counters, recent activity, and last-error display
- Minimize-to-tray behavior
- Tray menu for show, start/stop, and quit
- App-managed local configuration storage

### Out of scope

- Web UI
- Split service/daemon architecture
- Backlog scan on startup
- Multi-account raid execution
- Browser automation inside X/Twitter
- Remote control or multi-device sync
- Packaging/installer work beyond what is needed to run locally during development

## Recommended Approach

Use a PySide6 desktop application with the existing bot runtime moved behind a clean UI-facing controller.

This is the best fit for the approved requirements because:

- it supports a proper native Windows window and tray icon
- it handles a guided wizard and settings UI cleanly
- it provides enough structure for future multi-account expansion
- it allows the bot to run in the same application while keeping the UI responsive

## Architecture

The application should have two main layers inside one process:

### UI layer

- onboarding wizard
- main window
- settings page
- stats and activity views
- tray icon and tray menu

### Bot layer

- existing Telegram client integration
- parser, dedupe, and Chrome opener
- runtime start/stop lifecycle
- event emission for status and activity updates

The bot layer should run in a worker thread instead of the UI thread. Window classes should not directly contain Telegram or Chrome logic.

## Main Components

- `desktop/app`
  - application bootstrap and main window creation
- `desktop/wizard`
  - first-run step-by-step setup flow
- `desktop/settings`
  - editable settings page for post-setup changes
- `desktop/tray`
  - tray icon behavior and tray menu actions
- `desktop/stats`
  - live counters, recent activity list, and last-error display
- `desktop/config`
  - persistent config file loading and saving for the desktop app
- `desktop/controller`
  - bridge between the UI and the reusable bot runtime
- existing bot runtime modules
  - continue to implement raid detection and execution logic

## First-Run Wizard Flow

The wizard should be the default experience when no saved app config exists.

### Step 1: Welcome

- explain what the bot does
- explain that it uses a Telegram user account
- explain that Chrome must already be logged into the desired X account

### Step 2: Telegram Authorization

- capture Telegram API credentials
- capture the phone number needed for one-time Telethon authorization
- if a valid existing Telethon session file is already present, reuse it and skip code entry
- otherwise request the Telegram login code and 2FA password only if Telegram requires them
- never persist login codes or 2FA passwords after authorization completes
- if authorization is interrupted or the session is invalid, allow retry and replace the incomplete session cleanly
- show clear success or failure state

### Step 3: Chat Discovery

- fetch accessible chats from Telegram
- present searchable/selectable chat list
- let the user choose whitelisted chats

### Step 4: Raidar Selection

- inspect selected chats using participant/entity data when available
- prefer an exact username match of `raidar`
- otherwise prefer an exact display-name match of `Raidar`
- if exactly one match is found, preselect it and show confirmation
- if multiple or no exact matches are found, present candidates inferred from recent message senders in the selected chats and require explicit confirmation
- expose a manual sender-ID override only as an advanced fallback on this step
- store the selected sender ID, not only the display name

### Step 5: Chrome Profile Selection

- detect local Chrome profiles
- present them with friendly labels when available
- let the user choose the profile already logged into X

### Step 6: Review And Save

- present a final summary
- save the app config locally
- offer `Start bot now`

After this completes, future launches should open the main window instead of the wizard.

## Main Window

After setup, the app should open into a normal control window with:

- current bot runtime state
- current Telegram connection state
- start and stop controls
- recent activity list
- last error panel
- lightweight statistics view
- access to settings

The main window should not expose raw internal bot structures. It should present operator-focused information only.

## Settings Page

After first-run setup, the app should expose a normal settings page that allows editing:

- Telegram API ID and API hash in an advanced section
- Telegram session status with a `Reauthorize` action
- whitelisted chats
- selected `Raidar` sender
- selected Chrome profile

Settings behavior should be:

- whitelist, `Raidar` sender, and Chrome profile changes apply live to future messages
- Telegram credential or session changes trigger a controlled reconnect or reauthorization flow rather than requiring a full app restart
- conflicting edits are blocked only while authorization, startup, or shutdown is actively in progress

## Runtime State Model

The desktop app should use one unified bot state model:

- `setup_required`
- `stopped`
- `starting`
- `running`
- `stopping`
- `error`

The Telegram connection state should be tracked separately as:

- `disconnected`
- `connecting`
- `connected`
- `reconnecting`
- `auth_required`

The main window, tray menu, and controller should derive labels and allowed actions from these states instead of using separate ad-hoc notions of "app running" or "bot running."

Recoverable Chrome-open failures should not move the bot out of `running`; they should surface through stats, recent activity, and the last-error display.

## Tray Behavior

The application should use tray behavior only as an explicit minimize action after setup, not as a replacement for the window close action.

Required tray behavior:

- `Show`
- `Start bot` or `Stop bot`
- `Quit`

Expected behavior:

- during first-run setup, close exits the app and minimize behaves like a normal window minimize
- after setup, pressing the minimize button hides the window to the tray
- when the bot is stopped, close exits the app normally
- when the bot is running, close asks for confirmation and then stops the worker cleanly before exit if the user confirms
- tray click or `Show` -> restore main window
- `Quit` -> shut down the bot worker cleanly and exit the app

## Statistics And Activity

The app should expose operator-relevant live data:

### Status

- bot runtime state from the unified runtime-state model
- Telegram connection state from the unified connection-state model
- last successful raid open timestamp

### Counters

- raids opened
- duplicate URLs skipped
- non-matching messages skipped
- open failures

These counters should persist across bot restarts and full app restarts until the local app state is cleared.

### Activity Feed

- timestamp
- action
- URL when relevant
- skip or error reason when relevant

The activity feed should persist the most recent 200 entries across app restarts.

### Error Surface

- show most recent error in the main window
- include enough text to diagnose setup and runtime problems

## Configuration Model

The desktop app should own a local persistent config file rather than relying on manual `.env` editing as the primary setup path.

Config should include:

- Telegram API ID
- Telegram API hash
- Telegram session path
- optional last-used phone number for convenience
- whitelisted chat IDs
- allowed `Raidar` sender ID
- Chrome profile directory
- app behavior flags such as start-on-launch later if added

Chrome executable path and the base Chrome user-data directory should be auto-detected from standard Windows locations in v1 and should not be user-editable settings.

Persistent counters and activity history should live in a separate local app-state store rather than in the editable config document.

The bot runtime should still receive a validated config object, not direct access to UI widgets or partially edited values.

## Runtime Model

The bot should run inside the same application but outside the UI thread.

The worker runtime should:

- start cleanly from saved config
- emit events for connection, activity, and errors
- stop cleanly on command
- continue running when the window is minimized to tray

The UI should communicate with the worker through clear controller interfaces and events rather than direct cross-thread mutation.

## Discovery Behavior

### Telegram discovery

During setup, the app should use the logged-in Telegram user session to:

- list chats the account can access
- allow chat selection for whitelist creation
- inspect chat participants or message sources as needed to help identify `Raidar`
- attempt exact username matching against `raidar`
- otherwise attempt exact display-name matching against `Raidar`
- if still ambiguous, present inferred candidates from recent message senders and require confirmation

### Chrome profile detection

During setup, the app should inspect the local Chrome user-data directory and present available profiles for selection.

The app should derive Chrome installation and base user-data paths from standard Windows locations. The v1 UI should not expose a manual Chrome executable path field.

If Chrome cannot be detected from those standard locations, setup should fail with a diagnostic error instead of prompting for a manual browser path.

## Error Handling

Failure handling should be operator-visible and non-fatal where possible.

- Telegram login failure
  - keep user in the wizard and show the error
- partial Telegram authorization
  - keep user on the authorization step, allow retry, and replace incomplete session state safely
- chat discovery failure
  - allow retry
- Chrome profile detection failure
  - show diagnostic message and prevent silent save
- runtime disconnect
  - update status and retry according to bot-runtime behavior
- Chrome launch failure
  - record activity and increment error stats without crashing the app

## Testing Strategy

Keep the current bot logic tests and add desktop-focused coverage:

- config persistence tests
- first-run detection tests
- worker-controller event tests
- tests for start/stop state transitions
- tests for activity and counter updates
- focused UI tests for:
  - wizard progression
  - settings save/load
  - tray minimize and restore behavior

UI tests should remain focused on behavior boundaries, not pixel-perfect rendering.

## Future Extension Path

This design should support later work without rewriting the base app:

- multi-profile raid opening
- multi-account execution
- richer dashboards
- packaging and installer work
- startup-on-login and auto-start bot behavior

## Open Decisions Deferred

These should be settled during implementation planning:

- exact PySide6 window/module layout
- exact app config and app-state file formats and locations
- exact presentation of recent activity rows and error details
