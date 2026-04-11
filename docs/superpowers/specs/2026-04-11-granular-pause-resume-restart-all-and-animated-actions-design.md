# Granular Pause Resume Restart All And Animated Actions Design

## Goal

Make pause/resume behave much closer to "pause wherever it is" in real usage, add a bulk `Restart All` control for large profile sets, and add stronger motion emphasis to the highest-priority action buttons.

This is a behavior and UX improvement pass across runtime, profile controls, and dashboard affordances.

## Current Problems

### Pause Stops Only At Coarse Boundaries

The current hotkey pause feature already stores a paused execution snapshot and resumes the interrupted run first, but it still pauses only at a limited set of worker/runtime boundaries.

That leaves a gap between user expectation and current behavior:

- the user expects pause to work regardless of where the bot currently is
- the current implementation only stops at the next available safe stop boundary
- some step internals still behave as a single chunk from the user's point of view

True mid-syscall continuation is not realistic for Windows mouse, keyboard, and clipboard operations. The right target is:

- pause before or immediately after each practical runtime action
- resume from that saved action boundary
- never restart the whole raid unless the interrupted window is gone

### Reseting Many Red Profiles Is Slow

The dashboard currently supports resetting one failed profile at a time through the per-card restart icon.

That is fine for a few profiles, but it is poor for operators with many accounts:

- if `20`, `50`, or more profiles go red
- the user has to reset them one by one
- that turns a recovery action into repetitive UI work

### Important Buttons Do Not Draw Enough Attention

The highest-value actions in the app are:

- `Start`
- `Raid NOW!`
- `Restart All`

These actions should be more prominent and alive than ordinary secondary controls. Right now they mostly rely on static styling and hover/pressed feedback.

## Desired Behavior

### Granular Pause And Resume

Pause should work at the practical action-boundary level, not only at a few high-level checkpoints.

The app should support pause checks around the major runtime actions involved in raiding:

- page-ready waits
- match-search polling loops
- move-click actions
- text paste
- image paste
- scroll steps
- page-exit click
- close-window action

This does **not** mean pausing inside the middle of an atomic Windows input or clipboard syscall. Instead:

- if pause is requested during execution
- the current action should stop before the next action begins, or immediately after the current atomic action completes
- the worker should store the exact safe resume boundary

Resume behavior:

- the interrupted run resumes first
- it resumes from the stored action boundary inside the current step
- it does not restart the entire raid unless recovery is impossible

If the interrupted window is gone by the time resume happens:

- fail that interrupted profile/run normally
- continue with queued raids afterward

### Restart All

Add a `Restart All` button at the far right of the `Dashboard -> Profiles` area.

Behavior:

- visible on the profiles dashboard all the time
- clicking it resets every profile to healthy green state
- clears profile error text/details
- same semantics as manually clicking every red profile reset button one by one

This is a bulk recovery tool for large account sets. It does not replay raids and does not modify queue contents by itself.

### Animated Important Buttons

Add stronger motion emphasis only to:

- `Start`
- `Raid NOW!`
- `Restart All`

The animation language should be intentional and limited:

- smooth hover response
- pressed pop/click response
- subtle pulse while the action is available and idle

Guardrails:

- no pulse on disabled buttons
- no pulse while the button is already in a busy state
- no animation rollout to every button in the app

The goal is attention direction, not visual noise.

## Runtime Model

### Pause Snapshot Granularity

The existing paused execution snapshot model should stay, but it needs finer resume checkpoints.

Current snapshoting already tracks interrupted execution at the profile/run level. The new design extends that down to action boundaries inside a running step.

For normal raid steps, the resume boundary should be able to distinguish between practical phases such as:

- step match found but not yet clicked
- click finished, waiting for confirmation
- preset reply text not yet pasted
- preset reply text pasted, image not yet pasted
- reply finish button not yet clicked
- reply finish clicked, submit confirmation pending
- page exit pending
- close-window pending

For warmup flows, the resume boundary should similarly distinguish:

- page open pending page-ready
- page-ready passed, settle pending
- specific scroll index within the scroll block
- second page open pending
- close pending

This is still bounded and pragmatic. It is not arbitrary instruction-by-instruction journaling.

### Queue Behavior

The existing high-level pause semantics stay intact:

- Telegram remains connected
- new raids keep queuing while paused
- resume continues the interrupted run first
- queued raids continue afterward

`Restart All` is separate from pause/resume:

- it only resets profile health state
- it does not implicitly pause, resume, or clear the queue

## UI Changes

### Profiles Dashboard

Add `Restart All` on the far right of the profiles header area.

It should visually read as a primary recovery action for operators managing many profiles.

### Animated Buttons

Implement animated behavior through widget-level animation in PySide6, not stylesheet-only animation.

Recommended motion behavior:

- hover:
  - smooth color and/or elevation feel
- press:
  - small scale pop or compression
- idle pulse:
  - slow, subtle breathing emphasis

Animation scope:

- `Start`
- `Raid NOW!`
- `Restart All`

Disabled and busy states must remain visually calm and non-pulsing.

## Component Changes

### `raidbot/desktop/automation/input.py`

Add pause-aware checkpoints around action methods used by the automation runner, especially:

- `move_click`
- `paste_text`
- `paste_image_file`
- `scroll`
- `close_active_window`

The input layer itself should remain low-level. It should expose enough structure so the runner/worker can pause before and after major actions without pretending to resume inside atomic calls.

### `raidbot/desktop/automation/runner.py`

Extend step execution so slot execution can save and restore finer-grained boundaries within a step.

This is especially important for:

- normal click/confirm steps
- slot 1 reply preset flow
- finish/retry confirmation logic

The runner should restart from the correct internal boundary instead of replaying the whole step unnecessarily.

### `raidbot/desktop/worker.py`

Extend paused execution snapshoting to store the finer-grained runner state.

Add:

- bulk profile reset entry point:
  - `reset_all_raid_profiles()`

Behavior:

- iterate all profile states
- set them healthy/green
- clear errors
- persist updated state
- emit updated stats/state events

### `raidbot/desktop/controller.py`

Add:

- `reset_all_raid_profiles()`

Wire it the same way as the existing single-profile reset path, through the worker runner.

### `raidbot/desktop/main_window.py`

Add:

- `Restart All` button in the profiles dashboard header
- signal wiring to `controller.reset_all_raid_profiles()`

Also introduce animated button widgets or a small reusable animated-button abstraction for:

- `Start`
- `Raid NOW!`
- `Restart All`

The per-profile `Raid NOW!` button should use the animated variant while still respecting:

- connected-only enabled state
- busy text state
- no pulse while disabled or busy

### `raidbot/desktop/theme.py`

Keep static theme support aligned with the animated states:

- disabled state remains clear
- hover/pressed colors stay consistent with the rest of the app
- animation should layer on top of the design rather than fight it

## Error Handling

### Pause Resume Failure

If resume cannot restore the interrupted context because the window is gone or unusable:

- fail the interrupted profile normally
- keep the real failure reason
- continue with the queue

### Restart All

`Restart All` should be resilient:

- if there are no profiles, it becomes a no-op
- if some profiles are already green, they remain healthy
- the operation should not depend on Telegram connection state

## Testing

Add or update tests for:

- pause request during a running step stores a finer-grained resumable boundary
- resume continues from the stored boundary instead of restarting the whole raid
- slot 1 preset flow resumes from the correct internal phase
- warmup scroll/page sequence resumes from the correct internal phase
- missing interrupted window on resume fails only that interrupted run
- `Restart All` resets every profile to green and clears errors
- `Restart All` button exists in the profiles dashboard and routes to controller
- animated buttons pulse only on:
  - `Start`
  - `Raid NOW!`
  - `Restart All`
- animated buttons do not pulse while disabled or busy

## Versioning

This is a user-facing feature pass across runtime control and dashboard UX, so the implementation should end with a version bump.
