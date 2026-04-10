# Warmup Graduation And Pause Feedback Design

## Goal

Improve warmup mode so it automatically graduates a profile back into normal raiding after enough completed warmup cycles, add visible warmup progress, and make queue pause/block states obvious in the UI instead of leaving the app misleadingly at `Running`.

## Current Problems

### Warmup Never Ends

Warmup mode currently loops forever with a per-profile `warmup_cycle_index` that only tracks the local `2 browse + 1 real action` pattern. There is no concept of completed full cycles, so a profile never automatically returns to normal raid behavior.

### Pause Has No Clear User Feedback

The hotkey pause feature currently suspends automation through the queue state, but the top panel still renders the raw bot runtime state as `Running`. Users can pause the bot successfully and still see:

- `Bot state: Running`
- `Telegram: Connected`

That makes the feature look broken even when the queue is actually suspended.

### Auto-Run Pauses Too Broadly

`auto_run_paused` currently happens because the auto-run processor pauses at the raid-item level whenever a work item fails. That means:

- one failed automation item can put the whole queue into a blocked state
- later Telegram raids are still detected
- but they get rejected as `auto_run_paused`
- profiles can remain green even while nothing is actually raiding

That is too broad. Per-profile automation failures should stay per-profile and should not block the rest of the bot.

## Desired Behavior

### Warmup Graduation

Each warmup-enabled profile should complete at most `20` full warmup cycles before automatically graduating out of warmup mode.

A full cycle is:

1. warmup browse flow
2. warmup browse flow
3. one real random raid action from the allowed warmup action set

After the third step succeeds, that profile has completed one full cycle.

Warmup profiles should also display a visible progress bar on the profile card:

- range `0%` to `100%`
- based on completed full cycles out of `20`
- hidden for non-warmup profiles

When a profile reaches `20` full completed cycles:

- `warmup_enabled` becomes `False`
- `warmup_cycle_index` resets to `0`
- `warmup_completed_cycles` resets to `0`
- `reply_enabled` becomes `True`
- `like_enabled` becomes `True`
- `repost_enabled` becomes `True`
- `bookmark_enabled` becomes `False`

The profile should then behave like a normal green profile on future raids.

If a warmup run fails:

- do not advance `warmup_cycle_index`
- do not advance `warmup_completed_cycles`
- fail the profile normally

If the user later re-enables `Warm me up baby` manually:

- start warmup fresh
- reset both warmup counters back to `0`

### Pause And Block Feedback

The UI must visibly distinguish user pause from true automation stop/block.

#### User Pause

When the user presses the global pause hotkey:

- top panel should display `Bot state: Paused`
- bot-state styling should be orange
- all profile cards should render an orange paused overlay
- Telegram status should still display its real connection state, for example `Connected`
- Bot Actions queue status should continue to show `Paused`

This is a display override, not a runtime disconnect. The bot may stay connected to Telegram while automation is paused.

#### True Global Stop / Block

When automation is genuinely blocked by an app-wide problem:

- top panel should display `Bot state: Stopped`
- bot-state styling should be red
- all profile cards should render a red stopped overlay

This stopped state is reserved for genuine global blockers, not ordinary per-profile automation failures.

#### Resume

When pause is cleared and the queue resumes:

- top panel should return to the real bot runtime state, such as `Running`
- profile cards should return to their real underlying colors/states

## Data Model Changes

Add one new per-profile persisted field:

- `warmup_completed_cycles: int = 0`

This field tracks how many full `2 browse + 1 real action` cycles a profile has completed while warmup mode is enabled.

Existing configs should load cleanly with a default of `0`.

## Runtime Changes

### Warmup Runtime

Current warmup runtime already supports:

- `warmup_cycle_index == 0` -> browse
- `warmup_cycle_index == 1` -> browse
- `warmup_cycle_index == 2` -> one real action

The new graduation behavior should extend that model:

- browse success on steps `0` and `1` still advances only the local cycle step
- real-action success on step `2` should:
  - increment `warmup_completed_cycles`
  - either:
    - wrap to the next warmup cycle if completed cycles are still below `20`
    - or graduate the profile out of warmup if this was cycle `20`

Graduation should persist immediately through config save, just like the existing warmup cycle persistence.

### Queue And Failure Semantics

Per-profile automation failures should not pause the whole auto-run queue.

New rule:

- if one profile gets an automation error, only that profile should fail
- other profiles should continue for the current raid
- future Telegram raids should continue normally
- ordinary per-raid/profile failures should not produce `auto_run_paused`

Queue-level blocked state should be reserved only for genuine global blockers, for example:

- no default action sequence configured
- automation runtime unavailable
- other app-wide conditions that make all further auto-run execution impossible

### Pause Presentation

Pause feedback should remain mostly UI-owned and should not require a deep runtime enum rewrite.

The main window should derive the displayed bot state like this:

- internal user-pause queue state -> show `Paused` with orange styling
- internal global blocked queue state -> show `Stopped` with red styling
- otherwise show the real bot runtime state from worker events

This keeps the current worker/controller mechanics intact while making the visible state honest to the user.

## Component Changes

### `raidbot/desktop/models.py`

- add `warmup_completed_cycles` to `RaidProfileConfig`

### `raidbot/desktop/storage.py`

- save and load `warmup_completed_cycles`
- default missing values to `0`

### `raidbot/desktop/controller.py`

When profile settings are saved:

- if `warmup_enabled` becomes `True`, reset:
  - `warmup_cycle_index = 0`
  - `warmup_completed_cycles = 0`

This ensures warmup restarts cleanly when re-enabled manually.

### `raidbot/desktop/worker.py`

- increment `warmup_completed_cycles` only after successful third-step real action
- graduate profile after cycle `20`
- persist the updated profile config immediately
- keep failures from advancing counters
- keep per-profile automation failures local instead of pausing the whole queue
- reserve queue-level stop/block only for genuine global blockers

### `raidbot/desktop/main_window.py`

- add a display override so top status reads:
  - `Paused` in orange for user pause
  - `Stopped` in red for true global queue block
- add profile-card overlays:
  - orange while user-paused
  - red while globally stopped
- add a warmup progress bar on warmup profile cards
- restore the real runtime state and profile colors after pause clears

## Testing

Add or update tests for:

- config/storage round-trip of `warmup_completed_cycles`
- 20th full warmup cycle graduates the profile out of warmup
- graduation enables `reply/like/repost` and disables `bookmark`
- failed warmup real action does not advance completed-cycle count
- re-enabling warmup resets both counters to `0`
- warmup profile card progress bar reflects completed cycles out of `20`
- user pause renders orange `Paused` state in the top panel and profile cards
- true global queue block renders red `Stopped` state in the top panel and profile cards
- clearing user pause restores `Running` and the underlying profile colors
- one profile failure does not pause the whole queue or block later raids

## Versioning

Per project rule, this change must end with a version bump after implementation.
