# Mock Dashboard Preview Design

**Goal:** Add a disposable dashboard preview launcher that seeds fake raid data into a temporary app-data folder so the real desktop UI can be inspected safely before beta shipping.

**Why:** The `Raid Activity` chart and related dashboard metrics need a visual sanity check with controlled data. Using fake state in the real `%APPDATA%\RaidBot` would be risky and noisy.

## Approach

Create a small script in `scripts/` that:

- creates a temporary app-data directory
- writes a seeded `config.json` and `state.json`
- launches the real desktop app against that temp folder
- supports a few canned scenarios with different success patterns

The desktop app itself stays unchanged. This is a preview harness only.

## Scenarios

The preview launcher should support:

- `steady-4p`
  - smooth, consistent 4-profile success output
  - useful for checking whether the cumulative chart climbs cleanly
- `burst-4p`
  - flat periods with sudden heavy output bursts
  - useful for checking chart readability under spiky traffic
- `mixed-failures`
  - includes profile reds, mixed recent activity, and uneven success throughput
  - useful for checking the dashboard when activity is noisy

## Seeded State

Each scenario should seed:

- `successful_profile_runs`
  - primary source for `Raid Activity`, `AVG RAIDS PER HOUR`, and `AVG RAID COMPLETION TIME`
- `activity`
  - visible `Recent Activity` rows matching the scenario
- whole-link counters
  - `raids_completed`
  - `raids_failed`
  - `raids_detected`
  - `raids_opened`
- `raid_profile_states`
  - to show green/red profile cards where relevant

The seeded timestamps should be local-time datetimes spread across the last 24 hours.

## Safety

The preview script must not touch the user’s real app state.

- use a temp folder for `APPDATA`
- use a temp folder for `TEMP` and `TMP`
- do not write to `%APPDATA%\RaidBot`
- do not persist anything after the preview closes

## Disposable Nature

This preview tool is temporary by design.

- it exists only to validate the dashboard/chart visually before shipping
- after you and the user are satisfied, it should be deleted from the repo
- no menu item, no production feature flag, no permanent integration

## Validation

Success means:

- the script launches the real app UI with fake data
- the real app UI shows the seeded scenarios exactly
- the chart can be visually reviewed without touching real user state
- the script can be removed cleanly afterward without affecting the app
