# Last Successful Raid Display Design

## Goal

Make `Dashboard -> System Status -> Last successful raid` readable and polished by replacing the raw ISO timestamp with a human-friendly label.

## Current Problem

The current row displays the raw stored timestamp string directly. That produces dense values like `2026-03-31T13:45:14.956912`, which are hard to scan and do not fit the rest of the dashboard styling.

## Decision

Keep the existing `System Status` layout and row structure, but format the displayed timestamp before assigning it to the label.

Display rules:

- Same day: `Today, 18:42`
- Previous day: `Yesterday, 18:42`
- Older in the current year: `Mar 29, 18:42`
- Older in a previous year: `Mar 29, 2025, 18:42`
- No successful raid yet: `No successful raid yet`

## Scope

In scope:

- Formatting the `Last successful raid` value for the dashboard
- Handling empty values safely
- Testing the display cases above

Out of scope:

- Changing the underlying stored timestamp format
- Adding secondary subtext, chips, or multi-line presentation
- Changing any other `System Status` rows

## Implementation Notes

- Add a small formatter in `raidbot/desktop/main_window.py`
- Reuse local machine time semantics already used by the desktop app
- If the stored value cannot be parsed, fall back to the original string rather than crashing the dashboard

## Testing

Add focused coverage in `tests/desktop/test_main_window.py` for:

- `Today, HH:MM`
- `Yesterday, HH:MM`
- Older this year
- Older previous year
- Empty value
- Invalid timestamp fallback
