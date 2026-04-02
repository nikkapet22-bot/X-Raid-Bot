# Per-Profile Dashboard Counters Design

## Summary

Change the dashboard counters so `Raids Completed`, `Raids Failed`, and `Success Rate` use per-profile execution outcomes instead of whole-raid outcomes.

This keeps those cards consistent with the existing per-profile metrics already used by:

- `AVG RAIDS PER HOUR`
- `AVG RAID COMPLETION TIME`
- `Raid Activity`

Because the current persisted counters use the old whole-raid meaning, the app should reset those counters once during migration and start counting fresh under the new semantics.

## Goals

- Count a successful profile run as one completed raid.
- Count a failed profile run as one failed raid.
- Keep `Success Rate` as `completed / (completed + failed)`.
- Avoid mixing old whole-raid totals with new per-profile totals.

## Non-Goals

- Preserve old whole-raid completed/failed history in the dashboard cards.
- Change how `AVG RAID COMPLETION TIME`, `AVG RAIDS PER HOUR`, or `Raid Activity` are calculated.
- Add new UI controls or labels.

## Current Problem

The worker currently mixes two meanings:

- Per-profile success increments `raids_completed`.
- Whole-raid summary helpers also mutate `raids_completed` / `raids_failed`.

This creates inconsistent dashboard cards. For example:

- 4 profiles run one link
- 3 succeed
- 1 fails

The user expects:

- `Raids Completed = 3`
- `Raids Failed = 1`
- `Success Rate = 75%`

But the current whole-raid summary path can hide the failed profile and make the cards disagree with the rest of the dashboard.

## Design

### Runtime Counter Semantics

- Each successful profile run increments `raids_completed`.
- Each failed profile run increments `raids_failed`.
- Whole-raid summary helpers no longer mutate those two counters.

Whole-raid orchestration still decides whether the overall raid succeeded or failed for control flow, but the dashboard cards no longer use that whole-raid rollup.

### Success Rate

`Success Rate` remains:

`completed / (completed + failed)`

No formula change is needed in the UI once the underlying counters switch to per-profile meaning.

### Migration

Persisted `raids_completed` / `raids_failed` currently represent old whole-raid totals.

On first load after this change:

- reset `raids_completed` to `0`
- reset `raids_failed` to `0`
- reset related dashboard reset offsets tied to those counters
- mark the migration as completed

This gives the cards a clean fresh baseline and prevents mixed semantics.

### Example

If one raid link runs on 4 profiles:

- profile A succeeds
- profile B succeeds
- profile C succeeds
- profile D fails

Then the dashboard becomes:

- `Raids Completed += 3`
- `Raids Failed += 1`
- `Success Rate = 3 / 4 = 75%`

## Implementation Outline

- Update worker runtime accounting so profile-level outcomes own the counters.
- Stop whole-raid completion/failure helpers from mutating completed/failed totals.
- Add a one-time storage/state migration marker.
- Reset legacy whole-raid counters once during state load.
- Update worker, storage, and dashboard tests.

## Risks

- Existing users will see the three cards restart from zero after upgrading.
- Tests that assumed whole-raid counter semantics will need to be updated.

## Validation

- Worker test: per-profile failure increments `raids_failed`.
- Worker test: whole-raid success/failure summary no longer changes completed/failed.
- Storage test: migration resets counters once and marks completion.
- Main window test: cards show per-profile completed/failed totals and success rate.
