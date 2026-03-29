# Dedicated Raid Window Automation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Telegram-triggered bot actions open each raid in a fresh dedicated Chrome window, run only against that window, close the whole window on success, and pause/retry the same open window on failure.

**Architecture:** Replace the current “pick an existing Chrome window and hope the new tab landed there” approach with an explicit per-raid window lifecycle. The worker should open a fresh Chrome window for each raid, detect the new Chrome surface created by that open, carry that window handle through execution, and keep that same open window context around for pause/resume retries. Auto-run admission should ignore new raids while paused instead of queuing them behind a broken raid.

**Tech Stack:** Python, existing `ChromeOpener`, PySide6 desktop app, Windows window enumeration/focus helpers, existing automation runtime (`windowing.py`, `runner.py`, `input.py`), pytest

---

## File Map

### Modify

- `raidbot/chrome.py`
  - Add explicit fresh-window raid opening support and return richer opened-window context.
- `raidbot/desktop/automation/windowing.py`
  - Add a helper to identify the Chrome window created or changed by a fresh raid open.
- `raidbot/desktop/automation/input.py`
  - Add a dedicated “close current Chrome window” action for successful dedicated-raid runs.
- `raidbot/desktop/automation/autorun.py`
  - Rework auto-run state so paused failures retain the active raid context and resume retries that same open window.
- `raidbot/desktop/worker.py`
  - Remove the generic existing-window targeting flow, open a fresh dedicated raid window, bind execution to that window, and ignore new raids while paused.
- `tests/test_chrome.py`
  - Cover fresh-window open commands and returned context.
- `tests/desktop/automation/test_windowing.py`
  - Cover new-window detection from before/after Chrome window snapshots.
- `tests/desktop/automation/test_input.py`
  - Cover the new window-close hotkey path.
- `tests/desktop/automation/test_autorun.py`
  - Cover paused retry-on-resume semantics and ignored admissions while paused.
- `tests/desktop/test_worker.py`
  - Cover dedicated raid window opening, retrying the same failed window, closing the whole window on success, and ignoring new raids while paused.

### Do Not Touch Unless Needed

- `raidbot/desktop/controller.py`
- `raidbot/desktop/main_window.py`
- `raidbot/desktop/bot_actions/page.py`

This feature is runtime behavior, not a visible Bot Actions UI redesign. Only touch the UI/controller if a failing test proves the runtime changes are not surfacing status correctly.

---

### Task 1: Add Dedicated Raid Window Open/Close Primitives

**Files:**
- Modify: `raidbot/chrome.py`
- Modify: `raidbot/desktop/automation/input.py`
- Modify: `tests/test_chrome.py`
- Modify: `tests/desktop/automation/test_input.py`

- [ ] **Step 1: Write the failing open/close tests**

```python
def test_chrome_opener_can_open_fresh_raid_window(monkeypatch):
    opener = ChromeOpener(...)
    context = opener.open_raid_window("https://example.com/status/123")
    assert captured["cmd"][1] == "--new-window"
    assert context.window_handle is None


def test_input_driver_close_active_window_uses_ctrl_shift_w():
    sent = []
    driver = InputDriver(send_hotkey=lambda keys: sent.append(keys))
    driver.close_active_window()
    assert sent == [("ctrl", "shift", "w")]
```

- [ ] **Step 2: Run the targeted tests to verify they fail**

Run:

```bash
python -m pytest -q tests/test_chrome.py tests/desktop/automation/test_input.py
```

Expected:
- FAIL because `open_raid_window()` and `close_active_window()` do not exist yet

- [ ] **Step 3: Implement the minimal dedicated-window primitives**

```python
class ChromeOpener:
    def open_raid_window(self, url: str) -> OpenedRaidContext:
        self.launcher([
            str(self.chrome_path),
            "--new-window",
            f"--user-data-dir={self.user_data_dir}",
            f"--profile-directory={self.profile_directory}",
            url,
        ])
        return OpenedRaidContext(
            normalized_url=url,
            opened_at=self.clock(),
            window_handle=None,
            profile_directory=self.profile_directory,
        )


class InputDriver:
    def close_active_window(self) -> None:
        self._send_hotkey(("ctrl", "shift", "w"))
```

Extend `_send_hotkey_win32()` so it safely supports both:
- `("ctrl", "w")`
- `("ctrl", "shift", "w")`

- [ ] **Step 4: Run the targeted tests to verify they pass**

Run:

```bash
python -m pytest -q tests/test_chrome.py tests/desktop/automation/test_input.py
```

Expected:
- PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/chrome.py raidbot/desktop/automation/input.py tests/test_chrome.py tests/desktop/automation/test_input.py
git commit -m "feat: add dedicated raid window open and close primitives"
```

---

### Task 2: Detect The Fresh Chrome Window Created For A Raid

**Files:**
- Modify: `raidbot/desktop/automation/windowing.py`
- Modify: `tests/desktop/automation/test_windowing.py`

- [ ] **Step 1: Write the failing window-detection tests**

```python
def test_find_opened_raid_window_prefers_new_handle():
    before = [WindowInfo(handle=7, title="Chrome", bounds=(0,0,1,1), last_focused_at=1.0)]
    after = before + [WindowInfo(handle=9, title="Chrome", bounds=(0,0,1,1), last_focused_at=2.0)]
    chosen = find_opened_raid_window(before, after)
    assert chosen.handle == 9


def test_find_opened_raid_window_falls_back_to_most_recent_changed_candidate():
    before = [WindowInfo(handle=7, title="Old title", bounds=(0,0,1,1), last_focused_at=1.0)]
    after = [WindowInfo(handle=7, title="New raid title", bounds=(0,0,1,1), last_focused_at=3.0)]
    chosen = find_opened_raid_window(before, after)
    assert chosen.handle == 7
```

- [ ] **Step 2: Run the targeted tests to verify they fail**

Run:

```bash
python -m pytest -q tests/desktop/automation/test_windowing.py -k "opened_raid_window"
```

Expected:
- FAIL because the dedicated-window detection helper does not exist yet

- [ ] **Step 3: Implement the minimal opened-window detection helper**

```python
def find_opened_raid_window(
    before_windows: list[WindowInfo],
    after_windows: list[WindowInfo],
) -> WindowInfo | None:
    before_by_handle = {window.handle: window for window in before_windows}
    new_handles = [window for window in after_windows if window.handle not in before_by_handle]
    if new_handles:
        return max(new_handles, key=lambda item: item.last_focused_at)

    changed = []
    for window in after_windows:
        previous = before_by_handle.get(window.handle)
        if previous is None:
            continue
        if window.title != previous.title or window.last_focused_at > previous.last_focused_at:
            changed.append(window)
    return max(changed, key=lambda item: item.last_focused_at, default=None)
```

Keep this helper small and deterministic. Do not add broader Chrome ownership heuristics here.

- [ ] **Step 4: Run the targeted tests to verify they pass**

Run:

```bash
python -m pytest -q tests/desktop/automation/test_windowing.py -k "opened_raid_window"
```

Expected:
- PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/desktop/automation/windowing.py tests/desktop/automation/test_windowing.py
git commit -m "feat: detect dedicated raid window after chrome open"
```

---

### Task 3: Rework Auto-Run To Use A Fresh Dedicated Raid Window

**Files:**
- Modify: `raidbot/desktop/automation/autorun.py`
- Modify: `raidbot/desktop/worker.py`
- Modify: `tests/desktop/automation/test_autorun.py`
- Modify: `tests/desktop/test_worker.py`

- [ ] **Step 1: Write the failing worker/autorun tests**

```python
def test_worker_opens_fresh_raid_window_and_runs_against_detected_opened_handle(...):
    outcome = worker._handle_message(build_message(...))
    assert opener.open_raid_window_calls == ["https://x.com/i/status/777"]
    assert runtime.run_calls == [("bot-actions", 9)]


def test_autorun_processor_failure_keeps_context_for_resume_retry(...):
    processor.admit(build_item())
    assert processor.process_next() is False
    assert processor.state == "paused"
    processor.resume()
    assert execute_calls == [("raid-1", 21), ("raid-1", 21)]


def test_worker_ignores_new_raids_while_paused_on_failed_window(...):
    worker._handle_message(first_message)
    worker._handle_message(second_message)
    assert second_failure_reason == "auto_run_paused"
    assert opener.open_raid_window_calls == [first_url]


def test_worker_success_closes_active_raid_window_not_tab(...):
    worker._handle_message(message)
    assert runtime.input_driver.close_active_window_calls == 1
    assert runtime.input_driver.close_active_tab_calls == 0
```

- [ ] **Step 2: Run the targeted tests to verify they fail**

Run:

```bash
python -m pytest -q tests/desktop/automation/test_autorun.py tests/desktop/test_worker.py -k "fresh_raid_window or paused_on_failed_window or close_active_window or resume_retry"
```

Expected:
- FAIL because the processor still assumes pre-open window targeting
- FAIL because resume does not retry the same open context
- FAIL because success still closes only a tab

- [ ] **Step 3: Implement the minimal dedicated-window autorun flow**

In `DesktopBotWorker`:

```python
before_windows = runtime.list_target_windows()
context = opener.open_raid_window(item.normalized_url)
self.auto_run_wait(self.config.auto_run_settle_ms / 1000.0)
after_windows = runtime.list_target_windows()
opened_window = find_opened_raid_window(before_windows, after_windows)
```

Then:
- bind the detected `opened_window.handle` onto the opened raid context
- emit `automation_started` with that handle
- run the sequence against only that handle
- on success call `input_driver.close_active_window()`

In `AutoRunProcessor`:
- keep `failed_item` and `failed_context` when execution fails
- while paused, reject new admissions with `auto_run_paused`
- add a narrow resume path that retries the stored failed item/context instead of reopening a new raid window
- clear the stored failed context only after a successful retry or explicit clear/reset

Do not reintroduce generic queue-draining behind a failed raid. While paused, later raids are ignored.

- [ ] **Step 4: Run the targeted tests to verify they pass**

Run:

```bash
python -m pytest -q tests/desktop/automation/test_autorun.py tests/desktop/test_worker.py -k "fresh_raid_window or paused_on_failed_window or close_active_window or resume_retry"
```

Expected:
- PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/desktop/automation/autorun.py raidbot/desktop/worker.py tests/desktop/automation/test_autorun.py tests/desktop/test_worker.py
git commit -m "feat: run telegram raids in dedicated chrome windows"
```

---

### Task 4: Full Regression Verification

**Files:**
- Modify only touched files from Tasks 1-3 if green verification exposes a real issue

- [ ] **Step 1: Run the focused regression suite**

Run:

```bash
python -m pytest -q tests/test_chrome.py tests/desktop/automation/test_input.py tests/desktop/automation/test_windowing.py tests/desktop/automation/test_autorun.py tests/desktop/test_worker.py
```

Expected:
- PASS

- [ ] **Step 2: Run the full suite**

Run:

```bash
python -m pytest -q
```

Expected:
- PASS

- [ ] **Step 3: Manual desktop smoke**

Run:

```bash
python -m raidbot.desktop.app
```

Verify:
- Telegram raid opens a fresh Chrome window
- bot actions run in that window only
- success closes the whole raid window
- failure leaves the raid window open and pauses the bot
- resume retries the same open failed raid window

- [ ] **Step 4: Commit**

```bash
git add raidbot/chrome.py raidbot/desktop/automation/input.py raidbot/desktop/automation/windowing.py raidbot/desktop/automation/autorun.py raidbot/desktop/worker.py tests/test_chrome.py tests/desktop/automation/test_input.py tests/desktop/automation/test_windowing.py tests/desktop/automation/test_autorun.py tests/desktop/test_worker.py
git commit -m "test: verify dedicated raid window automation flow"
```

---

## Notes For The Implementer

- Keep this change scoped to the Telegram-triggered auto-run path. The manual `Test` button can continue using the current generic Chrome-window targeting unless a failing test proves it must change too.
- Do not add new config knobs for this. The behavior should become the default runtime model for Telegram-triggered bot actions.
- Reuse the existing automation runtime and runner; the main change is how the worker creates and targets the Chrome surface.
- Follow `@superpowers:test-driven-development` strictly: every runtime change starts with a failing test.
- Keep commits small and aligned with the tasks above.
