# Telegram Auto Sequence Design

Date: 2026-03-28

## Goal

Extend the desktop app so that when the Telegram worker opens a raid link in Chrome, the app can automatically queue and run one saved image-based automation sequence against that newly opened Chrome tab.

The desired first version is:

- one single default auto-run sequence
- links processed one by one in FIFO order
- a short settle delay before automation starts
- Chrome forced to the foreground before the sequence runs
- close only the newly opened tab on success
- leave the tab open on failure
- show a visible failure message and pause the queue on failure

## Current State

The project already has two relevant but separate flows:

1. `Telegram/browser flow`
   - the desktop bot worker watches Telegram
   - it detects supported raid links
   - it opens those links in Chrome
   - it records browser-pipeline stats and activity

2. `Template automation flow`
   - the desktop app has an Automation tab
   - the user can save image-based sequences
   - the user can manually run a sequence or dry-run a step
   - the sequence runner scans a Chrome window and clicks matching templates

These flows are not currently connected. A Telegram-opened link does not automatically trigger a saved sequence.

## Scope

This design covers:

- automatic queueing of successfully opened Telegram raid links
- one configured default automation sequence
- foreground Chrome execution after a short settle delay
- success/failure handling for queue progression
- Automation-tab controls for enabling and monitoring auto-run behavior

This design does not cover:

- headless execution
- browser-internal tab inspection APIs
- multiple auto-run sequences chosen by source bot or chat
- automatic recovery after a failed step without user inspection

## Architecture

The first version should keep the existing worker/controller split and add a narrow handoff seam between browser opening and template automation.

The system should be split into four responsibilities:

1. `opened raid context`
   - created when the Telegram/browsing path successfully opens a raid link
   - carries enough metadata to identify the opened work item and reacquire the Chrome window used for it

2. `auto-run queue`
   - lives in the desktop bot worker path
   - accepts opened raid contexts
   - processes one item at a time
   - pauses on failure

3. `automation execution bridge`
   - waits the configured settle delay
   - forces Chrome to foreground
   - runs the configured default sequence
   - closes only the active tab on success

4. `desktop UI/state`
   - configures the default auto-run sequence and settle delay
   - shows queue state, queue length, current URL, and failure state
   - lets the user resume or clear a paused queue

This keeps the Telegram worker in charge of ordering and pacing while reusing the existing image-based runner.

## Opened Raid Context

The browser-open path should stop being a pure fire-and-forget side effect for Telegram-triggered runs. It should return a structured `opened raid context`.

The context should contain:

- normalized URL
- raw URL
- chat ID
- sender ID
- trace ID
- open timestamp
- Chrome profile used
- enough window metadata to reacquire the Chrome window that received the opened tab

The first version does not need browser-internal tab IDs. It only needs enough context to:

- associate a queued automation run with the opened raid
- reacquire the foreground Chrome window that was just used
- close the active tab after successful completion

## Auto-Run Queue

The queue should be FIFO and single-consumer.

Behavior rules:

- every successfully opened Telegram link may enqueue one opened raid context
- only one auto-run may be active at a time
- if a new Telegram link arrives while another auto-run is active, it waits in the queue
- if two supported bots post links at nearly the same time, both links are queued and processed one by one
- if `auto_run_enabled` is `false`, successfully opened Telegram links are not admitted to the auto-run queue
- if the queue is `paused`, newly opened Telegram links are not admitted to the auto-run queue
- when admission is rejected because auto-run is disabled or paused, the app should emit a visible activity entry with the reason

Queue states:

- `idle`
- `running`
- `paused`

Runtime queue fields should include:

- queue length
- current URL
- current trace ID
- last failure reason

Queue length should mean pending items that have been admitted but not yet started. The currently active item is not counted in queue length.

## Sequence Selection

The first version should support exactly one default auto-run sequence.

Rules:

- the default auto-run sequence is configured in the Automation tab
- the setting is optional
- if auto-run is enabled but no default sequence is configured, Telegram-triggered processing should fail visibly and pause the queue
- the manual sequence editor remains available and unchanged in purpose

This avoids per-bot or per-chat routing logic in the first version.

## Execution Flow

When a supported Telegram message produces a successfully opened link:

1. create opened raid context
2. enqueue context
3. if the queue is idle, start processing immediately
4. wait the configured settle delay
5. force the relevant Chrome window to foreground
6. run the default automation sequence against the foreground Chrome window
7. if the sequence succeeds:
   - close only the active tab in the owned foreground Chrome window
   - mark the queue item completed
   - continue to the next queued item
8. if the sequence fails:
   - leave the tab open
   - emit a visible failure message
   - pause the queue

The worker should not continue auto-processing queued items after a failure until the user explicitly resumes.

Failed-item lifecycle rules:

- when a run fails, the active item becomes terminal and is removed from active processing
- the failed tab remains open for inspection
- the queue enters `paused`
- pending items remain pending
- `Resume queue` continues with the next pending item; it does not automatically retry the failed item
- `Clear queue` removes only pending items; it does not close or alter the failed tab that was left open

## Window And Tab Targeting

The first version should stay simple and explicit:

- Telegram opens the raid link as a new Chrome tab
- the automation run assumes the newly opened tab is the active tab in the Chrome window that was just used
- the system forces that Chrome window to the foreground before the sequence starts
- on success, the app closes only the active tab of that owned foreground Chrome window using tab-close input behavior

The first version should not depend on browser-debugging protocols or browser-internal tab enumeration.

This implies one important safety rule:

- if the system can no longer reacquire the intended Chrome window, it must fail visibly and pause the queue rather than guessing another target
- if the user changes tabs or otherwise breaks the assumption that the newly opened raid tab is still the active tab in that owned Chrome window, the implementation cannot prove tab identity; in that case the system should prefer failing visibly over guessing

The first version therefore guarantees only:

- exclusive ownership of the foreground Chrome window used for the auto-run
- closure of the active tab in that owned Chrome window after success

It does not guarantee browser-internal tab identity beyond that owned-window/active-tab invariant.

## Settle Delay

The queue should wait a fixed settle delay before starting the automation sequence after opening the link.

Rules:

- the settle delay is configurable in the Automation tab
- it is applied to every queued Telegram-triggered auto-run
- it exists to give Chrome and the newly opened page time to become active and visually stable before template matching begins

## Success Handling

If the sequence succeeds:

- close only the active tab in the owned foreground Chrome window
- do not close the whole Chrome window
- emit a success activity entry for the queue item
- immediately continue to the next queued link, if any

Closing the active tab is part of the success path only.

## Failure Handling

If the sequence fails for any reason:

- leave the tab open for inspection
- show a visible popup or equivalent surfaced error message with the concrete reason
- set queue state to `paused`
- do not continue to the next queued item until the user resumes

Failure reasons that should be surfaced include:

- no default auto-run sequence configured
- target Chrome window not found
- target Chrome window could not be focused
- image match not found
- invalid click target
- no UI change after click
- tab close failed
- runtime error

Failures must be visible. The system should not silently skip, auto-retry indefinitely, or close the tab on failure.

## Desktop UI

The Automation tab should gain a dedicated auto-run section with:

- `Auto-run enabled` toggle
- `Default auto sequence` selector
- `Settle delay` input
- queue state display
- queue length display
- current URL display
- `Resume queue` button
- `Clear queue` button

The existing manual controls remain:

- sequence editor
- dry run
- manual start/stop

The new section configures how Telegram-opened links feed into automation. It should not replace the manual sequence workflow.

## Desktop State And Persistence

Desktop config should gain:

- `auto_run_enabled: bool`
- `default_auto_sequence_id: str | None`
- `auto_run_settle_ms: int`

Desktop runtime state should gain:

- `automation_queue_state`
- `automation_queue_length`
- `automation_current_url`
- `automation_last_error`

Queued items themselves may remain runtime-only in the first version if persistence is not needed across app restarts.

## Threading And Ownership

The queue should be owned by the desktop bot worker/runtime side, not by the Automation tab UI.

Reasoning:

- Telegram-driven order and pacing already live in the worker path
- queue semantics are operational behavior, not just display behavior
- the worker already sees the exact moment when the link was successfully opened

The UI should observe and control the queue through controller signals, not own the queue directly.

There should be exactly one shared automation execution slot.

Interlock rules:

- Telegram-driven auto-runs and manual Automation-tab runs must be mutually exclusive
- while a Telegram-driven auto-run is active, manual `Start run` and `Dry run step` actions should be rejected or disabled
- while the queue is `paused`, manual automation actions should remain disabled until the user either resumes the queue or clears the pending queue state
- if a manual run is already active, Telegram-triggered auto-run processing should not start until the shared automation slot is idle again

## Testing

Implementation should cover:

- successful Telegram-open event enqueues one auto-run item
- two opened links are processed one by one
- success closes only the active tab and continues
- failure leaves the tab open and pauses the queue
- missing default sequence fails visibly
- explicit window reacquisition failure pauses the queue
- resume continues processing remaining queued items
- clear queue removes pending items

Tests should stay seam-based:

- fake browser opener / opened context
- fake automation runner
- fake tab closer
- fake queue timing / settle delay
- controller tests for auto-run state propagation

## Future Extensions

This design should leave room for:

- headless or browser-internal execution later
- different sequences per source bot or chat
- persisted queue state across app restarts
- smarter tab targeting than “active tab in the opened Chrome window”

Those are explicitly future work, not part of the first version.
