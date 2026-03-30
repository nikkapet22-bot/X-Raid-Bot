# Video-Aware Raid Detection And Per-Profile Dashboard Metrics

## Goal

Fix two related problems in the current app:

1. Some posts from supported raid bots contain a parsable X link but are not real raid posts. In practice, the real raid posts consistently include video media.
2. Dashboard metrics currently collapse successful raids by URL, which undercounts multi-profile success and inflates completion time.

The desired behavior is:

- a Telegram message only becomes a detected raid if it contains both:
  - a valid parsable raid link
  - video media on the message
- dashboard metrics count successful profile raids, not just unique URLs

## Scope

This change covers:

- Telegram message ingestion
- raid detection
- persisted desktop activity entries
- dashboard metric derivation and charting

This change does not alter:

- bot action runtime behavior
- sequence order
- profile execution order
- replay-on-restart behavior

## Detection Model

### Current Problem

`RaidService.handle_message()` only inspects `message.text`. If the parser finds a valid X link, the message is treated as a raid even when the Telegram post itself is malformed or effectively empty.

### New Rule

A message should be treated as a real raid only when:

- chat is whitelisted
- sender is allowed
- raid text parser finds a valid raid link
- the Telegram message includes video media

If the parser finds a valid link but the message has no video, the result should be:

- `RaidDetectionResult(kind="not_a_raid")`

This should apply uniformly to the supported raid bots, based on the observed invariant that real raid posts include video.

## Telegram Message Model

### Current Problem

`IncomingMessage` currently carries:

- `chat_id`
- `sender_id`
- `text`

This does not preserve any media information from Telethon events.

### New Model

Extend `IncomingMessage` with:

- `has_video: bool`

`telegram_client.event_to_incoming_message()` should populate this from the Telethon event by inspecting the message media and marking whether the message contains video media.

This keeps the video rule explicit at the message-ingestion boundary instead of trying to infer it from text.

## Activity Identity For Metrics

### Current Problem

`ActivityEntry` currently stores:

- `timestamp`
- `action`
- `url`
- `reason`

The dashboard metric code is therefore forced to group by URL only. In a multi-profile run, four successful profiles on the same raid URL collapse into one completion.

### New Model

Extend `ActivityEntry` with:

- `profile_directory: str | None = None`

The worker should populate `profile_directory` for per-profile automation activity:

- `automation_started`
- `automation_succeeded`
- `automation_failed`
- `session_closed`

Older persisted activity rows that do not contain `profile_directory` must still load safely as `None`.

## Dashboard Metric Semantics

### AVG RAIDS PER HOUR

Current behavior undercounts because it uses unique completed URLs.

New behavior:

- count each successful profile raid as one completion
- use successful profile runs from the rolling last 24 hours
- display the average per hour over that window

Example:

- 5 detected raid links in one hour
- 4 profiles successfully complete each one
- result should be `20.0/hr`

### AVG RAID COMPLETION TIME

Current behavior measures coarse URL-level timing, which overstates completion time in multi-profile runs.

New behavior:

- measure each successful profile run individually
- pair:
  - `automation_started`
  - with the matching `automation_succeeded`
- matching key is:
  - `(url, profile_directory)`
- compute duration as:
  - `success.timestamp - start.timestamp`
- average only completed runs

Example:

- profile A completes in 3s
- profile B completes in 3s
- profile C completes in 3s
- profile D completes in 3s
- average should be `3s`

### Raid Activity Chart

Current behavior undercounts because it plots unique completed URLs.

New behavior:

- plot successful profile runs per hour over the last 24 hours
- each successful profile completion contributes one unit to the hour bucket

### Success Rate

No semantic change is required for the top-level whole-raid success-rate card unless implementation naturally reuses the new run data. The current whole-raid success-rate definition may remain as long as it continues to reflect completed vs failed whole raid links.

## Storage Compatibility

Existing saved state must continue to load without migration errors.

Rules:

- `ActivityEntry.profile_directory` is optional
- missing value in older state files loads as `None`
- newly written activity rows include `profile_directory` only when available

No destructive migration is required.

## Error Handling

### Message Detection

- if a message has a valid link but no video:
  - return `not_a_raid`
- if the parser still fails:
  - existing `not_a_raid` path remains unchanged

### Metrics

- incomplete per-profile runs must not contribute to average completion time
- runs with missing `profile_directory` must not be incorrectly paired across profiles
- if there are no completed runs in the last 24 hours:
  - `AVG RAID COMPLETION TIME` remains `0s`
  - `AVG RAIDS PER HOUR` remains `0.0/hr`
  - chart remains empty

## Testing

Add or update tests for:

- Telegram event mapping marks `has_video=True` for video posts
- raid service rejects parsed-link posts without video
- raid service still detects video raid posts normally
- desktop storage round-trips activity entries with and without `profile_directory`
- dashboard metrics count multi-profile successful runs individually
- dashboard average completion time is derived from per-profile completed runs only
- raid activity chart buckets successful profile runs per hour

## Success Criteria

This work is successful when:

- malformed/empty raid posts that lack video no longer trigger automation
- multi-profile raid success is reflected accurately in `AVG RAIDS PER HOUR`
- `AVG RAID COMPLETION TIME` reflects individual successful profile duration
- the raid activity chart reflects successful profile runs, not collapsed URLs
- old saved state still loads cleanly
