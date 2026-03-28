# Telegram Auto Sequence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automatically queue Telegram-detected raid links in the desktop app, open them one-by-one in Chrome, run one default image-based automation sequence after a settle delay, close only the active tab on success, and pause visibly on failure.

**Architecture:** Keep Telegram admission and queue ownership in the desktop worker, but extract the existing manual automation runtime into a shared module so both manual runs and Telegram-triggered auto-runs reuse the same window capture, matching, focus, and input logic. Extend desktop config/state and the Automation tab to persist auto-run settings and expose queue state without changing the existing manual sequence editor workflow.

**Tech Stack:** Python, PySide6, existing desktop automation modules (`windowing`, `runner`, `input`), win32-backed Chrome/window interaction, pytest.

---

## File Structure

### Existing files to modify

- `raidbot/desktop/models.py`
  - Add persisted auto-run config fields and runtime queue state fields.
- `raidbot/desktop/storage.py`
  - Persist/load new auto-run config and queue state fields.
- `raidbot/desktop/controller.py`
  - Stop owning a private automation runtime implementation; load the shared runtime, expose auto-run config updates, and forward worker auto-run status events to the Automation tab.
- `raidbot/desktop/worker.py`
  - Replace immediate open-on-detect behavior with admission + queue + per-item processing.
- `raidbot/desktop/main_window.py`
  - Wire new Automation-tab controls and queue status displays to controller signals.
- `raidbot/desktop/automation/page.py`
  - Add auto-run settings controls, queue displays, and queue recovery actions without breaking manual run controls.
- `raidbot/desktop/automation/input.py`
  - Add a keyboard/tab-close capability for the success path.
- `raidbot/desktop/automation/windowing.py`
  - Reuse existing focus helpers and, if needed, expose a tiny seam for "existing owned Chrome window available" checks.
- `raidbot/chrome.py`
  - Stop being a pure fire-and-forget wrapper; return enough context to let the worker reacquire the Chrome window it opened into.
- `tests/desktop/test_models.py`
  - Cover new config/state fields.
- `tests/desktop/test_storage.py`
  - Cover config/state persistence and migration defaults.
- `tests/desktop/test_controller.py`
  - Cover controller-side config updates and signal propagation for queue status.
- `tests/desktop/test_main_window.py`
  - Cover Automation-tab controls and disabled/enabled states.
- `tests/desktop/test_worker.py`
  - Cover admission, queue sequencing, failure pause behavior, and activity/state updates.
- `tests/desktop/automation/test_controller_integration.py`
  - Cover shared runtime reuse from the controller side.
- `tests/test_chrome.py`
  - Cover opened-context behavior.

### New files to create

- `raidbot/desktop/automation/runtime.py`
  - Shared automation runtime extracted from `raidbot/desktop/controller.py` so both manual runs and Telegram auto-runs use the same sequence execution seam.
- `raidbot/desktop/automation/autorun.py`
  - Worker-owned queue dataclasses and processor for pending work items, opened raid context, queue transitions, and failure handling.
- `tests/desktop/automation/test_runtime.py`
  - Unit tests for the shared runtime wrapper.
- `tests/desktop/automation/test_input.py`
  - Unit tests for the new tab-close input capability.

### Optional docs update

- `README.md`
  - Briefly document the new Automation-tab auto-run flow and the first-version operating contract that Chrome must already be open and untouched during active auto-runs.

## Task 1: Persist Auto-Run Config And Queue State

**Files:**
- Modify: `raidbot/desktop/models.py`
- Modify: `raidbot/desktop/storage.py`
- Test: `tests/desktop/test_models.py`
- Test: `tests/desktop/test_storage.py`

- [ ] **Step 1: Write failing model/storage tests for new auto-run fields**

Add assertions for:
- `DesktopAppConfig.auto_run_enabled`
- `DesktopAppConfig.default_auto_sequence_id`
- `DesktopAppConfig.auto_run_settle_ms`
- `DesktopAppState.automation_queue_state`
- `DesktopAppState.automation_queue_length`
- `DesktopAppState.automation_current_url`
- `DesktopAppState.automation_last_error`

Example test additions:

```python
config = DesktopAppConfig(
    ...,
    auto_run_enabled=True,
    default_auto_sequence_id="seq-1",
    auto_run_settle_ms=1500,
)
assert config.auto_run_enabled is True
assert config.default_auto_sequence_id == "seq-1"
assert config.auto_run_settle_ms == 1500
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run:

```bash
python -m pytest -q tests/desktop/test_models.py tests/desktop/test_storage.py
```

Expected: FAIL with missing constructor/state fields or missing persisted keys.

- [ ] **Step 3: Extend desktop config/state models with the new fields**

Update `DesktopAppConfig` defaults so the feature is off by default:

```python
auto_run_enabled: bool = False
default_auto_sequence_id: str | None = None
auto_run_settle_ms: int = 1500
```

Update `DesktopAppState` with runtime-only queue fields:

```python
automation_queue_state: str = "idle"
automation_queue_length: int = 0
automation_current_url: str | None = None
automation_last_error: str | None = None
```

- [ ] **Step 4: Persist and load the new config/state fields**

Modify `DesktopStorage._config_to_data`, `_config_from_data`, `_state_to_data`, and `_state_from_data` to serialize the new fields and default safely when loading old data.

- [ ] **Step 5: Re-run the focused tests and make them pass**

Run:

```bash
python -m pytest -q tests/desktop/test_models.py tests/desktop/test_storage.py
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add raidbot/desktop/models.py raidbot/desktop/storage.py tests/desktop/test_models.py tests/desktop/test_storage.py
git commit -m "feat: persist desktop auto-run config and queue state"
```

## Task 2: Extract A Shared Automation Runtime And Add Tab-Close Input

**Files:**
- Create: `raidbot/desktop/automation/runtime.py`
- Modify: `raidbot/desktop/controller.py`
- Modify: `raidbot/desktop/automation/input.py`
- Test: `tests/desktop/automation/test_controller_integration.py`
- Create: `tests/desktop/automation/test_runtime.py`
- Create: `tests/desktop/automation/test_input.py`

- [ ] **Step 1: Write failing tests for shared runtime reuse and tab-close input**

Add tests that prove:
- controller still runs manual automation through a shared runtime module
- the input driver can issue a close-active-tab keyboard action without affecting click/scroll behavior

Example input test:

```python
driver = InputDriver(send_hotkey=recorded.append)
driver.close_active_tab()
assert recorded == [("ctrl", "w")]
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run:

```bash
python -m pytest -q tests/desktop/automation/test_controller_integration.py tests/desktop/automation/test_runtime.py tests/desktop/automation/test_input.py
```

Expected: FAIL because `runtime.py` does not exist and `InputDriver` has no tab-close method.

- [ ] **Step 3: Move `_AutomationRuntime` into a shared module**

Create `raidbot/desktop/automation/runtime.py` with a public runtime class that exposes:
- `list_target_windows()`
- `run_sequence(sequence, selected_window_handle)`
- `dry_run_step(sequence, step_index, selected_window_handle)`
- `request_stop()`

Keep the behavior identical to the current private implementation in `controller.py` so manual runs do not change.

- [ ] **Step 4: Update the controller to import and use the shared runtime**

Replace the private `_AutomationRuntime` path with imports from the new shared module. Keep the same public controller API for manual runs.

- [ ] **Step 5: Extend `InputDriver` with a tab-close method**

Add a small keyboard seam, not a generic macro engine:

```python
def close_active_tab(self) -> None:
    self._send_hotkey(("ctrl", "w"))
```

Use a win32-backed implementation and injectable test double.

- [ ] **Step 6: Re-run the focused tests and make them pass**

Run:

```bash
python -m pytest -q tests/desktop/automation/test_controller_integration.py tests/desktop/automation/test_runtime.py tests/desktop/automation/test_input.py
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add raidbot/desktop/controller.py raidbot/desktop/automation/runtime.py raidbot/desktop/automation/input.py tests/desktop/automation/test_controller_integration.py tests/desktop/automation/test_runtime.py tests/desktop/automation/test_input.py
git commit -m "refactor: share automation runtime and add tab close input"
```

## Task 3: Add Opened-Raid Context And Worker-Owned Auto Queue Processor

**Files:**
- Create: `raidbot/desktop/automation/autorun.py`
- Modify: `raidbot/chrome.py`
- Modify: `raidbot/desktop/automation/windowing.py`
- Modify: `tests/test_chrome.py`
- Test: `tests/desktop/test_worker.py`

- [ ] **Step 1: Write failing tests for queue items, opened context, and pre-open checks**

Cover these scenarios in `tests/desktop/test_worker.py` and `tests/test_chrome.py`:
- detected links are admitted into a pending queue instead of opening immediately
- disabled auto-run rejects admission without opening Chrome
- missing default sequence pauses the queue without opening Chrome
- no existing Chrome window pauses the queue before open
- when Chrome opens successfully, the worker stores enough context to target the same window later

Example worker assertion:

```python
assert worker.state.automation_queue_state == "queued"
assert worker.state.automation_queue_length == 1
assert pipeline.execute_calls == []
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run:

```bash
python -m pytest -q tests/test_chrome.py tests/desktop/test_worker.py
```

Expected: FAIL because the worker still opens links immediately and `ChromeOpener` returns no context.

- [ ] **Step 3: Add queue/opened-context dataclasses and processor**

Create `raidbot/desktop/automation/autorun.py` with focused types:
- `PendingRaidWorkItem`
- `OpenedRaidContext`
- `AutoRunProcessor`

`AutoRunProcessor` should own:
- FIFO pending items
- queue state transitions (`idle`, `queued`, `running`, `paused`)
- admission checks
- pre-open validation
- success/failure bookkeeping callbacks

Keep Chrome opening and sequence execution injected through narrow callables so the class is easy to fake in tests.

- [ ] **Step 4: Extend `ChromeOpener` to return an opened context instead of `None`**

Do not add browser-internal tab IDs. Return only the data the first version can actually prove, such as:

```python
OpenedRaidContext(
    normalized_url=url,
    opened_at=clock(),
    window_handle=window_handle,
    profile_directory=self.profile_directory,
)
```

If an existing Chrome window cannot be identified safely before open, fail visibly instead of inventing one.

- [ ] **Step 5: Add a tiny windowing seam for "existing Chrome window available"**

Reuse `WindowManager.list_chrome_windows()` and `choose_window_for_rule()` instead of adding a second window discovery implementation.

- [ ] **Step 6: Re-run the focused tests and make them pass**

Run:

```bash
python -m pytest -q tests/test_chrome.py tests/desktop/test_worker.py
```

Expected: PASS for the new queue/opened-context cases.

- [ ] **Step 7: Commit**

```bash
git add raidbot/chrome.py raidbot/desktop/automation/autorun.py raidbot/desktop/automation/windowing.py tests/test_chrome.py tests/desktop/test_worker.py
git commit -m "feat: add opened raid context and auto-run queue processor"
```

## Task 4: Integrate The Desktop Worker With Auto-Run Processing

**Files:**
- Modify: `raidbot/desktop/worker.py`
- Modify: `tests/desktop/test_worker.py`

- [ ] **Step 1: Write failing worker tests for end-to-end queue behavior**

Add coverage for:
- one detected link queues, opens at head-of-queue, and starts auto processing
- two detected links process strictly one by one
- disabling auto-run while items are pending leaves them pending and unopened
- success closes only the active tab and continues
- failure leaves the tab open, emits an error, and pauses the queue
- `Resume queue` continues with the next pending item
- `Clear queue` removes pending items without touching the failed tab

Example success assertion:

```python
assert emitted_actions == [
    "raid_detected",
    "auto_queued",
    "automation_started",
    "automation_succeeded",
    "session_closed",
]
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run:

```bash
python -m pytest -q tests/desktop/test_worker.py
```

Expected: FAIL because `_handle_message` still routes directly to `BrowserPipeline.execute(...)`.

- [ ] **Step 3: Replace immediate pipeline execution with admission + queue handling**

Refactor `DesktopBotWorker` so `_handle_message()`:
- records the detection result
- hands admitted items to `AutoRunProcessor`
- only opens Chrome when the processor starts the head-of-queue item
- records queue/automation activity into `DesktopAppState`

Keep existing non-detected and rejected-message behavior unchanged.

- [ ] **Step 4: Reuse the shared automation runtime from the worker**

Inject or lazily build the same automation runtime used by manual controller runs. Do not reimplement capture/matching/focus/click logic inside the worker.

- [ ] **Step 5: Add explicit worker events for the Automation tab**

Emit structured events for:
- queue state changes
- queue length changes
- current URL changes
- auto-run started/succeeded/failed

These should be separate from the existing manual `automationRunEvent` feed so the UI can display queue state cleanly.

- [ ] **Step 6: Re-run the focused worker tests and make them pass**

Run:

```bash
python -m pytest -q tests/desktop/test_worker.py
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add raidbot/desktop/worker.py tests/desktop/test_worker.py
git commit -m "feat: wire Telegram detection into worker-owned auto sequence queue"
```

## Task 5: Add Automation-Tab Controls And Controller/Main-Window Plumbing

**Files:**
- Modify: `raidbot/desktop/automation/page.py`
- Modify: `raidbot/desktop/controller.py`
- Modify: `raidbot/desktop/main_window.py`
- Test: `tests/desktop/test_controller.py`
- Test: `tests/desktop/test_main_window.py`

- [ ] **Step 1: Write failing UI/controller tests for auto-run controls**

Cover:
- Automation page shows `Auto-run enabled`, `Default auto sequence`, `Settle delay`, queue state, queue length, current URL, `Resume queue`, and `Clear queue`
- selecting a default sequence persists through the controller/config path
- manual `Start run` and `Dry run step` are disabled when the queue is `queued`, `running`, or `paused`
- queue events from the worker update the Automation tab labels/buttons

Example assertion:

```python
assert page.resume_queue_button.isEnabled() is False
assert page.auto_run_toggle.isChecked() is False
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run:

```bash
python -m pytest -q tests/desktop/test_controller.py tests/desktop/test_main_window.py
```

Expected: FAIL because the page/controller do not yet expose those controls or signals.

- [ ] **Step 3: Extend `AutomationPage` with a dedicated auto-run section**

Add:
- toggle
- default sequence selector
- settle delay input
- queue state/length/current URL labels
- `Resume queue` button
- `Clear queue` button

Do not remove or repurpose the existing manual sequence editor.

- [ ] **Step 4: Add controller methods/signals for auto-run config and queue state**

The controller should:
- save updated auto-run config through `DesktopStorage`
- forward worker queue-state events to the UI
- keep manual-run state and auto-queue state distinct

- [ ] **Step 5: Wire the main window**

Connect the new page signals to the controller and route worker/controller updates back into `AutomationPage`.

- [ ] **Step 6: Re-run the focused tests and make them pass**

Run:

```bash
python -m pytest -q tests/desktop/test_controller.py tests/desktop/test_main_window.py
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add raidbot/desktop/automation/page.py raidbot/desktop/controller.py raidbot/desktop/main_window.py tests/desktop/test_controller.py tests/desktop/test_main_window.py
git commit -m "feat: add Automation tab controls for Telegram auto-run queue"
```

## Task 6: Run Full Regression Coverage And Update Docs

**Files:**
- Modify: `README.md`
- Test: `tests/test_chrome.py`
- Test: `tests/desktop/test_models.py`
- Test: `tests/desktop/test_storage.py`
- Test: `tests/desktop/test_controller.py`
- Test: `tests/desktop/test_main_window.py`
- Test: `tests/desktop/test_worker.py`
- Test: `tests/desktop/automation/test_controller_integration.py`
- Test: `tests/desktop/automation/test_runtime.py`
- Test: `tests/desktop/automation/test_input.py`

- [ ] **Step 1: Add a short README section for the supported first-version workflow**

Document:
- Chrome must already be open for the configured profile
- the bot queues links one by one
- success closes only the active tab
- failure leaves the tab open and pauses the queue
- user should not interact with the owned Chrome window during an active auto-run

- [ ] **Step 2: Run the focused regression suite**

Run:

```bash
python -m pytest -q tests/test_chrome.py tests/desktop/test_models.py tests/desktop/test_storage.py tests/desktop/test_controller.py tests/desktop/test_main_window.py tests/desktop/test_worker.py tests/desktop/automation/test_controller_integration.py tests/desktop/automation/test_runtime.py tests/desktop/automation/test_input.py
```

Expected: PASS.

- [ ] **Step 3: Run the full suite**

Run:

```bash
python -m pytest -q
```

Expected: PASS for the full repository test suite.

- [ ] **Step 4: Commit**

```bash
git add README.md tests/test_chrome.py tests/desktop/test_models.py tests/desktop/test_storage.py tests/desktop/test_controller.py tests/desktop/test_main_window.py tests/desktop/test_worker.py tests/desktop/automation/test_controller_integration.py tests/desktop/automation/test_runtime.py tests/desktop/automation/test_input.py
git commit -m "docs: document Telegram auto-run workflow"
```

## Notes For Execution

- Do not try to wire this through the existing `BrowserPipeline` until the queue processor has replaced immediate open-on-detect behavior; otherwise the implementation will violate the approved queue-before-open spec.
- Keep the first version conservative. If tab identity cannot be proven safely, fail and pause rather than guessing.
- Manual automation and Telegram auto-runs must share the same runtime primitives, but their UI state should remain distinct.
- Keep commits small and task-scoped. If a task reveals a hidden dependency, update the plan before continuing instead of silently broadening the change.
