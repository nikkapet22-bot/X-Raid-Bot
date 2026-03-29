# 2026-03-29 Page Ready Capture Design

## Summary

Add one shared `Page Ready` capture to the Bot Actions tab. When configured, the bot should wait until that image appears in the freshly opened raid Chrome window before it starts searching the fixed action slots `[R][L][R][B]`.

## Goals

- Replace the current blind "wait and hope" startup behavior with a real visual readiness signal.
- Keep the existing slot workflow intact after the readiness gate passes.
- Let different users tune readiness with a capture from their own page layout instead of hardcoding a single fixed delay.

## Non-Goals

- Do not replace the existing per-slot captures.
- Do not remove the existing settle delay; it still runs first.
- Do not make page ready profile-specific. All raid profiles use the same shared page-ready image.
- Do not add a second generic automation system.

## UX

The Bot Actions tab gets a new shared `Page Ready` section above the four slot boxes.

It should include:

- thumbnail preview
- `Capture` button
- path/status text

The layout should match the existing slot capture style so it feels like part of the same system.

## Runtime Behavior

For each profile raid attempt:

1. open the raid link in a fresh Chrome window for that profile
2. wait the existing settle delay
3. if `Page Ready` is configured:
   - search for the page-ready image in the opened raid window
   - only continue once it is found
4. start the normal bot-action slot search and click flow

If `Page Ready` is not configured, keep the current behavior.

## Failure Behavior

If `Page Ready` is configured but never appears:

- fail that profile with reason `page_ready_not_found`
- leave that profile window open
- mark that profile red on the dashboard
- continue with the remaining healthy profiles

This follows the current multi-profile failure model.

## Data Model

Add one shared path to desktop config for the page-ready template image.

The path should:

- persist in config storage
- update the Bot Actions UI preview after capture
- be shared across all raid profiles

## Implementation Shape

- extend desktop config/storage with `page_ready_template_path`
- extend Bot Actions UI with a shared page-ready capture surface
- add controller wiring for capturing and saving the page-ready image
- add worker/runtime logic to wait for the page-ready image before building/running the slot sequence
- reuse the existing automation matcher instead of inventing a separate page-ready detection path

## Testing

Add coverage for:

- config/storage round-trip for the page-ready template path
- Bot Actions page rendering the page-ready capture controls
- capture/save wiring from UI to controller config
- worker waiting for page-ready image before running bot actions
- worker reporting `page_ready_not_found` when the shared image never appears
- worker falling back to current behavior when no page-ready image is configured

## Notes

This feature is meant to reduce wasted time from large blind waits like the current `8s` first-slot search window. It does not need to solve every timing issue by itself, but it should give the bot a much better start condition before slot searching begins.
