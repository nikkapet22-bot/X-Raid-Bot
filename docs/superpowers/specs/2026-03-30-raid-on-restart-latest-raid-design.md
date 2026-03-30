# Raid On Restart Latest-Raid Design

Date: 2026-03-30

## Summary

Add a per-profile `Raid on Restart` toggle to the dashboard profile cards.

When a profile is red and the user presses `Restart`:

- if `Raid on Restart` is `off`, restart behaves exactly like today:
  - clear the red state
  - make the profile eligible for future raids
- if `Raid on Restart` is `on`, the profile also participates in a replay of only the most recent replayable raid link

This replay state is in-memory only. If the app closes, it is forgotten.

## Goals

- Let failed profiles catch up on the latest missed raid without waiting for a new Telegram link
- Keep replay behavior narrow and predictable
- Avoid turning restart into a backlog or queue replay system
- Keep profile recovery operationally simple for the user

## Non-Goals

- No replay of older missed raids
- No persistent replay history across app restarts
- No global replay toggle
- No replay queue UI

## User Experience

Each dashboard profile card gets:

- existing `Restart` button
- new `Raid on Restart` on/off toggle

Placement:

- bottom-right area of the profile card

Behavior:

- toggle is per profile
- default is `off`
- it is persisted with the rest of the raid profile configuration

## Runtime Model

The worker keeps one in-memory latest replayable raid record:

- latest raid URL
- profiles that already succeeded on that raid
- profiles that failed on that raid

This replay record is updated during the normal multi-profile raid run.

When a raid runs:

- profiles that succeed are marked as succeeded for that latest raid
- profiles that fail are marked as missed for that latest raid

When the app exits:

- this replay record is discarded

## Restart Behavior

When the user presses `Restart` on a red profile:

1. clear the profile’s red state and last error
2. if `Raid on Restart` is `off`, stop there
3. if `Raid on Restart` is `on`, check whether a latest replayable raid exists
4. if none exists, stop there with normal green recovery behavior
5. if one exists, schedule a replay pass for that one latest raid

Replay pass rules:

- replay only the most recent raid URL
- run profiles one by one in configured profile order
- only run restarted profiles that:
  - are now green
  - have `Raid on Restart` enabled
  - did not already succeed on that latest raid
- skip profiles still red
- skip profiles that already completed that latest raid
- if one replayed profile fails again, continue to the next eligible restarted profile

## Data Changes

Persisted profile config change:

- add `raid_on_restart: bool = False` to each raid profile config

Persisted storage impact:

- save/load the new per-profile boolean

In-memory only worker state:

- latest replayable raid URL
- set of successful profile directories for that raid
- set of failed profile directories for that raid

## Edge Cases

If only one profile succeeded and all others failed:

- the raid still counts as completed
- replay applies only to restarted opted-in failed profiles

If the user restarts multiple failed profiles:

- replay runs them one by one in configured order

If a restarted profile fails again:

- it turns red again
- replay continues to the next eligible restarted profile

If the user restarts a profile after a newer raid has happened:

- replay uses only the newest replayable raid
- older missed raids are not replayed

If there is no replayable latest raid:

- `Restart` behaves like a plain health reset

If the app restarts:

- replay memory is cleared
- only the persisted `Raid on Restart` toggle remains

## Implementation Shape

### Models and storage

- extend raid profile config with `raid_on_restart`
- update config serialization/deserialization

### Dashboard UI

- add a compact per-profile `Raid on Restart` toggle
- place it in the lower-right area of the profile card
- keep `Restart` behavior and layout intact

### Worker logic

- maintain one in-memory latest replayable raid record
- update it during normal multi-profile execution
- extend profile restart flow to optionally schedule replay

### Replay execution

- replay only the latest raid
- reuse the existing per-profile raid execution path
- run replayed profiles in configured order
- continue on per-profile replay failure

## Testing

Add or update tests for:

- profile config save/load of `raid_on_restart`
- dashboard profile cards exposing the toggle
- restart with toggle `off` only clears red state
- restart with toggle `on` replays only the latest raid
- replay skips profiles that already succeeded that raid
- replay continues when one restarted profile fails again
- replay state is forgotten after app restart

## Acceptance Criteria

- User can turn `Raid on Restart` on/off per profile
- Restarting a red profile with toggle `on` replays only the latest raid
- Replay never creates a backlog system
- Replay runs restarted profiles in configured order
- Replay continues past a newly failing restarted profile
- Closing the app clears replay memory
