# Slot 1 Second Finish Image Design

## Summary

Extend the existing slot-1 preset flow with one additional shared capture: `Capture finish image 2`.

This is a slot-1-only change. The user continues to configure:

- slot 1 main image on the main Bot Actions page
- presets inside the slot-1 `Presets` dialog
- shared `Capture finish image`
- new shared `Capture finish image 2`

At runtime, slot 1 will click finish image 1, wait `0.5s`, then click finish image 2 before confirming UI change.

## Goals

- Let slot 1 complete a two-stage finish flow after preset text/image paste.
- Keep the UI simple and consistent with the current slot-1 presets dialog.
- Preserve the current behavior for slots 2, 3, and 4.

## Non-Goals

- Do not generalize this into an arbitrary number of finish captures.
- Do not make finish image 2 preset-specific.
- Do not redesign the Bot Actions page or the slot-1 presets dialog.

## UI Changes

The slot-1 `Presets` dialog will contain two shared finish capture controls:

- `Capture finish image`
- `Capture finish image 2`

Both are shared for slot 1 and apply to every preset.

The dialog should show status text or preview state for both shared finish images so the user can tell whether each one has been captured.

## Data Model Changes

Slot 1 needs one additional persisted shared path:

- `finish_template_path`
- `finish_template_path_2`

This should be stored in the slot-1 config alongside the existing preset list and first finish image path.

Storage must round-trip the second finish image path correctly.

## Runtime Flow

Updated slot 1 runtime:

1. Find the main slot-1 image.
2. Move mouse to it.
3. Wait `0.5s`.
4. Click.
5. Wait `0.5s`.
6. Choose one random preset.
7. Paste preset text.
8. If the preset has an image, paste the preset image.
9. Find `finish image 1`.
10. Move mouse to it.
11. Wait `0.5s`.
12. Click.
13. Wait `0.5s`.
14. Find `finish image 2`.
15. Move mouse to it.
16. Wait `0.5s`.
17. Click.
18. Confirm UI changed.

## Failure Rules

- If slot 1 has no presets, keep the current behavior: notify the user and skip slot 1.
- If `finish image 1` is missing, fail slot 1.
- If `finish image 2` is missing, inform the user and stop slot 1.
- If `finish image 2` cannot be found on screen, fail slot 1 like a normal action failure.

There is no fallback that stops after finish image 1 only.

## Implementation Shape

The change should stay narrow:

- extend slot-1 config/model with `finish_template_path_2`
- extend storage save/load with the second finish path
- extend the slot-1 presets dialog with the second capture control
- extend main-window/controller save and capture wiring
- extend the slot-1 runner path to click finish image 1 then finish image 2

No other slot behavior should change.

## Testing

Add regression coverage for:

- storage round-trip of `finish_template_path_2`
- slot-1 presets dialog showing and updating the second finish image state
- main-window wiring for `Capture finish image 2`
- slot-1 runtime clicking finish image 1, waiting, then clicking finish image 2
- slot-1 failing when finish image 2 is missing

## Risks

- This adds one more slot-1-specific branch to the runtime, so tests need to lock the sequence down.
- If the UI between finish image 1 and finish image 2 changes slower than expected, the existing search/confirmation timings may need tuning later.
