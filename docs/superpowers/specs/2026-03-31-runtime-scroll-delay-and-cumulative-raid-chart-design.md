# Runtime Scroll Delay And Cumulative Raid Activity Chart

## Goal

Fix two issues in the current app:

1. Bot-action runtime waits too long before scrolling when a required slot is below the fold.
2. The `Raid Activity` chart is visually weak and currently shows raw hourly counts instead of a cumulative trend.

The desired behavior is:

- normal runtime slot search should wait about 2 seconds before scrolling instead of 8 seconds
- the chart should show cumulative successful profile raids over the last 24 hours with a more premium line/fill treatment

## Scope

This change covers:

- bot-action runtime search timing
- dashboard raid activity chart semantics
- dashboard chart rendering

This change does not cover:

- slot test search timing
- page-ready logic
- storage format
- activity event semantics

## Runtime Timing

### Current Problem

All normal bot-action runtime steps currently use:

- `max_search_seconds = 8.0`

That means the bot waits about 8 seconds before the first scroll attempt for any enabled slot that is not visible.

This causes two bad behaviors:

1. When the link opens and no slot is visible, the bot sits idle too long before scrolling.
2. When slots `2/3/4` are visible and execute, but `slot 1` is below the fold, `slot 1` still waits too long before scrolling.

### New Rule

Change normal runtime bot-action slot search to:

- `BOT_ACTION_STEP_SEARCH_SECONDS = 2.0`

Keep:

- `SLOT_TEST_STEP_SEARCH_SECONDS = 1.0`
- `BOT_ACTION_SLOT_SCROLL_ATTEMPTS = 4`

This should apply uniformly to all enabled runtime slots.

## Raid Activity Chart Semantics

### Current Problem

The chart currently shows per-hour successful profile raid counts. The user wants a cumulative trend line instead.

### New Rule

The chart should:

1. bucket successful profile raid completions by hour across the last 24 hours
2. convert those hourly buckets into a cumulative running total from left to right
3. render the cumulative series

Meaning:

- left side starts near the oldest 24h total
- right side ends at the total successful profile raids in the rolling last 24 hours

The underlying signal remains:

- successful profile raids

## Chart Visual Direction

The current chart looks too utilitarian. The goal is a more premium visual feel, closer to a Polymarket PnL graph.

Rendering changes should include:

- cleaner, stronger stroke
- more polished filled area under the line
- reduced harshness in the grid/background feel
- keep the current dark theme and panel footprint

This should remain a lightweight custom widget change, not a chart-library replacement.

## Testing

Add or update tests for:

- bot-action runtime sequence uses `2.0s` search windows
- slot test sequence still uses `1.0s`
- raid activity series builder returns cumulative values
- chart-related dashboard tests continue to use successful profile raid data

## Success Criteria

This work is successful when:

- hidden runtime slots scroll after about 2 seconds instead of 8
- slot tests keep their current faster behavior
- `Raid Activity` shows a cumulative trend over the last 24 hours
- the chart looks materially more polished than the current thin utilitarian graph
