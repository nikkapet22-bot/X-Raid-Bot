# Local Activity Timestamps And Recent Activity Reason Layout

## Goal

Fix two small but visible dashboard issues:

1. `Recent Activity` timestamps do not match the user’s PC time.
2. Some activity reasons are visibly clipped even though the row has enough space.

The desired behavior is:

- new activity timestamps should align with local PC time
- the reason text in `Recent Activity` should render fully when there is horizontal room

## Scope

This change covers:

- desktop worker activity timestamp source
- recent activity row layout

This change does not cover:

- migration of old stored timestamps
- activity filtering semantics
- metric calculations

## Timestamp Source

### Current Problem

The desktop worker defaults its `now` factory to `datetime.utcnow`, while the UI formats timestamps using local time functions. That means activity rows are written in UTC but displayed as if they were local times.

### New Rule

The desktop worker should default to:

- `datetime.now`

instead of:

- `datetime.utcnow`

This aligns newly recorded activity entries with the user’s local PC clock and the rest of the UI.

### Compatibility

No historical conversion is required. Existing saved timestamps remain as-is; the fix applies to new activity written after this change.

## Recent Activity Reason Layout

### Current Problem

The reason column is hard-limited to a narrow fixed width. That causes reasons like `window_not_focusable` to clip even when the row has free space.

### New Rule

The activity reason label should:

- stay right-aligned
- stop using the fixed `96px` width
- use its natural width instead

The URL column should remain the flexible center column, so the row still adapts to available width.

This is a layout fix, not a change to reason truncation semantics.

## Testing

Add or update tests for:

- worker default `now` source produces local naive datetimes
- recent activity row does not hard-limit the reason label width
- existing activity feed construction still does not flash the reason label as a top-level window

## Success Criteria

This work is successful when:

- new dashboard activity timestamps match the user’s local PC time
- reasons like `window_not_focusable` render fully when space is available
- the recent activity row remains stable and visually compact
