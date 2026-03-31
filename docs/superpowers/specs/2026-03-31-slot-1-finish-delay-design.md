# Slot 1 Finish Delay Design

## Goal

Give beta testers a simple way to tune the slot-1 finish wait for slower machines while cleaning up the Bot Actions card header.

## Current Problem

Slot 1 uses a fixed post-finish delay of `2.0s` after clicking the finish image. On slower PCs or networks, the post can take longer to register, so closing too early risks interrupting the completed action.

The current Bot Actions cards also still show `Slot 1/2/3/4` text, which is no longer adding useful information and wastes space in the header row.

## Decision

Keep the setting narrow and explicit:

- Remove the visible `Slot 1`, `Slot 2`, `Slot 3`, and `Slot 4` text from all action cards
- Add a compact `Finish Delay` numeric field only on the slot 1 card, in the top-right where `Slot 1` used to be
- Store the value as integer seconds
- Default to `2`
- Apply it only to slot 1 finish-image completion handling

Slots 2/3/4 remain unchanged and do not get their own delay fields.

## Scope

In scope:

- Bot Actions header cleanup by removing visible slot labels
- Adding a slot-1-only `Finish Delay` input
- Persisting the new value in desktop config
- Using the configured value in the slot-1 finish wait path
- Focused tests for UI, config persistence, and runner behavior

Out of scope:

- Per-profile or per-slot delay tuning beyond slot 1
- Slider UI
- Changing the behavior of slots 2/3/4
- Changing any unrelated Bot Actions layout or automation timings

## Implementation Notes

- Add `slot_1_finish_delay_seconds` to `DesktopAppConfig`
- Save/load it in `DesktopStorage`, defaulting older configs to `2`
- Update `raidbot/desktop/bot_actions/page.py` so slot 1 exposes a compact integer field labeled `Finish Delay`
- Emit a dedicated change signal from the Bot Actions page and persist it through `DesktopController`
- Replace the hardcoded slot-1 finish wait in `raidbot/desktop/automation/runner.py` with the configured value

Validation rules:

- Integer only
- Minimum `0`
- Maximum `10`

## Testing

Add focused coverage for:

- Config default/load/save of `slot_1_finish_delay_seconds`
- Bot Actions page showing `Finish Delay` only on slot 1
- Visible slot labels removed from all action cards
- Runner using the configured slot-1 finish delay instead of the old hardcoded `2.0s`
