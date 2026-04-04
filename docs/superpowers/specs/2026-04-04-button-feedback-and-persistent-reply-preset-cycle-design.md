# Button Feedback And Persistent Reply Preset Cycle Design

**Date:** 2026-04-04

## Goal

Improve button interaction feedback across the desktop app and make slot 1 reply presets rotate without repetition until the whole preset pool is exhausted, even across different raids and app restarts.

## Decisions

- Keep the current visual language; do not redesign the theme.
- Make every custom button family define clear `hover` and `pressed` feedback.
- Use the existing global `QPushButton` styling as the fallback for standard buttons.
- Persist slot 1 preset-cycle state in desktop app state, not in a new side file.
- Slot 1 presets must not repeat until every configured preset has been used once.
- Preset-cycle state must survive app restarts.
- If presets are added or removed, stale preset ids are dropped automatically during load/use.

## UI Changes

### Buttons

Audit and complete the button selectors that override the base `QPushButton` behavior so they all react visibly on mouseover and click.

Likely families to tighten:

- `QPushButton#shellTabButton`
- `QPushButton[variant="quiet"]`
- icon-only custom button selectors already defined in the theme

Normal buttons that already inherit the base `QPushButton`, `primary`, `secondary`, `danger`, and bot-action selectors should continue to work through the shared stylesheet.

## Preset Rotation Behavior

Current behavior only avoids slot 1 preset reuse inside a single active raid run. The chooser is recreated on the next raid, so repetition across raids is expected.

New behavior:

1. Slot 1 chooses from presets whose ids have not yet been used in the current cycle.
2. Each chosen preset id is recorded in persisted desktop state immediately.
3. When all currently configured preset ids have been used, the cycle resets.
4. The next raid starts a new full-cycle rotation.

This makes preset selection durable across:

- different raids
- `Raid NOW!`
- auto-run queue execution
- app restarts

## Persistence

Add a small state field for slot 1 preset-cycle memory, for example a tuple/list of used preset ids for the current cycle.

Normalization rules:

- keep only ids that still exist in the current slot 1 preset list
- if slot 1 has zero or one preset, the state remains harmless and simple
- if the used-id set fully covers the current preset pool, clear it before the next selection

This belongs in desktop state rather than config because it is runtime rotation history, not user-authored configuration.

## Implementation Shape

- `raidbot/desktop/theme.py`
  - add missing `:hover` and `:pressed` states for the custom button families

- `raidbot/desktop/models.py`
  - extend desktop state with slot 1 preset-cycle tracking

- `raidbot/desktop/storage.py`
  - save/load the new state field
  - normalize stale preset ids on load

- `raidbot/desktop/bot_actions/sequence.py`
  - let the slot 1 chooser work from a provided used-id set
  - return the updated used-id state after selection

- `raidbot/desktop/worker.py`
  - use the persisted preset-cycle state when building slot 1 sequences
  - persist the updated used-id state after each selected preset

## Failure Handling

- If slot 1 has no presets, existing `no_presets_configured` behavior remains unchanged.
- If persisted used ids contain removed presets, they are silently dropped.
- If the used-id state is missing, invalid, or empty, selection starts a fresh cycle.

## Testing

Add coverage for:

- custom button selectors that were missing explicit `pressed` or `hover` feedback
- slot 1 preset rotation across separate raids without reuse until pool exhaustion
- persisted preset-cycle state surviving storage round-trip
- stale preset ids being discarded cleanly
- cycle reset after the full preset pool is exhausted
