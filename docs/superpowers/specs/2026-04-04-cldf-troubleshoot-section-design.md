# CLDF Troubleshoot Section Design

## Summary

Add the first `Troubleshoot` surface to the existing Bot Actions page.

This first slice is intentionally narrow:
- add a new `Troubleshoot` section to the Bot Actions UI
- add a first troubleshoot subgroup named `CLDF`
- render 3 troubleshoot capture cards labeled `1`, `2`, and `3`
- each troubleshoot card includes:
  - preview image area
  - `Capture` button
  - `Test` button

This pass does not yet implement the automatic troubleshooting runtime path or the worker/controller logic that activates troubleshooting after `Page Ready` fails.

## Goals

- Give users a dedicated place to capture and test troubleshooting icons.
- Keep the new section visually consistent with the current Bot Actions page.
- Keep the first slice small enough to validate the UI layout before building the runtime behavior.

## Non-Goals

- Automatic entry into troubleshooting mode
- Troubleshooting execution sequence logic
- New worker recovery flow
- New persistent troubleshooting outcomes or status handling
- Additional troubleshoot groups beyond `CLDF`

## UI Design

### Placement

The Bot Actions page gains a new section named `Troubleshoot`.

For this first slice, `Troubleshoot` should sit alongside the existing Bot Actions content in a way that feels native to the page rather than like a separate mode. The exact container structure should follow the existing page’s section language (`QGroupBox`, cards, muted helper text, existing spacing tokens).

### CLDF Group

Inside `Troubleshoot`, add a subgroup titled `CLDF`.

The `CLDF` group contains 3 mini cards laid out horizontally:
- `1`
- `2`
- `3`

Each card should visually mirror the simplified shape of the existing Bot Actions slot cards:
- title at the top
- dashed preview area
- compact action button row
- muted status/path label underneath

### Card Controls

Each `CLDF` card includes only:
- `Capture`
- `Test`

Each `CLDF` card explicitly does not include:
- enabled toggle
- presets
- finish delay
- extra config fields

## Interaction Design

### Capture

When the user presses `Capture` on a `CLDF` card:
- the page emits a dedicated troubleshoot capture signal with:
  - troubleshoot group identifier: `CLDF`
  - item index: `0`, `1`, or `2`
- the card status follows the same simple immediate-feedback pattern already used by Bot Actions:
  - section status updates to indicate capture started

### Test

When the user presses `Test` on a `CLDF` card:
- the page emits a dedicated troubleshoot test signal with:
  - troubleshoot group identifier: `CLDF`
  - item index: `0`, `1`, or `2`
- the page status updates to indicate test started

### Preview

Each troubleshoot card has its own preview image area.

Preview behavior should match the existing Bot Actions capture previews:
- show image when a template path exists
- show a neutral empty state when no template exists
- load preview bytes fresh from disk so overwritten same-path captures refresh immediately

## Data Model Expectations

This first slice may use placeholder or local page-level troubleshoot structures if that keeps the change isolated.

However, the UI contract should clearly support future persistence and runtime use:
- troubleshoot group key: `cldf`
- troubleshoot item keys:
  - `cldf_1`
  - `cldf_2`
  - `cldf_3`

If new config models are introduced in implementation, they should stay minimal and scoped to troubleshooting templates only.

## Signals And Wiring

The Bot Actions page should expose new signals for troubleshoot actions, separate from the existing bot action slot signals.

Recommended signal shape:
- troubleshootCaptureRequested(group_key: str, item_index: int)
- troubleshootTestRequested(group_key: str, item_index: int)

The page should also expose setters for troubleshoot card state similar to the existing slot setters, so the main window can later sync preview/template paths cleanly.

## Testing

Add focused UI tests for:
- `Troubleshoot` section renders
- `CLDF` group renders
- 3 troubleshoot cards render in order `1`, `2`, `3`
- each card has preview + `Capture` + `Test`
- no toggle is rendered on troubleshoot cards
- no presets button is rendered on troubleshoot cards
- capture signal emits correct `CLDF` group and index
- test signal emits correct `CLDF` group and index

## Implementation Notes

- Follow the existing `BotActionsPage` styling and structure rather than introducing a new visual system.
- Reuse preview-loading helpers where possible.
- Keep this slice UI-focused so the troubleshooting runtime can be designed separately in the next step.
