# Auto CLDF Troubleshoot Recovery Design

## Summary

When a raid window opens and `Page Ready` does not appear within `5` seconds, the desktop bot should automatically enter a fixed `CLDF` troubleshoot path instead of failing immediately.

The troubleshoot path is recovery-only:

- it runs only after `Page Ready` times out
- it does not count as a successful raid
- if it succeeds, the current raid is abandoned and the profile is restored to `green`
- if it fails, the profile remains `red`

This design reuses the existing runtime image-match-and-click engine rather than inventing a separate troubleshoot executor.

## Goals

- Automatically recover from stalled raid windows after `Page Ready` timeout.
- Reuse the already-added `Troubleshoot -> CLDF` captures.
- Keep user-facing setup simple: no new troubleshoot settings, no per-profile troubleshoot variants.
- Preserve the current meaning of profile colors:
  - `green` = usable
  - `red` = requires user attention

## Non-Goals

- Additional troubleshoot groups beyond `CLDF`
- Partial-step tolerance
- Counting troubleshoot recovery as raid success
- New controller-driven runtime orchestration for troubleshoot mode

## Trigger Point

The trigger belongs in the worker’s raid execution path, immediately after page-ready probing:

1. open raid window
2. maximize and focus it
3. scan for `Page Ready`
4. if found, continue normal raid flow
5. if `Page Ready` times out, enter CLDF recovery

The current `Page Ready` probe timeout should be reduced from `8` seconds to `5` seconds.

## CLDF Runtime Path

The CLDF path is fixed and ordered:

1. find `CLDF 1`
2. move mouse and click
3. wait `5` seconds
4. find `CLDF 2`
5. move mouse and click
6. wait `5` seconds
7. find `CLDF 3`
8. move mouse and click
9. wait `5` seconds

Each step uses the same runtime automation primitives already used for slot matching and slot tests:

- existing Chrome target window
- image match
- mouse move / click
- bounded settle after click

Each CLDF step is a single required step. There is no skip behavior.

## Template Paths

CLDF images live at fixed paths under app data:

- `bot_actions/troubleshoot/cldf_1.png`
- `bot_actions/troubleshoot/cldf_2.png`
- `bot_actions/troubleshoot/cldf_3.png`

If any required CLDF image file is missing at runtime, that step fails immediately.

## Success Behavior

If all three CLDF steps succeed:

- close the active Chrome window
- set the profile state to:
  - `status="green"`
  - `last_error=None`
- do not increment:
  - `raids_completed`
  - success history
  - successful profile run history
- do not continue the current raid
- return to waiting for the next raid normally

This is a recovery outcome, not a raid-success outcome.

## Failure Behavior

If `CLDF 1`, `CLDF 2`, or `CLDF 3` is missing or fails:

- stop immediately at that step
- mark the profile `red`
- keep a meaningful failure reason in `last_error`
- leave the current raid failed

Examples of failure reasons:

- `troubleshoot_cldf_1_missing`
- `troubleshoot_cldf_1_not_found`
- `troubleshoot_cldf_2_not_found`
- `troubleshoot_cldf_3_not_found`
- `window_close_failed`

The important rule is that failed recovery leaves the profile unusable until the user resolves it.

## State Semantics

Page-ready timeout no longer means automatic permanent failure by itself.

Instead:

- `page_ready_not_found` triggers troubleshoot mode
- final state depends on troubleshoot outcome

Outcomes:

- page-ready timeout + CLDF success
  - profile becomes `green`
  - current raid is abandoned
- page-ready timeout + CLDF failure
  - profile becomes `red`
  - current raid fails

## Architecture

### Worker

Owns the new behavior:

- reduced `Page Ready` timeout
- CLDF path execution
- state transition after recovery success/failure

Suggested helper boundaries:

- `_wait_for_page_ready(...)`
  - now returns timeout after `5s`
- `_run_cldf_troubleshoot(...)`
  - executes the 3-step ordered recovery path
- `_run_troubleshoot_step(...)`
  - reusable single-step image-match/click helper
- troubleshoot template path helpers

### Controller / Main Window

No new runtime orchestration is required.

The existing manual `Capture` / `Test` troubleshoot UI remains unchanged and continues to exist for setup and manual validation.

Auto-troubleshoot is worker-owned runtime behavior only.

## Data Flow

Normal path:

- raid detected
- profile raid opens
- page-ready found
- normal slot execution

Recovery path:

- raid detected
- profile raid opens
- page-ready times out
- worker executes CLDF 1 -> 2 -> 3
- if all succeed:
  - close window
  - clear profile error
  - wait for next raid
- otherwise:
  - mark profile red
  - stop for that profile

## Testing

Add focused worker coverage for:

1. page-ready timeout enters CLDF recovery instead of immediate permanent failure
2. CLDF success path:
   - executes all 3 steps in order
   - closes the window
   - restores profile to green
   - does not increment raid-success counters
3. CLDF step missing:
   - fails immediately
   - leaves profile red
4. CLDF step match failure:
   - fails immediately at that step
   - leaves profile red
5. CLDF success does not continue into bot-action sequence for the current raid

## Risks

- The same image-matching robustness constraints still apply to troubleshoot captures.
- A successful CLDF recovery only restores the profile for future raids; it does not salvage the current one.
- If users capture poor troubleshoot templates, recovery will fail fast and correctly leave profiles red.

## Recommendation

Implement this as a worker-owned recovery path, not a controller-driven automation feature. The worker already owns:

- page-ready timeout handling
- profile failure/success state
- window close behavior

That keeps the logic narrow, predictable, and aligned with the current runtime architecture.
