# Dedicated Raid Window Automation Design

## Summary

Replace the current "guess which Chrome window to automate" behavior with a dedicated per-raid Chrome window flow.

For each Telegram raid:

1. Detect the raid link.
2. Open a fresh dedicated Chrome window for that raid.
3. Wait for the page to settle.
4. Run the enabled fixed bot actions in left-to-right order: `[R] [L] [R] [B]`.
5. If all actions succeed, close the whole dedicated raid window.
6. If any action fails, keep that dedicated raid window open, pause the bot, show the failure reason, and retry that same open raid window when the user resumes.

This removes the current ambiguity between multiple Chrome windows and makes the bot operate only on the Chrome surface created for the current raid.

## Goals

- Stop relying on "most recently focused Chrome window" heuristics for Telegram-triggered bot actions.
- Give each Telegram raid its own fresh dedicated Chrome window.
- Keep the bot behavior simple and deterministic.
- Preserve the current fixed `[R] [L] [R] [B]` action pipeline.
- Keep failed raid windows open for inspection and retry.

## Non-Goals

- Do not reintroduce the old generic automation sequence UI.
- Do not add tab-level Chrome introspection or internal Chrome automation.
- Do not queue new raids while the bot is paused on a failed raid.
- Do not change the current per-slot capture model.

## Desired Runtime Flow

### Success path

1. Telegram detects a supported raid message.
2. The bot opens a fresh dedicated Chrome window for that raid URL.
3. The bot waits for the configured settle delay.
4. The bot targets only that dedicated raid window.
5. The bot runs the enabled action slots from left to right.
6. If all enabled slots succeed, the bot closes the whole dedicated raid window.
7. The bot continues waiting for the next raid.

### Failure path

1. Telegram detects a supported raid message.
2. The bot opens a fresh dedicated Chrome window for that raid URL.
3. The bot waits for the configured settle delay.
4. The bot runs the enabled action slots.
5. If any slot fails:
   - keep the dedicated raid window open
   - pause the bot
   - show the concrete failure reason
   - ignore new incoming raids while paused
6. When the user resumes, the bot retries that same failed raid in that same still-open dedicated raid window.

## Dedicated Raid Window Lifecycle

- The bot does not create a dedicated raid window at startup.
- A fresh dedicated raid window is created only when a raid is actually being processed.
- Each raid gets its own fresh dedicated Chrome window.
- Successful completion closes the whole dedicated raid window.
- Failed completion leaves that dedicated raid window open for inspection and retry.

This means the bot never needs to decide between unrelated Chrome windows once a raid has started.

## Bot Action Execution

The bot continues to use the existing fixed four-slot action model:

- slot 1: `R`
- slot 2: `L`
- slot 3: `R`
- slot 4: `B`

Execution rules:

- only enabled slots run
- slots run left to right
- each enabled slot uses its saved captured image
- if a slot image is missing, treat that as configuration failure and do not run
- slot 3 keeps its current special behavior:
  - move mouse
  - wait 0.5s
  - click
  - wait 0.5s
  - click again
  - confirm UI changed

## Pause, Resume, And Admission Rules

- While the bot is actively processing one raid, normal sequential processing still applies.
- If a raid fails, the bot enters a paused state immediately.
- While paused, new incoming raids are ignored rather than queued.
- Resume retries the currently failed open raid window instead of skipping to later raids.

## Required Implementation Changes

### Chrome opening layer

- Add a dedicated "open fresh raid window" path instead of only opening a new tab in a preselected Chrome window.
- Return context that represents the opened dedicated raid window for that raid.
- Add the ability to close that whole raid window on success.

### Worker auto-run flow

- Remove the current dependency on preselecting or reacquiring a general Chrome window for Telegram-triggered runs.
- Change the auto-run processor to treat the opened dedicated raid window as the run target.
- On failure, retain the opened context so resume can retry the same window instead of starting over in a different window.

### Status and activity

The runtime should continue to expose clear status/error signals, including:

- `automation_started`
- `automation_succeeded`
- `automation_failed`
- `auto_run_paused`
- retrying the failed raid on resume

The user-visible message should make it clear that the failure belongs to the currently open dedicated raid window.

## Error Handling

Expected failures include:

- dedicated Chrome raid window could not be opened
- dedicated Chrome raid window could not be located after open
- image match not found
- invalid click target
- UI did not change after click
- dedicated raid window could not be closed on success

Failure handling rules:

- show the concrete reason
- keep the dedicated raid window open
- pause the bot
- require explicit resume

## Testing

Add or update tests for:

- opening a fresh dedicated Chrome window per raid
- running bot actions against the dedicated raid window context instead of a generic Chrome window guess
- closing the whole dedicated raid window on success
- preserving the failed dedicated raid window on failure
- ignoring new incoming raids while paused
- resuming by retrying the same failed dedicated raid window
- keeping the existing `[R] [L] [R] [B]` order and slot 3 double-click behavior intact

## Risks

- Opening a fresh dedicated window per raid changes current Chrome behavior and may expose new timing issues around first paint or window discovery.
- Window-close behavior must be scoped carefully so success closes only the dedicated raid window created for that raid.
- Retry logic must not accidentally rebind to a different Chrome window after a failure.

## Recommendation

Implement this as a dedicated-raid-window flow now, rather than continuing to patch "which Chrome window should we use?" heuristics.

It is a larger behavioral change than another timing tweak, but it is simpler, clearer, and better aligned with the way the bot is supposed to work.
