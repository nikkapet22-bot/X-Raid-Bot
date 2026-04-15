# Restart All Raid Replay Design

## Goal

Extend the dashboard `Restart All` control so it can optionally do more than reset red profiles to green.

When the new replay checkbox is enabled, pressing `Restart All` should:

- reset all profiles to green
- fetch the latest valid recent raid from Telegram
- skip profiles that already succeeded on that exact raid URL
- raid only the remaining profiles one by one

This is a recovery workflow for operators who want to restore failed profiles and immediately catch them up on the current raid without re-running accounts that already completed it.

## Current Problems

### Restart All Only Resets State

The current `Restart All` button is a bulk version of the per-profile restart icon:

- it turns all profiles from red back to green
- it clears their last error
- it does not launch any raid work

That is useful, but it is incomplete for a live raid workflow:

- users often want failed profiles to recover and immediately rejoin the active raid
- large account sets make one-by-one manual recovery expensive
- users should not need to press `Restart All`, then manually raid each missing profile separately

### Re-Raiding Successful Profiles Is Wrong

The replay behavior cannot simply run all profiles again. If some profiles already succeeded on the latest raid:

- they should be skipped
- only missing profiles should run

This requires exact URL-level filtering based on the app's saved success activity.

## Desired Behavior

## Profiles Header UI

The Profiles dashboard header should render the controls in this exact order:

- `[Restart All] Raid? [ ]`

Meaning:

- `Restart All` remains the action button
- `Raid?` is a persistent checkbox immediately to its right

This should be visually compact and clearly tied to the button, not presented as a separate settings section.

## Persistent Checkbox

Add one new persisted app setting:

- `raid_on_restart_enabled: bool = False`

Rules:

- it survives app restarts
- it stays enabled until the user turns it off
- toggling it should auto-save immediately

## Restart All Behavior

### When `Raid?` Is Unchecked

Keep current behavior:

- reset all profiles to green
- clear their errors
- do not launch any raid replay

### When `Raid?` Is Checked

Pressing `Restart All` should execute this flow:

1. reset all profiles to green
2. fetch the latest valid recent raid from Telegram, using the same lookup rules as `Raid NOW!`
3. inspect saved successful activity for that exact normalized raid URL
4. build the replay list from profiles that did not already succeed on that URL
5. execute only those profiles, one by one

Important rule:

- this is not "raid everyone again"
- this is "catch up the profiles that missed the latest valid raid"

## Success Filter Rules

The replay skip logic should treat a profile as already completed when saved activity contains:

- `action = automation_succeeded`
- the same `profile_directory`
- the same normalized raid URL returned by the latest valid recent raid lookup

Profiles that already succeeded on that URL should not be replayed.

Profiles that failed, were skipped, or have no success record for that URL should be eligible.

## Failure Handling

### Telegram Or Lookup Failure

If `Raid?` is checked but replay cannot start because:

- Telegram is not connected
- the bot is not running
- no recent valid raid is found

Then:

- the reset still happens
- replay does not start
- the user gets a clear status/error message

### Nothing To Replay

If all profiles already succeeded on the fetched latest raid URL:

- the reset still happens
- no replay run starts
- the user gets clear feedback that there were no missing profiles to replay

## Runtime Model

This feature should reuse the existing `Raid NOW!` raid lookup path rather than introducing a second independent replay system.

The worker already knows how to:

- fetch the latest valid recent raid from Telegram
- execute a manual one-off raid for selected profiles

The new behavior should build on those seams:

- `Restart All` handles the state reset
- the worker then runs a filtered one-off replay list for the fetched latest raid URL

This keeps the replay logic aligned with the existing Telegram validation rules instead of creating a parallel source of truth.

## Component Changes

### `raidbot/desktop/models.py`

Add persisted config field:

- `raid_on_restart_enabled: bool = False`

### `raidbot/desktop/storage.py`

Save and load `raid_on_restart_enabled`, defaulting older configs cleanly to `False`.

### `raidbot/desktop/main_window.py`

Update the Profiles header row so it renders:

- `Restart All`
- `Raid?`
- checkbox

Wire the checkbox to auto-save through the controller.

Keep the existing `Restart All` button behavior as the trigger, but route it through the new controller path that knows whether replay is enabled.

### `raidbot/desktop/controller.py`

Add:

- setter for `raid_on_restart_enabled`
- extended `Restart All` command that includes the current checkbox state

If the bot is not running, the local fallback should still support plain reset behavior. Replay should require the normal worker/runtime path.

### `raidbot/desktop/worker.py`

Extend `reset_all_raid_profiles()` into a reset-plus-optional-replay workflow:

- always reset all profiles first
- if replay is disabled, stop there
- if replay is enabled:
  - fetch the latest valid recent raid
  - determine which profiles already succeeded on that URL
  - execute only the missing profiles

This should reuse the same recent-raid lookup semantics as `Raid NOW!` and should not re-raid profiles that already succeeded on the current/latest raid.

## Testing

Add coverage for:

- config/storage round-trip for `raid_on_restart_enabled`
- Profiles header renders `Restart All` followed by `Raid?` and checkbox
- checkbox auto-saves through the controller
- `Restart All` with replay disabled keeps current reset-only behavior
- `Restart All` with replay enabled fetches the latest valid recent raid
- replay skips profiles that already succeeded on that exact URL
- replay runs profiles that did not succeed on that URL
- replay reports clear feedback when no recent valid raid exists
- replay reports clear feedback when nothing needs to be replayed

## Out Of Scope

This feature does not:

- reintroduce the old per-profile restart replay model
- replay an arbitrary cached old URL
- queue multiple old raids
- change `Raid NOW!` button behavior
- change how ordinary auto-run detection works
