# 2026-03-30 Dashboard Chart And Sidebar Polish Design

## Summary

Tighten the desktop UI by rebalancing the dashboard, compressing the sidebar, simplifying Recent Activity, and normalizing labels. The primary visual addition is a compact `Raid Activity` chart beside `System Status`, showing completed whole raids per hour over the last 24 hours.

## Goals

- Use the empty right side of `System Status` for useful live telemetry.
- Remove duplicate status information from the command strip.
- Make the sidebar narrower and reduce wasted space in nav and footer cards.
- Make Recent Activity cleaner by removing low-value duplicate text and shrinking the action pills.
- Ensure live metrics show meaningful values immediately instead of `—`.
- Normalize title casing and status captions across the dashboard.

## Non-Goals

- Do not change bot runtime behavior.
- Do not add new settings, toggles, or workflow steps.
- Do not redesign the Settings or Bot Actions pages in this pass.

## Layout Changes

### System Status

- Keep the current left-side status list.
- Remove the duplicate top-right `Bot state` and `Telegram` labels that sit near `Start` / `Stop`.
- Fill the right-side empty space with a `Raid Activity` chart card.

### Raid Activity Chart

- Title: `Raid Activity`
- Subtitle: `Last 24 Hours · Per Hour`
- Plot: completed whole raids bucketed by hour across a rolling last 24 hours.
- Render as a compact dark-mode chart that fits beside `System Status`.
- If there is no activity yet, show an empty baseline chart rather than hiding the component.

### Sidebar

- Reduce sidebar width.
- Reduce dead space in nav buttons and footer metric cards.
- Keep the three nav destinations only:
  - `Dashboard`
  - `Settings`
  - `Bot Actions`
- Center nav button labels cleanly within the buttons.
- Keep the two footer cards:
  - `Success Rate`
  - `Uptime`

## Text And Caption Cleanup

Normalize labels and captions:

- `running` -> `Running`
- `connected` -> `Connected`
- `Success rate` -> `Success Rate`
- `last 24 hours` -> `Last 24 Hours`
- `since last start` -> `Uptime Since Last Start`

The command row buttons should remain:

- `Start`
- `Stop`

and their text should be visually centered.

## Recent Activity

Recent Activity should keep the current compact row structure but simplify the content:

- show only:
  - timestamp
  - colored action pill
  - URL
  - optional useful reason text
- remove the far-right raw action text entirely
- make the colored pills smaller/tighter

Filter out low-value activity noise:

- `duplicate`
- `sender_rejected`
- `chat_rejected`

## Metrics Behavior

Dashboard metric cards should continue showing:

- `AVG RAID COMPLETION TIME`
- `AVERAGE RAIDS PER HOUR`
- `Raids Completed`
- `Raids Failed`

Metric derivation rules:

- `Average Raids Per Hour`
  - use completed whole raids over the rolling last 24 hours
  - if there is not enough data, show `0.0/hr`, not `—`
- `AVG RAID COMPLETION TIME`
  - use completed whole raids that have both open and success timestamps
  - if there is not enough data, show `0s`, not `—`
- `Success Rate`
  - use recent open/completed whole-raid data immediately
  - if there is not enough data, show `0%`, not `—`

## Last Error

The dashboard `Last Error` area should be restyled to feel more deliberate and match the stronger information hierarchy already used in the Bot Actions status section. This is a visual polish change only; the underlying data source remains the same.

## Implementation Shape

### Main Window

- remove duplicate command-strip status labels
- add and populate the `Raid Activity` chart
- update title-casing/label formatting
- simplify Recent Activity rows
- adjust live metric formatting to prefer zero values over `—`

### Theme

- reduce sidebar width
- tighten nav buttons and sidebar metric cards
- tighten activity pill sizing
- style the chart container and refined `Last Error` card

### Data Preparation

- derive hourly completed-raid buckets from the existing activity list
- reuse existing recent-activity summarization paths where possible
- keep all metrics based on whole raid URLs, not per-profile attempts

## Testing

Add or update tests for:

- sidebar still rendering the three nav buttons and two footer cards
- Recent Activity hiding `duplicate`, `sender_rejected`, and `chat_rejected`
- Recent Activity rows no longer rendering the far-right raw action text
- live metric formatters returning `0%`, `0s`, and `0.0/hr` instead of `—`
- dashboard chart data builder returning hourly buckets for recent completed raids
- duplicate command-strip state labels removed

## Risks

- The chart must not overcount multi-profile raids; it should stay keyed to whole raid URLs.
- Sidebar compression must not hurt readability on smaller desktop window sizes.
- Removing the duplicate command-strip labels should not remove the only visible connection/runtime state; `System Status` remains the source of truth.
