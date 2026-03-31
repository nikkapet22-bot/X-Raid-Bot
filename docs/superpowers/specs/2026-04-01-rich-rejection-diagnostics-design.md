# Rich Rejection Diagnostics Design

## Goal

Make rejected raid posts explain *why* they were rejected, so sender and parsing problems can be diagnosed from normal app activity without guesswork.

## Current Problem

The current detection path collapses too much information:

- `sender_rejected` does not tell us which incoming sender ID actually arrived
- `not_a_raid` does not tell us whether the post failed because of:
  - missing video
  - missing status URL
  - missing action markers

This makes debugging new bots such as `@RallyGuard_Raid_Bot` ambiguous even when save/allowlist persistence is working.

## Decision

Keep the same detection kinds, but enrich the reason text at the source.

- `sender_rejected`
  - still returns `kind="sender_rejected"`
  - reason includes the actual incoming `sender_id`

- `not_a_raid`
  - still returns `kind="not_a_raid"`
  - reason distinguishes the exact failure cause:
    - `missing_video`
    - `missing_status_url`
    - `missing_action_markers`

## Scope

In scope:

- richer rejection reasons from the service/parser layer
- preserving those reasons in desktop activity/state
- focused tests for the new reason strings

Out of scope:

- changing allowlist behavior
- changing raid matching rules
- broadening media detection
- UI redesign

## Implementation Notes

- `raidbot/parser.py`
  - expose enough parsing detail to distinguish:
    - no URL
    - no action markers
    - valid parsed raid

- `raidbot/service.py`
  - continue returning the same rejection kinds
  - populate specific reasons for sender rejection and non-raid rejection

- `raidbot/desktop/worker.py`
  - no behavioral change needed beyond preserving the richer reason text already passed into activity recording

The key point is to improve observability first. Once Rally Guard failures are explained precisely, any real compatibility fix can target the correct layer.

## Testing

Add focused coverage for:

- sender rejection reason includes the incoming sender ID
- non-raid rejection reason is `missing_video` when the parsed post lacks video
- non-raid rejection reason is `missing_status_url` when markers exist but no status link is present
- non-raid rejection reason is `missing_action_markers` when a status link exists but markers are absent
