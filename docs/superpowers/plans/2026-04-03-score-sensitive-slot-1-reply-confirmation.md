# Score-Sensitive Slot 1 Reply Confirmation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make slot 1 reply confirmation distinguish an active white submit button from the weaker post-submit gray state, so successful replies do not get marked as failed.

**Architecture:** Keep the existing finish-image capture and change only the slot 1 post-submit confirmation logic inside the automation runner. Compare post-submit match score against the original pre-click score, retry once only when the score remains too similar, and fail only if the score still remains too close after the retry.

**Tech Stack:** Python, PySide6 desktop bot, existing automation runner and pytest suite

---

### Task 1: Add score-sensitive slot 1 runner coverage

**Files:**
- Modify: `tests/desktop/automation/test_runner.py`
- Modify: `raidbot/desktop/automation/runner.py`

- [ ] **Step 1: Write the failing runner tests**

Add/replace slot 1 reply-confirmation tests in `tests/desktop/automation/test_runner.py` to cover:

```python
def test_runner_slot_1_treats_weaker_post_submit_match_as_success(...):
    ...
    assert result.status == "completed"


def test_runner_slot_1_retries_when_post_submit_match_score_stays_too_similar(...):
    ...
    assert input_driver.clicks == [(25, 15), (45, 15), (45, 15)]


def test_runner_slot_1_fails_when_post_submit_match_score_stays_too_similar_after_retry(...):
    ...
    assert result.failure_reason == "reply_submit_not_confirmed"
```

Model the post-submit states by returning `MatchResult` objects whose `score` is:
- materially lower than the original pre-click finish-button score for success
- nearly unchanged from the original score for retry/failure

- [ ] **Step 2: Run the focused runner tests to verify they fail**

Run: `python -m pytest -q tests\desktop\automation\test_runner.py -k "slot_1 and (weaker_post_submit_match or too_similar)"`

Expected: FAIL because current slot 1 logic treats the reply-button recheck as binary instead of score-sensitive.

- [ ] **Step 3: Implement the minimal slot 1 score-sensitive confirmation**

Update `raidbot/desktop/automation/runner.py`:

```python
def _slot_1_match_still_looks_active(original_score: float, current_score: float) -> bool:
    return current_score >= max(0.9, original_score - 0.03)


def _verify_slot_1_reply_submission(...):
    finish_still_visible = self._find_match_for_template(...)
    if isinstance(finish_still_visible, RunResult):
        if finish_still_visible.failure_reason == "match_not_found":
            return None
        return finish_still_visible

    retry_window, _retry_frame, retry_match = finish_still_visible
    if not self._slot_1_match_still_looks_active(finish_match.score, retry_match.score):
        return None

    self.input_driver.move_click(retry_point, delay_seconds=1.0)
    self.sleep(_SLOT_1_REPLY_SUBMIT_RETRY_DELAY_SECONDS)

    finish_after_retry = self._find_match_for_template(...)
    if isinstance(finish_after_retry, RunResult):
        if finish_after_retry.failure_reason == "match_not_found":
            return None
        return finish_after_retry
    if not self._slot_1_match_still_looks_active(finish_match.score, finish_after_retry[2].score):
        return None
    return RunResult(status="failed", failure_reason="reply_submit_not_confirmed", ...)
```

Keep the change slot-1-specific. Do not change generic click-confirmation behavior for other slots.

- [ ] **Step 4: Run the focused runner tests to verify they pass**

Run: `python -m pytest -q tests\desktop\automation\test_runner.py -k "slot_1 and (weaker_post_submit_match or too_similar)"`

Expected: PASS

- [ ] **Step 5: Run the full runner slice**

Run: `python -m pytest -q tests\desktop\automation\test_runner.py`

Expected: PASS

- [ ] **Step 6: Commit the runner fix**

```bash
git add tests/desktop/automation/test_runner.py raidbot/desktop/automation/runner.py
git commit -m "fix: make slot 1 reply confirmation score-sensitive"
```

### Task 2: Keep the new failure reason readable if it surfaces

**Files:**
- Modify: `raidbot/desktop/controller.py`
- Test: `tests/desktop/test_controller.py`

- [ ] **Step 1: Write the failing controller test**

Add a focused test in `tests/desktop/test_controller.py` for slot-test status rendering:

```python
def test_controller_formats_reply_submit_not_confirmed_slot_test_reason(...):
    ...
    assert event["message"].endswith("reply submit not confirmed")
```

- [ ] **Step 2: Run the focused controller test to verify it fails**

Run: `python -m pytest -q tests\desktop\test_controller.py -k "reply_submit_not_confirmed"`

Expected: FAIL because the reason is not yet mapped to a friendly message.

- [ ] **Step 3: Add the reason mapping**

Update `raidbot/desktop/controller.py`:

```python
reason_messages = {
    ...
    "reply_submit_not_confirmed": "reply submit not confirmed",
}
```

- [ ] **Step 4: Run the focused controller test to verify it passes**

Run: `python -m pytest -q tests\desktop\test_controller.py -k "reply_submit_not_confirmed"`

Expected: PASS

- [ ] **Step 5: Run the combined verification slice**

Run: `python -m pytest -q tests\desktop\automation\test_runner.py tests\desktop\test_controller.py -k "slot_1 or reply_submit_not_confirmed"`

Expected: PASS

- [ ] **Step 6: Commit the polish**

```bash
git add raidbot/desktop/controller.py tests/desktop/test_controller.py
git commit -m "fix: surface slot 1 reply confirmation failures clearly"
```
