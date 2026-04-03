# Score-Sensitive Slot 1 Reply Confirmation

## Problem

Slot 1 reply submission currently uses the same captured `Reply` button image both:

- before submit, when the button is active and visually white
- after submit, when the button can still appear in a weaker gray state

The current binary recheck logic treats any post-submit match as a failure signal. In practice, that causes false failures after real successful replies, because the gray post-submit state can still partially match the original white-button capture.

## Goal

Keep the existing user workflow and existing finish-image capture, but make slot 1 reply confirmation distinguish:

- a still-active white reply button that likely means submission did not happen
- a weaker gray post-submit button state that should count as success

## Non-Goals

- no new user settings
- no second finish-image capture
- no UI changes
- no redesign of other action slots

## Design

### 1. Keep the current finish-image capture

The existing slot 1 finish image remains the only capture used for reply submission confirmation.

### 2. Make the post-submit check score-sensitive

When slot 1 finds the finish image before the submit click, it already has an original match score for the active button state.

After clicking submit:

- re-scan briefly using the same finish template
- if there is no match, treat submission as successful
- if there is a match, compare the new score to the original pre-click score

Interpretation:

- materially weaker score:
  - treat as success
  - this corresponds to the gray post-submit state
- nearly unchanged strong score:
  - treat as likely still-active button
  - retry one more submit click

After the retry:

- if there is no match, success
- if the score is materially weaker, success
- if the score is still nearly unchanged, fail with `reply_submit_not_confirmed`

### 3. Scope of change

This behavior applies only to slot 1 reply confirmation.

Other slots continue using the existing generic click-confirmation behavior.

## Implementation Shape

- update `raidbot/desktop/automation/runner.py`
  - replace the current binary slot 1 recheck with score-sensitive logic
  - add a helper that decides whether a post-submit match is too similar to the original active-button score
- update `tests/desktop/automation/test_runner.py`
  - lower post-submit score => success
  - unchanged high post-submit score => retry
  - unchanged high score after retry => failure

## Verification

Focused verification should cover:

- slot 1 succeeds when the post-submit match disappears
- slot 1 succeeds when the post-submit match remains but drops materially in score
- slot 1 retries once when the post-submit score remains too close to the original
- slot 1 fails only if the score still remains too close after the retry
