# Slot 1 Presets Design

## Summary

Extend bot action slot 1 (`R`) with a slot-specific preset dialog.

Slot 1 keeps its existing main capture on the Bot Actions page. That main capture remains the image used to start the slot-1 action.

A new `Presets` button on slot 1 opens a modal where the user can manage a pool of presets. Each preset contains text plus an optional image. The modal also owns one shared finish-image capture for slot 1.

At runtime, slot 1 becomes a multi-step action:

1. find the main slot-1 image
2. move mouse to it
3. wait `0.5s`
4. click
5. wait `0.5s`
6. choose one random preset
7. paste the preset text
8. if the preset has an image, copy and paste that image
9. find the shared slot-1 finish image
10. move mouse to it
11. wait `0.5s`
12. click
13. confirm UI changed

Slots 2, 3, and 4 keep their current behavior.

## Goals

- Keep the Bot Actions tab simple for normal use.
- Make slot 1 capable of writing randomized text and optionally pasting an image before finishing.
- Preserve the existing fixed 4-slot model.
- Keep the slot-1 preset setup local to slot 1 rather than reintroducing a generic sequence editor.

## Non-Goals

- Do not generalize presets to slots 2, 3, or 4.
- Do not bring back the old generic automation UI.
- Do not add advanced preset logic such as weights, tags, or conditional routing.
- Do not change the current dedicated-raid-window bot flow outside of slot 1 behavior.

## UI

## Bot Actions Page

Only slot 1 gets a new `Presets` button.

Slot 1 main page controls become:

- enable checkbox
- thumbnail for the main slot-1 capture
- `Capture`
- `Test`
- `Presets`
- path/status text

Slots 2, 3, and 4 remain unchanged.

## Slot 1 Preset Modal

The modal contains:

- preset list
- `Add preset`
- `Remove preset`
- `Save`
- per-preset text editor
- per-preset optional image upload
- one shared `Capture finish image` control
- shared finish-image preview/status
- selected preset image preview/status

The shared finish image belongs to slot 1 as a whole, not to individual presets.

## Data Model

Slot 1 needs extra persisted data beyond the current `BotActionSlotConfig` fields.

Recommended additions:

- `BotActionPreset`
  - `id`
  - `text`
  - `image_path: Path | None`

- slot-1-specific fields on `BotActionSlotConfig`
  - `presets: tuple[BotActionPreset, ...]`
  - `finish_template_path: Path | None`

For slots 2, 3, and 4:

- `presets` stays empty
- `finish_template_path` stays `None`

This keeps the existing fixed slot layout intact while letting slot 1 carry the extra information it needs.

## Runtime Behavior

## Normal Bot Run

If slot 1 is enabled:

- the bot must first validate the main slot-1 capture exists
- the bot must then validate whether presets exist
- if no presets exist:
  - emit a clear user-visible warning
  - skip slot 1
  - continue with later enabled slots
- if a preset is chosen and it has no optional image:
  - skip only the image paste portion
- if the shared finish image is missing:
  - slot 1 fails like a normal action failure
  - leave the raid window open
  - pause the bot

Preset selection is uniform random from the currently saved slot-1 preset list.

## Slot 1 Test

`Test` for slot 1 should use the same slot-1 runtime behavior, not a simplified click-only behavior.

That means slot-1 testing should also:

- start from the main slot-1 capture
- choose a random preset
- paste its text
- optionally paste its image
- finish using the shared finish image

This keeps test behavior aligned with real bot behavior.

## Clipboard/Image Handling

For a chosen preset image:

- load the image from disk
- copy it to the clipboard
- paste it into the active Chrome window

If a preset image path exists in config but the file is missing at runtime:

- treat that preset image as unavailable
- do not fail the whole slot for that alone
- continue as if the preset had no optional image

Only the shared finish image is required for successful slot-1 completion.

## Persistence

Desktop config storage must round-trip:

- slot-1 presets
- preset text
- preset optional image paths
- slot-1 shared finish image path

Older configs without this data must still load successfully, defaulting to:

- no presets
- no shared finish image

## Error Handling

User-facing slot-1 messages should cover:

- no presets configured
- preset text/image handling failures
- finish image missing
- finish image not found on screen
- UI did not change

Important rule:

- `no presets configured` is a skip reason, not a hard stop
- `missing shared finish image` is a failure reason

## Testing

Add tests for:

- slot-1 `Presets` button presence and signal wiring
- slot-1 preset modal add/remove/save behavior
- persistence round-trip for preset data and shared finish image
- slot-1 sequence/runtime building with preset-aware behavior
- slot 1 skips when enabled but has no presets
- slot 1 uses random preset selection from saved presets
- slot 1 pastes text
- slot 1 optionally pastes preset image
- slot 1 uses shared finish image to complete
- slots 2, 3, and 4 remain unchanged

## Recommended Implementation Boundaries

- `models.py`
  - add preset model and slot-1 persisted fields
- `storage.py`
  - persist and load preset data
- `bot_actions/page.py`
  - add `Presets` button to slot 1
- new slot-1 preset modal module
  - keep modal logic isolated from the main page
- `bot_actions/sequence.py`
  - represent slot-1 special runtime path cleanly
- automation runtime / runner path
  - execute the slot-1 special action without affecting other slots
- `controller.py` and `main_window.py`
  - wire modal save/capture actions into config and status feedback

## Recommended UX Rule

Keep this feature visibly scoped:

- only slot 1 shows `Presets`
- do not expose preset concepts elsewhere unless later required

That preserves the simple 4-box mental model while giving slot 1 the extra behavior you actually need.
