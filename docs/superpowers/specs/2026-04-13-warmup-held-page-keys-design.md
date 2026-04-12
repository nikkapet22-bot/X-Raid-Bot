# Warmup Held Page Keys Design

## Goal

Change warmup browsing from wheel scrolling to held keyboard navigation so warmup accounts browse more naturally.

## Behavior

Warmup browse mode keeps the existing page flow:

1. Open `https://x.com`
2. Wait for `Page Ready`
3. Wait `1s`
4. Hold:
   - `PageDown` for `5s`
   - `PageUp` for `2s`
   - `PageDown` for `3s`
5. Open `https://x.com/BRICSinfo`
6. Wait for `Page Ready`
7. Wait `1s`
8. Hold:
   - `PageDown` for `4s`

## Failure Rules

- If `Page Ready` is missing on either page, the profile fails normally and goes red.
- Warmup graduation, warmup cycle counting, and the third-cycle real-action behavior stay unchanged.

## Pause / Resume

- If the user pauses during a held key segment, the key must be released immediately.
- Resume continues the remaining duration of the interrupted segment instead of restarting the whole page block.

## Implementation Shape

- Add held-key support to the desktop automation input layer for `PageDown` and `PageUp`.
- Replace warmup wheel-scroll segments with timed key-hold segments in the worker.
- Persist pause snapshots at the remaining hold-duration boundary for warmup mode.
- Update worker and input tests to cover held-key behavior and pause-safe resume.

## Non-Goals

- No change to normal raid action input behavior.
- No UI or settings changes.
