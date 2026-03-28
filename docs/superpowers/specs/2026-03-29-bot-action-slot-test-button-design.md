# Bot Action Slot Test Button Design

## Summary

Add a smaller `Capture` button and a new per-slot `Test` button to the simplified Bot Actions UI. `Test` should validate one captured slot image against Chrome using the same real step behavior as the bot: search, move mouse, wait 0.5 seconds, click, verify UI change, and report the result.

## Goals

- Let the user quickly verify whether a captured slot image is actually usable.
- Keep the Bot Actions tab simple and bot-centric.
- Reuse the current automation runtime instead of creating a second click/match implementation.

## Non-Goals

- Do not bring back the old sequence editor, runner, or window picker UI.
- Do not test the full `[R][L][R][B]` chain from the tab.
- Do not require Telegram or a freshly opened raid tab to use `Test`.

## UI Changes

Each fixed slot `[R] [L] [R] [B]` shows:

- checkbox
- thumbnail preview
- smaller `Capture` button
- new `Test` button
- existing path/status text

The thumbnail stays above the buttons.

## Test Button Behavior

When the user presses `Test` for one slot:

1. Validate that the slot has a captured image path.
2. Validate that the image file still exists.
3. Find a Chrome window automatically.
4. Build a one-step temporary automation sequence from that slot.
5. Run the step with the same real behavior as the bot:
   - find image
   - move mouse
   - wait `0.5s`
   - click
   - verify UI changed
6. Report a simple result in the Bot Actions status area.

Example status results:

- `Slot 1 (R): success`
- `Slot 1 (R): image not found`
- `Slot 1 (R): no Chrome window found`
- `Slot 1 (R): UI did not change`
- `Slot 1 (R): template missing`

## Chrome Targeting

Slot testing auto-picks the most recently focused visible Chrome window.

If no Chrome window exists:

- do not click anywhere
- fail with a clear status message

This keeps the UI simple and avoids adding a window-picker back into the tab.

## Runtime Rules

- `Test` runs one slot at a time.
- `Test` is blocked while a bot-owned action run is already active.
- `Test` does not modify saved config except for normal status updates.
- `Test` reuses the existing automation runtime, matcher, input driver, and UI-change confirmation logic.

## Implementation Shape

### Bot Actions UI

- Add `slotTestRequested`
- add a `Test` button to each `SlotBox`
- reduce the visual footprint of `Capture` so both buttons fit cleanly under the thumbnail

### Main Window

- Wire `slotTestRequested` from `BotActionsPage` into a controller method
- route result text back into the Bot Actions status area

### Controller

Add `test_bot_action_slot(slot_index: int)` that:

- validates template presence
- builds a one-step ephemeral sequence from the selected slot
- resolves a Chrome target automatically
- submits the one-step run through the existing automation runtime
- maps runtime results into simple Bot Actions status text

## Testing

Add tests for:

- per-slot `Test` button signal emission
- smaller capture/test button presence in the slot UI
- controller rejecting test when template is missing
- controller rejecting test when no Chrome window exists
- successful one-slot test routing through the automation runtime
- Bot Actions status updates for success and common failure reasons

## Risks

- If multiple Chrome windows are open, the auto-picked target may not be the one the user expected. This is accepted to keep the UI simple.
- Slot testing uses real click behavior, so failures must remain safe and explicit when Chrome or the template is unavailable.
