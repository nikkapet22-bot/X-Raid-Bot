# Action Timing Reduction Pass

## Goal

Reduce visible automation hesitation during raid actions without changing the action model or sequencing logic.

## Changes

### Global move-click delay

Normalize every mouse-move-then-click pause to `0.25s`.

This applies to:
- normal bot action clicks
- reply open click
- final reply finish-image click
- reply retry click
- repost clicks
- page-exit click
- troubleshoot clicks

Pure cursor moves without a click are unchanged.

### Scroll settle

Reduce the settle after each scroll from `1.0s` to `0.5s`.

This affects:
- action template search retries
- any runtime path that uses the shared scroll-settle constant

### Click confirmation window

Reduce the post-click confirmation window from `2.0s` to `1.5s`.

This affects the runner confirmation loop after a click has been sent.

### Repost timing

Reduce repost inter-click timing to `0.25s`.

Because all move-click delays are also normalized to `0.25s`, the repost second click now effectively becomes:
- `0.25s` inter-click wait
- `0.25s` move-click delay

### Reply timing

The final reply finish-image click now uses the same global `0.25s` move-click delay.

The existing reply finish delay and submit confirmation logic remain unchanged.

## Non-goals

- no change to reply finish delay
- no change to page-ready timeout
- no change to page-exit search timeout
- no change to warmup timings
- no change to action ordering logic

## Files

- `raidbot/desktop/automation/input.py`
- `raidbot/desktop/automation/runner.py`
- `raidbot/desktop/worker.py`
- related timing tests

## Verification

Focused tests should cover:
- generic move-click default timing
- runner scroll-settle timing
- runner click-confirmation timing
- repost timing
- slot 1 final reply click timing
- page-exit click timing

Version bump required at completion.
