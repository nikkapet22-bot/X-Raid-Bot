# Raid Bot Design

## Goal

Build a background Windows app that runs 24/7, watches Telegram as a user account, detects new raid posts from `Raidar` in whitelisted chats, and opens the matching X/Twitter status link in a specific Chrome profile exactly once per process lifetime.

## Scope

### In scope

- Telegram user-account login with a saved local session
- New incoming messages only
- Whitelisted chat filtering
- Sender filtering for the specific `Raidar` account
- Detection of active raid messages that contain a single X/Twitter status link
- Immediate opening of the detected link in a configured Chrome profile
- In-memory deduplication so the same raid URL is not opened twice while the process is running
- Background runtime with reconnect handling and logging

### Out of scope

- Telegram bot-account support
- Backlog scanning on startup
- Persisting dedupe state across restarts
- Handling message edits as new work
- Multi-account raiding
- Any X/Twitter automation beyond opening the target URL

## Recommended Approach

Use a single Python daemon with a Telegram listener and a Chrome launcher.

This is the simplest design that matches the current requirements:

- it reacts immediately to new raid posts
- it avoids the fragility of full browser automation
- it stays small enough to run and debug easily
- it leaves room to add multi-profile or multi-account opening later

## Architecture

The app should be split into a small set of focused modules:

- `telegram_client`
  - Logs in as the Telegram user account
  - Subscribes to new-message events only
  - Reconnects automatically on transient disconnects
- `raid_filter`
  - Accepts messages only from configured whitelisted chats
  - Accepts messages only from the configured `Raidar` sender ID
- `raid_parser`
  - Extracts the raid target URL from the message text
  - Verifies the message looks like an active raid request
  - Rejects queue-style or irrelevant messages
- `dedupe_store`
  - Stores normalized URLs already opened during the current process lifetime
- `chrome_opener`
  - Launches the URL in a configured Chrome user-data directory and profile
- `service_loop`
  - Coordinates startup, shutdown, reconnects, and logging

## Message Matching Rules

Each new Telegram message flows through the following checks:

1. Receive a new-message event.
2. Verify the chat is in the configured whitelist.
3. Verify the sender matches the configured `Raidar` sender ID.
4. Parse the message text.
5. Extract a matching X/Twitter status URL:
   - Accept `x.com/.../status/<id>`
   - Accept `twitter.com/.../status/<id>`
6. Verify the message looks like an active raid:
   - contains one or more raid markers such as `Likes`, `Retweets`, or `Replies`
   - does not represent a queue-style `Next up...` listing
7. Normalize the extracted URL.
8. Skip the URL if it is already present in the in-memory dedupe store.
9. Open the URL in Chrome.
10. Add the normalized URL to the dedupe store after a successful open attempt.

## Data Model

Minimal runtime data is needed:

- `settings`
  - Telegram API credentials
  - Telegram session path
  - Whitelisted chat IDs
  - Allowed `Raidar` sender ID
  - Chrome executable path
  - Chrome user-data-dir
  - Chrome profile directory
  - Optional throttle or cooldown settings
- `opened_urls`
  - In-memory `set[str]` of normalized raid URLs

## Runtime Behavior

The application runs as a long-lived local process on Windows.

Expected behavior:

- Start once and remain connected to Telegram
- Process only new incoming messages after startup
- Ignore old backlog messages
- Ignore message edits for raid execution purposes
- Continue running even if individual parse or browser-launch operations fail
- Emit structured logs for matched, skipped, duplicate, opened, and failed events

## Chrome Launch Strategy

The first version should open URLs by launching Chrome with an explicit profile configuration rather than automating browser actions.

Expected Chrome launch inputs:

- Chrome executable path
- `--user-data-dir`
- `--profile-directory`
- target raid URL

This assumes the configured Chrome profile is already logged into the desired X account.

## Error Handling

Failure handling should favor availability:

- Telegram disconnects
  - reconnect with backoff
- Message parse failures
  - log and skip
- Missing or invalid URL
  - log and skip
- Chrome open failure
  - log the URL and error, keep the service alive
- Duplicate raid URL
  - log and skip

## Testing Strategy

The first test layer should focus on deterministic logic:

- unit tests for active-raid message detection
- unit tests for queue-message rejection
- unit tests for X/Twitter status URL extraction
- unit tests for URL normalization
- unit tests for in-memory dedupe behavior

One lightweight smoke path should verify that a sample Raidar message produces exactly one Chrome open request.

## Future Extension Path

The design should leave room for later expansion without rewriting the Telegram intake path:

- open the same raid URL in multiple Chrome profiles
- add persistent dedupe storage if needed
- add operational status output or a small local dashboard
- add install and service-management wrappers for easier 24/7 operation

## Open Decisions Deferred

These are intentionally deferred until implementation planning:

- exact Python library choice for Telegram connectivity
- exact process manager or Windows startup strategy
- exact logging format and destination
- whether to count a failed Chrome launch as "opened" for dedupe purposes
