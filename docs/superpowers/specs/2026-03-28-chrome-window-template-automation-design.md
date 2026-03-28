# Chrome Window Template Automation Design

Date: 2026-03-28

## Goal

Add a desktop-app automation module that can watch a selected Chrome window, locate user-provided template images in live window captures, and execute a fixed ordered sequence of mouse actions against the best match for each step.

The module should work for general UI automation purposes, not only raids. The first version should target Chrome windows only, use template matching rather than semantic vision models, and integrate into the existing desktop app rather than running as a separate tool.

## Current State

The project already provides:

- a PySide6 desktop app with first-run setup, settings, tray behavior, and persistent app state
- a background worker/controller pattern for long-running bot activity
- activity logging and persistent counters in the desktop app
- Chrome profile detection and Chrome-targeted workflow assumptions in the existing app

The project does not yet provide:

- live capture of a specific application window
- image-template matching
- window-targeted mouse or scroll automation
- a persistent sequence model for ordered screen actions
- UI for managing template-driven automation steps

## Scope

This design covers:

- a Chrome-window-only automation subsystem
- ordered automation sequences made of template-driven steps
- live window capture and template matching
- mouse move, delayed click, and scroll orchestration
- desktop persistence for sequences and step settings
- desktop UI for editing, testing, and running sequences
- worker-thread execution and event reporting

This design does not cover:

- semantic computer vision or foundation-model-based recognition
- OCR-first workflows
- automation against arbitrary applications beyond Chrome in the first version
- keyboard scripting beyond what is strictly needed for future extension
- cloud execution or remote control

## Architecture

The implementation should be split into five focused areas:

1. `window targeting`
   - locate Chrome windows on the local machine
   - let the user select the intended target window
   - capture only that window's bounds
   - stop the run if the window disappears or changes unexpectedly

2. `vision`
   - load template image assets from disk
   - capture frames from the target window
   - run template matching and return ranked match candidates
   - expose only match results and confidence, not UI-specific behavior

3. `sequence runner`
   - execute steps in a fixed order
   - decide when to keep scanning, when to scroll, and when to fail
   - treat UI change after click as step success

4. `input driver`
   - move the mouse to the chosen match
   - wait 0.5 seconds before clicking
   - issue a left click
   - perform scroll actions when the runner requests them

5. `desktop integration`
   - save sequences and step settings
   - provide editing, preview, dry-run, and start/stop controls
   - show step-by-step activity and failure reasons

This keeps image recognition, control flow, and UI concerns separate enough to test independently.

## Sequence Model

Each saved sequence should contain:

- `id`
- `name`
- `target_window_rule`
- ordered `steps`

Each step should contain:

- `name`
- `template_path`
- `match_threshold`
- `max_search_seconds`
- `max_scroll_attempts`
- `scroll_amount`
- `post_click_settle_ms`
- optional `click_offset_x`
- optional `click_offset_y`

The runner should process steps strictly in order. It should not skip ahead or dynamically reorder steps based on what else appears in the window.

## Matching Rules

Template matching rules for each step:

- search only inside the currently selected Chrome window capture
- allow multiple possible matches
- choose the highest-confidence match above the configured threshold
- if no match is found, keep scanning until the step's search budget is exhausted
- if still not found, perform a scroll attempt and continue searching
- if all search and scroll attempts are exhausted, fail the run on that step

The first version should use classic template matching. This is more predictable than a generalized vision model and matches the user's requirement to provide explicit template images.

## Success Detection

After a step is clicked:

- wait the configured settle delay
- recapture the target window
- verify that the UI changed enough that the matched template is no longer present in the same way

For the first version, "UI changed" should be defined conservatively:

- the previous best match is gone, or
- its confidence falls below threshold, or
- the best match location shifts materially after the click

If the template remains in place after the settle delay, the runner should treat the step as not yet complete and continue according to the step's retry policy rather than blindly advancing.

## Scrolling Behavior

When a step's template is not visible:

- the runner should keep scanning for a short bounded period
- then issue one scroll action
- then continue scanning
- repeat until `max_scroll_attempts` is reached

Scrolling should be part of the runner policy, not the matcher. The matcher only reports what is visible; the runner decides when to scroll.

## Desktop UI

The desktop app should gain a new automation area with four parts:

1. `Sequences`
   - list saved sequences
   - create, rename, duplicate, and delete

2. `Sequence editor`
   - ordered step list
   - template preview
   - step settings for threshold, search time, scroll attempts, settle delay, and offsets

3. `Runner panel`
   - select target Chrome window
   - start
   - stop
   - dry-run current step
   - show current step, last confidence, last click position, and scroll count

4. `Activity`
   - `step_found`
   - `step_clicked`
   - `step_scrolled`
   - `step_succeeded`
   - `step_failed`
   - `run_completed`
   - `run_stopped`

Dry-run mode should highlight or report the chosen match without clicking, so the user can validate templates safely before running a real sequence.

## Persistence

Sequence definitions should be stored in the desktop app's normal local storage area alongside existing app config and state, but separated into their own schema rather than mixed into unrelated bot settings.

The persistence layer should support:

- multiple saved sequences
- stable sequence IDs
- future schema migration
- safe handling of missing template files

Template image files themselves should remain user-managed files on disk. The app should store paths, not binary blobs, in the first version.

## Runtime And Threading

The sequence runner should execute in a worker thread, not the UI thread.

The worker should emit structured events back to the UI for:

- run started
- target window acquired/lost
- step search started
- match found
- scroll attempted
- click issued
- step success
- step failure
- run completed
- run stopped

This matches the project's existing background-work pattern and keeps the app responsive.

## Failure Handling

The module should fail safely and visibly in these cases:

- target Chrome window not found
- selected window disappears during a run
- template file missing or unreadable
- no match reaches threshold
- click occurs but no UI change follows
- scrolling reaches maximum attempts without surfacing the target
- user presses stop

Each failure should identify the exact step and reason in the activity panel.

## Testing

The implementation should favor seam-based testing:

- fake frame provider for deterministic image inputs
- fake matcher outputs for runner-state tests
- fake input driver for click/scroll verification
- config/storage tests for sequence persistence
- controller tests for start/stop and event wiring

Real desktop clicking and real screen capture should be limited to smoke testing, not unit tests.

## Future Extensions

The design should leave room for:

- support for browsers other than Chrome
- confirmation templates in addition to generic UI-change detection
- optional OCR assistance
- keyboard actions
- region-of-interest matching within subareas of the window
- multiple target window profiles

Those extensions should fit by adding matcher strategies or step types rather than rewriting the runner.
