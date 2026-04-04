# Settings Raid Profile Row Height Design

**Date:** 2026-04-04

## Goal

Reduce the height of the rows in Settings -> Routing -> `Raid profiles` by about one-third without changing spacing in the rest of the Settings screen.

## Decisions

- Only the `Raid profiles` list rows should change.
- Other `QListWidget` instances, including activity and any future settings lists, should keep their current sizing.
- Use stylesheet padding, not per-item custom sizing code.
- Keep the change visual-only with no behavior impact.

## UI Changes

### Raid profiles list

The `Raid profiles` list in Settings should become denser by reducing the vertical item padding.

This should affect:

- the normal row height
- the selected row height
- the hover row height

The surrounding section spacing, list border, and buttons (`Add profile`, `Remove`, `Move up`, `Move down`) should remain unchanged.

## Implementation Shape

- `raidbot/desktop/settings_page.py`
  - give `self.raid_profiles_list` a dedicated object name so it can be styled independently

- `raidbot/desktop/theme.py`
  - add a targeted selector for that object name
  - reduce the item vertical padding by about one-third relative to the default `QListWidget::item` padding

- `tests/desktop/test_app.py`
  - add a stylesheet assertion covering the new targeted selector

## Failure Handling

- If the dedicated selector is missing, the list should simply keep the current default row height.
- No data, routing, or selection behavior should change.

## Testing

Add coverage for:

- the dedicated `Raid profiles` list selector existing in the stylesheet
- the reduced row padding being defined only for that list
