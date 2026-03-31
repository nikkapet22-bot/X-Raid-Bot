## Summary

Polish the slot 1 `Finish Delay` control in Bot Actions so it reads as part of the card header instead of a detached dark block.

## Goal

- Keep the control in the slot 1 header, top-right
- Remove the heavy dark background behind the label/control cluster
- Make the numeric value clearly legible
- Avoid changing the underlying slot-1 finish-delay behavior

## Design

### Header Layout

Slot 1 keeps the current header structure:

- status dot
- slot glyph
- enable toggle
- spacer
- `Finish Delay`
- numeric input

Slots 2/3/4 remain unchanged.

### Visual Treatment

- the finish-delay container stays transparent
- `Finish Delay` remains muted helper text
- the numeric input becomes a compact outlined field
- the value is centered and uses the normal readable text color
- the input width increases slightly so values like `2`, `3`, and `4` do not look cramped

### Non-Goals

- no layout move to a new row
- no slider
- no logic changes to slot timing
- no changes for slots 2/3/4

## Files

- `raidbot/desktop/bot_actions/page.py`
- `raidbot/desktop/theme.py`
- `tests/desktop/bot_actions/test_page.py`

## Verification

- slot 1 still exposes `Finish Delay`
- slot 1 header stays transparent
- the numeric field is present and readable
- focused Bot Actions page tests remain green
