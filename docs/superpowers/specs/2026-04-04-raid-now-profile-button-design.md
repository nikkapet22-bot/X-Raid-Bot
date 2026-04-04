# Raid NOW Profile Button Design

**Date:** 2026-04-04

## Goal

Replace the profile-card `Restart` button and `Raid on Restart` toggle with a single `Raid NOW!` action that manually runs the most recent valid Telegram raid for one chosen profile.

## Decisions

- `Raid NOW!` is always visible on every profile card.
- `Raid NOW!` is enabled only when Telegram is actually `connected`.
- A red profile can still use `Raid NOW!`.
- `Raid NOW!` does not use the in-memory replay-on-restart flow.
- `Raid NOW!` fetches recent Telegram messages from the allowed chats and allowed senders, newest first.
- The first message that passes the existing raid detector becomes the manual run target.

## UI Changes

### Profile cards

Remove:

- `Restart`
- `Raid on Restart`
- its toggle

Add:

- `Raid NOW!`

The button stays visible for all profiles and is enabled only while the bot is Telegram-connected.

## Runtime Behavior

When the user presses `Raid NOW!` on a profile:

1. The app verifies that the bot is connected.
2. The app fetches recent Telegram messages from the currently allowed chats.
3. Messages are scanned newest-first.
4. The app reuses the normal raid detection rules:
   - allowed sender
   - valid raid link
   - action markers
   - video requirement
5. The first valid recent raid is executed only for the selected profile.

This is a one-profile manual run. It does not depend on `_latest_replayable_raid`.

## Failure Handling

`Raid NOW!` should fail clearly when:

- Telegram is not connected
- manual automation is blocked by the queue
- no recent valid raid is found
- the selected profile has no usable configured actions
- the selected profile run fails normally during automation

## Persistence Cleanup

`raid_on_restart` should be removed from:

- `RaidProfileConfig`
- desktop config serialization
- desktop config deserialization
- profile-card UI wiring
- controller restart/toggle flow

Older saved configs that still contain `raid_on_restart` must continue to load without error. The field should simply be ignored on load.

## Testing

Add coverage for:

- profile card renders `Raid NOW!` instead of old restart/toggle controls
- `Raid NOW!` routes to the controller
- `Raid NOW!` is disabled unless Telegram is `connected`
- worker fetches and executes the latest valid Telegram raid for only the chosen profile
- no valid recent raid returns a clear failure
- legacy configs containing `raid_on_restart` still load cleanly
