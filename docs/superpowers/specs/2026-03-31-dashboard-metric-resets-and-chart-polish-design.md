# Dashboard Metric Resets, Local-Time Migration, And Cumulative Chart Polish

## Goal

Polish the dashboard in three places:

1. add a small reset control to every metric card
2. fix legacy `Recent Activity` timestamps so they match local PC time
3. keep the cumulative `Raid Activity` chart, but remove the current rendering glitches and make it look smooth and premium

The desired user-visible behavior is:

- each metric card has a top-right `R`
- clicking `R` resets only that metric to `0` and it starts counting again from new events
- old activity rows stop showing past UTC-looking times
- the chart remains cumulative, rises smoothly, and no longer shows broken vertical artifacts

## Scope

This change covers:

- dashboard metric-card UI
- persisted dashboard reset state
- one-time legacy local-time migration for stored desktop activity
- cumulative chart rendering

This change does not cover:

- raid runtime behavior
- Telegram filtering
- bot-action logic
- adding reset controls to non-metric panels

## Metric Reset Model

### New Rule

Each dashboard metric card gets its own small top-right `R` button.

Clicking that button should:

- reset only that card
- immediately show `0`
- start counting again only from events after the reset

### Why This Needs Baselines

The cards do not all read from the same kind of backing data:

- `Raids Completed` and `Raids Failed` are raw counters
- `AVG RAID COMPLETION TIME`, `AVG RAIDS PER HOUR`, and `Success Rate` are derived from counters and/or activity history
- `Uptime` is derived from the current session start time

Deleting shared state would make one card reset interfere with other cards. Instead, each card needs its own reset baseline.

### Per-Card Behavior

#### `AVG RAID COMPLETION TIME`

- reset stores a timestamp baseline for this metric
- future averages only use completed successful profile runs after that reset

#### `AVG RAIDS PER HOUR`

- reset stores a timestamp baseline for this metric
- future rate only uses successful profile completions after that reset
- display still uses the existing hourly format, but starts from fresh data

#### `Raids Completed`

- reset stores the current completed count as that card's offset
- displayed value becomes `current_completed - completed_offset`

#### `Raids Failed`

- reset stores the current failed count as that card's offset
- displayed value becomes `current_failed - failed_offset`

#### `Success Rate`

- reset stores both:
  - current completed count
  - current failed count
- future success rate uses only the delta after reset

#### `Uptime`

- reset stores a new uptime baseline timestamp
- displayed uptime becomes time since that reset

### Persistence

Metric resets should survive app restart.

That means the per-card reset state must be saved in desktop state, not kept only in memory.

## Legacy Local-Time Migration

### Current Problem

New desktop activity is already recorded with local time, but older saved activity entries were written before that fix. Those older rows still appear shifted relative to the userâ€™s PC clock.

### New Rule

On load, desktop state should run a one-time migration for legacy timestamped data:

- if the saved state has not yet been migrated
- treat existing persisted activity timestamps as legacy UTC-written values
- convert them once into local naive timestamps
- convert `last_successful_raid_open_at` the same way when present
- save the migrated state back

All new activity continues to use local time as it does now.

### Safety

The migration must be guarded by a persisted marker so it runs only once.

Without a marker, repeated app launches would keep shifting already-migrated values.

## Raid Activity Chart

### Data Semantics

Keep the current cumulative meaning:

- source signal is successful profile raids over the last 24 hours
- build hourly buckets first
- convert those buckets into a running total from left to right

This means:

- the line can stay flat for long stretches
- it can rise sharply near the end if raids happened recently
- it should never dip
- the far-right value equals the total successful profile raids in the last 24 hours

### Rendering Rule

The current smoothing path is producing broken joins and stray vertical artifacts. Replace that renderer with a safer smooth path that preserves ordering and monotonic visual flow.

The chart should feel closer to a Polymarket-style PnL graph:

- smooth rising line
- clean soft fill under the line
- subtle glow
- no harsh rendering artifacts

The implementation should prioritize stable drawing over fancy interpolation tricks.

## UI Changes

### Metric Cards

Each metric card should now contain:

- title
- current value
- small top-right `R` button

The reset button should be:

- visually compact
- clearly clickable
- consistent across all six cards

### No Other Dashboard Layout Changes

This pass should not rearrange panels or change dashboard information architecture. It only augments existing metric cards and fixes the chart rendering.

## Data Model

Extend desktop persisted state with a small dashboard reset structure containing:

- per-metric reset timestamps where needed
- per-metric counter offsets where needed
- one migration marker for legacy local-time conversion

This should live in desktop state storage, not config.

## Testing

Add or update tests for:

- each metric card exposes a reset control
- clicking `R` resets only that metric to zero
- metrics start counting again after reset
- legacy activity timestamps migrate to local time only once
- `last_successful_raid_open_at` migrates consistently
- cumulative chart data remains monotonic
- chart widget accepts the cumulative series without regression

## Success Criteria

This work is successful when:

- every metric card has a visible `R`
- pressing `R` resets only that metric and it restarts from zero
- older saved activity times now align with local PC time
- the cumulative chart remains accurate but no longer renders broken vertical artifacts
- the dashboard feels cleaner and more reliable without changing raid behavior
