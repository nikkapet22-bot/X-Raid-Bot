# Bot Actions Panel Simplification Design

Date: 2026-03-28

## Goal

Replace the current generic Automation tab with a simple bot-owned action panel that matches the real user workflow:

1. Telegram detects a supported raid link
2. Chrome opens the link
3. the bot waits for the page to settle
4. the bot searches saved action images in order
5. the bot moves the mouse, waits `0.5s`, clicks, confirms UI change, and continues

The first version should present only four fixed action slots:

- `[R]`
- `[L]`
- `[R]`
- `[B]`

Each slot can be enabled or disabled, and each slot stores one captured template image. The bot runs enabled slots from left to right after a Telegram-opened link becomes active.

## Current State

The current branch already has:

- a Telegram listener and Chrome-open flow
- an internal FIFO auto-processing path for Telegram-detected links
- a generic image-based automation subsystem
- an Automation tab with:
  - sequence list
  - step editor
  - dry run
  - manual runner
  - queue controls
  - default auto-sequence configuration

That current tab is too generic for the real use case. It feels like a separate automation product instead of part of the bot.

## Scope

This design covers:

- replacing the visible Automation tab with a fixed four-slot bot-actions UI
- capturing one template image per fixed slot
- enabling/disabling each slot with a checkbox
- automatically running enabled slots left to right after a Telegram-opened link settles
- keeping the queueing/open-link/runtime behavior bot-owned and mostly hidden
- showing simple status and failure feedback

This design does not cover:

- user-defined sequences
- dry run
- manual runner controls
- target-window picking
- generic template path editing
- generic step timing/threshold tuning in the main UI
- headless or browser-internal execution

## Product Direction

The automation feature should no longer be presented as a standalone automation tool.

The product message should be:

- configure the bot's four action boxes once
- start the bot
- when a Telegram link opens, the bot automatically performs the enabled actions in order

The user should not need to think about sequences, queue ownership, or manual runner concepts.

## User Interface

The current Automation tab should be replaced by a simplified `Bot Actions` panel.

The panel should show:

- four fixed action boxes in one row:
  - `[R]`
  - `[L]`
  - `[R]`
  - `[B]`
- one checkbox above each box
- each box clickable for capture/recapture
- a small visual state per box:
  - no image captured
  - image captured
  - enabled / disabled
- one small status area below the row:
  - bot-actions state
  - current slot
  - last error
- one small settle-delay control

The user should not see:

- sequence list
- step list
- add/remove step controls
- dry-run controls
- manual start/stop runner controls
- queue state controls
- default auto-sequence selector
- target window selector

## Fixed Slot Model

The bot-actions configuration should be a fixed ordered list of four slots:

1. slot 1 labeled `[R]`
2. slot 2 labeled `[L]`
3. slot 3 labeled `[R]`
4. slot 4 labeled `[B]`

Each slot should contain:

- `label`
- `enabled`
- `template_path | None`
- `updated_at`

The labels are presentation labels only. The runtime processes them purely as ordered image-driven click steps.

The order is fixed and cannot be edited by the user.

## Capture Flow

Clicking a slot box should start a snipping flow:

1. user clicks the slot box
2. a screenshot/snipping tool appears
3. user captures the image they want the bot to detect for that slot
4. the app automatically saves the image into the app data directory
5. the slot updates to show that an image is now captured

Rules:

- one saved image per slot
- recapturing a slot replaces the previous image for that slot
- the main UI should not expose raw path editing
- the app may show a small preview or simple captured-state indicator

Saved images should live under the app data directory in a stable bot-actions location, for example:

- `bot_actions/slot_1_r.png`
- `bot_actions/slot_2_l.png`
- `bot_actions/slot_3_r.png`
- `bot_actions/slot_4_b.png`

Exact filenames may differ, but the mapping must be deterministic and internal.

## Enabled / Disabled Rules

Checkbox rules:

- if a slot is checked, that slot participates in the bot action run
- if a slot is unchecked, it is skipped
- unchecked slots may still keep their saved image for later reuse

Validation rules:

- if a checked slot has no captured image, the bot must refuse to start bot-actions execution for Telegram-opened links
- this failure must be visible to the user
- unchecked slots without images are valid and ignored
- at least one slot must be enabled for bot-actions execution to be considered runnable
- if zero slots are enabled, the bot must refuse bot-actions execution for Telegram-opened links
- slot-runnability validation must happen before Chrome is opened for a detected link

## Runtime Flow

When the Telegram worker detects a supported raid link:

1. perform the normal detection/admission checks
2. perform bot-actions preflight validation before opening Chrome:
   - at least one slot is enabled
   - every enabled slot has a captured image
3. if preflight validation fails:
   - do not open Chrome for that detected link
   - surface the failure reason
   - stop further bot-actions processing
4. open the link in Chrome
5. wait the configured settle delay
6. force the relevant Chrome window to the foreground
7. process the four slots from left to right
8. for each enabled slot:
   - load that slot's saved image
   - search for the best match in the active opened Chrome context
   - move the mouse to the match
   - wait `0.5s`
   - left click
   - verify the UI changed
   - continue to the next enabled slot
9. if all enabled slots succeed:
   - close the opened tab
   - mark success
   - continue waiting for the next link
10. if any enabled slot fails:
   - leave the tab open
   - surface the failure reason
   - pause further bot-actions processing

The runtime should no longer depend on a user-created sequence ID or any generic sequence selection.

## Internal Queue Behavior

The bot should still keep its simple internal one-by-one processing behavior for incoming links.

Rules:

- if multiple supported bots post links close together, links are processed one by one
- only one bot-actions run may be active at a time
- this queue remains internal and is not a user-facing workflow in the simplified tab

Failure behavior should stay simple:

- if a bot-actions run fails, the current tab stays open for inspection
- further bot-actions processing stops
- pending in-memory work should not continue automatically after the failure
- recovery for the first version happens through normal bot restart flow after inspection

This keeps behavior understandable without reintroducing visible queue-management UI.

## Window Targeting

The simplified design should remove target-window choice from the visible UI.

The bot should use the Chrome context created by the Telegram-opened link itself.

First-version assumptions:

- the Telegram open path produces the Chrome tab/window context used for the run
- the bot operates on that newly opened active Chrome tab/window context
- the bot forces that Chrome surface to the foreground before image search/clicking begins
- on success, the bot closes only the newly opened active tab

The user should not need to manually choose a target window in the simplified product.

## Success Detection

Each enabled slot succeeds only if:

- its image is found
- the click is executed
- the UI visibly changes afterward

The first version should use a narrow, deterministic confirmation heuristic instead of a semantic UI understanding layer.

For the first version:

- after the click, the bot should poll the active Chrome capture for up to `2000 ms`
- the bot should try to find the same slot template again using the slot's stored template image
- the slot should count as successful if either:
  - the same template is no longer found above threshold, or
  - the best-match center for that same template moves materially away from the pre-click match location
- `moves materially` should mean more than `max(10 px, 0.25 * min(template_width, template_height))`
- if the same template remains matched in essentially the same location for the full timeout window, the slot fails with `ui_did_not_change`

This first version intentionally uses template disappearance / movement as the UI-change check. It should not introduce OCR, semantic understanding, or a generalized screenshot-diff scoring system.

If the UI does not change after the click, that slot should fail with a visible reason such as:

- `image_not_found`
- `click_failed`
- `ui_did_not_change`
- `chrome_window_not_available`
- `missing_captured_image`
- `runtime_error`

## Failure Handling

Failure behavior should be explicit and simple:

- leave the tab open
- show the failure reason in the Bot Actions panel and dashboard error area
- stop further processing

The bot should not:

- silently skip failed slots
- keep moving to later slots after a failed enabled slot
- close the tab on failure
- keep processing later queued links after a bot-actions failure

## Persistence

The desktop config should gain bot-actions settings for:

- fixed slot configuration for the four boxes
- enabled state per slot
- captured image path per slot
- settle delay

Settle-delay rules for the first version:

- the value should be stored in milliseconds
- default value should be `1500`
- UI range should be `0` to `10000`

The old generic automation sequence data may remain on disk temporarily for compatibility, but it should no longer drive the visible user flow.

The app should treat older configs without the new slot data as:

- all slots disabled by default
- no captured images present
- a valid migration state that simply requires the user to configure the new boxes

If the user cancels a capture operation for a slot:

- the existing slot image, if any, should remain unchanged
- the slot should not be cleared automatically

## Implementation Direction

The existing image matching and input runtime may still be reused internally where it fits.

But the implementation should shift the public behavior from:

- generic sequence engine with a bot integration

to:

- bot-owned fixed action chain with hidden reusable internals

The user-facing app should not expose internal engine concepts that are no longer needed.

## Testing

Implementation should cover:

- simplified tab renders exactly four fixed slots
- checked slot without a captured image fails visibly
- unchecked slot without a captured image is ignored
- capture updates the correct slot and replaces previous capture
- enabled slots execute strictly left to right
- disabled slots are skipped
- success closes the newly opened tab
- failure leaves the tab open and stops further processing
- simultaneous incoming links still process one by one until a failure occurs
- old config without bot-action slots loads safely

Regression coverage should also verify that:

- the removed sequence/runner UI is no longer shown
- the bot can still detect Telegram links and open Chrome
- dashboard/error reporting still reflects bot-actions failures

## Future Extensions

This simplification should still leave room for future improvements such as:

- more polished per-slot preview states
- better visual guidance during capture
- smarter UI-change confirmation
- browser-internal tab targeting later if needed

Those should remain future work. The first version should stay intentionally simple.
