# 2026-03-30 Dashboard And Bot Actions Cleanup Design

## Summary

Tighten the redesigned UI by stripping the dashboard down to four meaningful whole-raid metrics, rebuilding Recent Activity into a cleaner event feed, simplifying the Bot Actions page, and making failure/status information more obvious.

This is a focused follow-up to the `UI IDEAS` hybrid redesign, not a new shell redesign.

## Goals

- Remove noisy dashboard statistics that users do not care about.
- Keep only four whole-raid summary metrics.
- Make `Recent Activity` feel polished instead of like a raw log dump.
- Make the Bot Actions enabled control look like a real toggle.
- Make Bot Actions failure/status information much easier to read.
- Remove the visible Timing section from Bot Actions.

## Non-Goals

- Do not redesign the whole app shell again.
- Do not change slot runtime behavior beyond the requested pause rule when all profiles are red.
- Do not reintroduce advanced settings that normal users should not touch.

## Dashboard Metrics

The dashboard should show only these four summary cards:

- `Raids Detected`
- `Raids Opened`
- `Raids Completed`
- `Raids Failed`

### Metric Meanings

- `Detected`: a valid raid link was detected from Telegram
- `Opened`: the bot opened that raid link in Chrome
- `Completed`: at least one profile completed the raid for that link
- `Failed`: no profile completed the raid for that link

### Multi-Profile Rule

These metrics are counted at the whole-link level, not per profile.

If one raid link has mixed profile outcomes:

- if at least one profile succeeds, count it as `Completed`
- profile-specific failures stay visible on the profile cards
- do not also count that raid as `Failed`

## All-Profiles-Red Rule

If all configured raid profiles are red/skipped:

- the bot pauses
- it does not pretend to process the incoming raid

This keeps the state honest and makes the failure visible immediately.

## Recent Activity

Recent Activity should remain newest-first, but its presentation should change from plain log rows to cleaner event rows/cards.

Each activity item should clearly separate:

- timestamp
- action label
- URL
- reason/details

Visual direction:

- stronger hierarchy for the action text
- muted metadata
- cleaner spacing
- card/row container styling instead of a plain dump

This should be implemented as a nicer rendering of the existing activity data, not a new logging system.

## Bot Actions

### Remove Timing

Remove the visible `Timing` section from the Bot Actions page.

Important implementation note:

- this does not have to remove the underlying settle-delay behavior immediately
- it only removes the user-facing control from the page

### Enabled Control

Replace the plain checkbox styling with a switch/toggle style.

Behavior remains identical:

- enabled = active
- disabled = skipped

Only the visual treatment changes.

### Global Status Panel

Keep one big global status panel on the page and make it more prominent.

It should show three distinct lines/fields:

- `Latest status`
- `Current slot`
- `Last error`

This panel should be the obvious place users look when a slot test or raid action fails.

## Implementation Shape

### `raidbot/desktop/main_window.py`

- remove old metric card set
- add four smaller summary cards
- rebuild Recent Activity rendering into cleaner event rows/cards

### `raidbot/desktop/models.py` and `raidbot/desktop/worker.py`

- add or derive whole-raid summary counters
- pause the bot when all profiles are red

### `raidbot/desktop/bot_actions/page.py`

- remove visible Timing section
- restyle enabled control as a switch
- restructure global status into three separate fields

### `raidbot/desktop/theme.py`

- style smaller dashboard summary cards
- style activity rows/cards
- style switch/toggle controls
- style more obvious global status panel hierarchy

## Validation

Validation should cover:

- dashboard shows only the four desired summary metrics
- mixed-profile raids count as completed when at least one profile succeeds
- all-red profiles pause the bot
- Recent Activity still shows newest-first entries
- Bot Actions still emits capture/test/toggle signals
- Bot Actions status panel shows latest status, current slot, and last error cleanly

## Success Criteria

- the dashboard is simpler and more useful
- Recent Activity looks intentional and polished
- Bot Actions is easier to understand at a glance
- users no longer see noisy counters or a timing control they should not touch
