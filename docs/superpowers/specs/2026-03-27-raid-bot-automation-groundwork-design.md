# Raid Bot Automation Groundwork Design

Date: 2026-03-27

## Goal

Refactor the current raid bot so it keeps all existing Telegram raid detection behavior, adds support for both `Raidar` and `D.RaidBot`, and introduces a clean browser execution pipeline that stops just short of performing X engagement actions.

When this work is complete, the remaining implementation for another engineer or AI should be a narrow executor module that receives a prepared raid job and a ready browser session, then performs the X-side actions.

## Current State

The current project already provides:

- Telegram user-session intake through Telethon
- chat whitelist filtering
- single-sender filtering through one configured sender ID
- raid parsing for active raid posts containing an X status URL plus target markers
- in-memory dedupe while the process is running
- a desktop Qt app with first-run setup, settings, tray behavior, persistent stats, and a background worker
- a simple `ChromeOpener` that launches a Chrome profile in a new tab but does not control the browser

The current browser layer is the main architectural limit. It only launches Chrome and cannot model page readiness, browser session lifecycle, executor results, or future handoff to a controllable backend.

The current cross-layer result contract is also too narrow for the future flow. `MessageOutcome` only carries `action`, `reason`, and `normalized_url`, while desktop state persistence only knows the old counters. The groundwork must replace that with explicit detection and execution result types rather than forcing implementers to infer pipeline state from free-form strings.

## Scope

This design covers:

- support for multiple allowed sender IDs, including `@raidar` and `@delugeraidbot`
- a new raid action job model
- a structured detection and execution result model that replaces the current single-step outcome contract
- a browser session abstraction and execution pipeline
- shared preset-reply pool storage and desktop editing
- runtime result reporting, stats, and activity updates for the new pipeline
- a stable executor interface with a default no-op implementation
- migration of CLI config, desktop config, and persisted desktop state from the current single-sender model
- updates to Telegram sender candidate inference for multiple supported raid bots

This design does not cover:

- implementation of X actions such as liking, reposting, bookmarking, or replying
- generation of preset reply text
- packaging changes beyond what is needed to keep the app running after the refactor

## Architecture

The system should be reorganized into five layers:

1. `raid intake`
   - Telegram listener receives a new message.
   - service verifies chat whitelist membership.
   - service verifies sender membership in an allowed sender ID set.
   - parser extracts the X status URL and confirms the message is an active raid rather than a queue update.

2. `raid job construction`
   - a structured `RaidActionJob` is created from the parsed raid.
   - the job carries source metadata, the normalized X URL, inferred action requirements, and the shared preset-reply pool reference.

3. `browser session management`
   - a browser backend creates or acquires a dedicated raid browser session based on the configured profile.
   - the session manager loads the target X URL and can report whether navigation and page readiness succeeded.

4. `executor hook`
   - the runtime calls a stable executor interface with the prepared job and ready browser session.
   - the shipped default implementation is a no-op executor that records `executor_not_configured`.

5. `result recording`
   - worker and desktop state update stats, activity, and error information for each step of the pipeline.

This keeps Telegram intake and desktop control flow intact while isolating all future X-side work behind one explicit boundary.

## Sender Support

Single-sender filtering should be replaced everywhere with an allowlist of sender IDs.

Required changes:

- CLI `Settings` should replace `raidar_sender_id` with `allowed_sender_ids`
- desktop `DesktopAppConfig` should replace `raidar_sender_id` with `allowed_sender_ids`
- service filtering should become `message.sender_id in allowed_sender_ids`
- wizard and settings UI should allow confirming multiple raid sender IDs

Default detection logic in the desktop app should prioritize candidates whose usernames or display names strongly match:

- `raidar`
- `delugeraidbot`
- `d.raidbot`

`TelegramSetupService` candidate inference is part of scope. It should support multi-candidate ranking and multi-select serialization into `allowed_sender_ids`, rather than the current single confirmed sender flow. Exact matches should be ranked ahead of frequency-based fallbacks.

No source-specific parser branch is needed for `D.RaidBot` if its active-raid message format matches the same normalized marker contract used for `Raidar`.

## Data Model

### RaidActionRequirements

A small model should represent the requested actions for a raid job. It should contain booleans for:

- `like`
- `repost`
- `bookmark`
- `reply`

The groundwork implementation should allow these flags to be populated from configuration and parser output, even though the shipped executor will not perform the actions.

Parser normalization rules should be defined up front. The parser should accept canonical active-raid markers and normalize common synonyms as follows:

- `like`: `like`, `likes`
- `repost`: `retweet`, `retweets`, `repost`, `reposts`
- `reply`: `reply`, `replies`
- `bookmark`: `bookmark`, `bookmarks`

Canonical sample messages for both `Raidar` and `D.RaidBot` should be added to tests so the parser contract is explicit rather than implied.

### RaidActionJob

The runtime should construct a job object containing at least:

- normalized raid URL
- raw source URL if useful for diagnostics
- source chat ID
- source sender ID
- action requirements
- shared preset-reply pool identifier or embedded pool reference
- timestamps or trace identifiers needed for activity logging

This model is the handoff contract between Telegram intake and the future X executor.

### Detection And Execution Result Contracts

The groundwork should split the current single `MessageOutcome` contract into two explicit layers:

- `RaidDetectionResult`
  - returned by the intake/service layer
  - represents `chat_rejected`, `sender_rejected`, `not_a_raid`, `duplicate`, or `job_detected`
  - carries the normalized URL and the constructed `RaidActionJob` when a job is detected

- `RaidExecutionResult`
  - returned by the browser and executor pipeline
  - represents browser session start, navigation, page readiness, executor outcome, session close, cancellation, and failure states

The execution layer should return structured outcomes rather than raw exceptions. It should be possible to distinguish:

- browser session start failure
- page navigation failure
- page-ready timeout
- cancelled before executor
- executor not configured
- executor success
- executor failure
- session close failure

## Browser Layer

The current `ChromeOpener` should be replaced or wrapped by a browser abstraction that supports two modes:

- `launch-only`
  - preserves today's basic behavior
  - opens the URL in the configured dedicated raid Chrome profile
  - records that there is no executor support

- `controlled-session`
  - prepares the runtime contract needed for future browser automation
  - can launch a dedicated browser session, navigate to the raid URL, report readiness, expose the session to the executor, and close the session

The groundwork should be designed around a dedicated Chrome profile intended for raid work rather than the user's everyday browsing profile. The desktop UI should explain that this profile is reserved for the raid browser session and should already be logged into X when appropriate.

The abstraction should be narrow. The future executor should not need to know how Telegram works, how config is loaded, or how stats are persisted. It should only receive:

- the prepared job
- a ready browser session object
- the shared preset-reply pool

## Executor Contract

The new browser execution package should expose:

- a base executor interface
- a shipped no-op executor
- one place where a future executor implementation can be registered or selected

The default no-op executor should:

- accept the same inputs as a real executor
- avoid touching the page
- return a structured `executor_not_configured` result
- allow the rest of the pipeline, stats, and session-closing behavior to be exercised now

This makes the missing implementation obvious and bounded.

## Config Surface

The groundwork should update both the CLI and desktop config models so the runtime can be driven consistently.

### CLI Settings

`Settings` should gain or replace fields for:

- `allowed_sender_ids`
- dedicated raid browser profile selection
- browser backend or mode
- executor selection, defaulting to the shipped no-op executor
- shared preset-reply pool
- default action requirements used to populate `RaidActionRequirements`

Environment variable names should be updated accordingly, with a compatibility path for the old single-sender setting where reasonable.

### Desktop Config

`DesktopAppConfig` should gain or replace fields for:

- `allowed_sender_ids`
- dedicated raid browser profile selection
- browser backend or mode
- executor selection, defaulting to the shipped no-op executor
- shared preset-reply pool
- default action requirements used to populate `RaidActionRequirements`

The desktop settings page and wizard should persist these fields cleanly.

## Desktop UI And Persistence

### Wizard

The onboarding wizard should change as follows:

- `Raidar sender` step becomes `Allowed Raid Senders`
- sender discovery should support confirming more than one sender ID
- the review step should summarize the sender allowlist rather than one sender ID
- the Chrome step should be relabeled to emphasize a dedicated raid browser profile

### Settings

The settings page should change as follows:

- replace the single sender ID field with an allowlist field
- add a shared preset-reply pool editor
- add default action requirement toggles
- show the configured browser backend or mode
- keep live-apply semantics where safe, and trigger subsystem restart where required

### Config Migration

`config.json` should migrate cleanly from the old single-sender shape:

- if `raidar_sender_id` exists and `allowed_sender_ids` does not, load it as a one-element allowlist
- future saves should write only the new allowlist key
- missing new config keys should be defaulted explicitly so existing installs remain readable

### State Migration

`state.json` should preserve existing persisted values while adding new pipeline counters. Existing saved fields should remain readable, and missing new counters should default to zero.

To preserve continuity with the current dashboard:

- `duplicates_skipped`, `non_matching_skipped`, and `open_failures` should remain readable
- `raids_opened` should continue to mean "raid URL successfully handed off to a browser backend"
- new counters should be added for later pipeline stages rather than redefining old ones silently

The shared preset-reply pool should be stored in desktop config. State persistence should continue to track runtime counters and recent activity across app restarts.

## Runtime Flow

The new runtime path should behave like this:

1. Telegram message arrives
2. service checks chat whitelist
3. service checks sender allowlist
4. parser validates the message and extracts the normalized X URL
5. dedupe checks whether the normalized URL has already been handed off during the current process lifetime
6. runtime builds `RaidActionJob`
7. browser session manager opens the dedicated raid session and loads the URL
8. runtime waits for session/page-ready result
9. runtime performs a second stop/restart check immediately before executor invocation
10. runtime calls the configured executor
11. runtime records the executor outcome
12. runtime closes the browser session when appropriate
13. desktop app updates stats and activity log

If stop or restart has been requested, the worker should refuse to start new jobs and should not call the executor for late-arriving messages.

### Dedupe Timing

The current behavior dedupes only after a successful open. The new pipeline should keep the same spirit but define the transition explicitly:

- do not mark dedupe on chat rejection, sender rejection, parse rejection, browser session start failure, page-ready failure, or cancellation before executor handoff
- mark dedupe once the job has been successfully handed off to a browser backend
- in `launch-only` mode, handoff occurs when the browser launch succeeds
- in `controlled-session` mode, handoff occurs when the session reaches page-ready and passes the pre-executor cancellation check

This preserves retries when the browser session never became usable while still preventing the same raid from being executed twice after a successful handoff.

## Stats And Activity

The desktop app should gain finer-grained runtime visibility. The activity feed and counters should be able to represent at least:

- raid detected
- duplicate skipped
- sender rejected
- browser session opened
- browser session failed
- page ready
- cancelled before executor
- executor not configured
- executor succeeded
- executor failed
- session closed

Existing stats such as `raids_opened`, `duplicates_skipped`, `non_matching_skipped`, and `open_failures` should either be mapped onto the new pipeline states or expanded carefully so the dashboard remains understandable.

## Error Handling

The browser and executor boundary must fail safely:

- browser startup failures must be recorded without crashing the desktop app or daemon
- page-ready failures must close any partially opened session where possible
- executor exceptions must be caught and converted into structured failures
- session-closing failures should be logged separately from executor failures
- restart and stop requests should prevent new executor work from starting

The no-op executor should never cause the bot to crash even if the browser layer succeeds.

## Testing

The refactor should be covered by tests at the same level of discipline as the existing codebase.

Required coverage includes:

- multi-sender filtering in the service layer
- config parsing for sender allowlists and new browser/executor settings
- desktop config migration from `raidar_sender_id` to `allowed_sender_ids`
- desktop state migration for newly added pipeline counters
- shared preset-reply pool persistence
- parser normalization for the supported action marker synonyms
- canonical sample-message tests for both `Raidar` and `D.RaidBot`
- job construction from valid raid messages
- worker/runtime flow using fake browser session and fake executor implementations
- stop/restart behavior preventing late executor starts
- fallback `launch-only` behavior preserving current open-on-detect capability

Existing tests for Telegram intake, parser behavior, dedupe, desktop controller, and launcher flow should remain green.

## Handoff Boundary

After this groundwork is implemented, another engineer or AI should only need to do one focused task:

- implement a concrete executor module behind the browser execution interface

That future implementation should not need to change:

- Telegram listener behavior
- raid parser rules
- dedupe handling
- desktop storage format beyond executor-specific settings
- tray and main window lifecycle
- startup wizard structure

If those components still need major changes, the groundwork has failed its purpose.
