# Bot Action Slot Test Button Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a smaller `Capture` button plus a per-slot `Test` button that runs one real bot-style action check against Chrome and reports the result in the Bot Actions status area.

**Architecture:** Keep the change narrow. The Bot Actions tab only emits UI signals, the main window wires them, the controller owns slot-test orchestration, and the existing automation runtime performs the actual match/move/click/confirm behavior. Reuse the existing fixed-slot model and the existing one-step automation runner instead of adding a second click engine.

**Tech Stack:** PySide6, existing desktop automation runtime, pytest, pytest-qt

---

## File Structure

- **Modify:** `raidbot/desktop/bot_actions/page.py`
  - Add the smaller `Capture` button layout and the new per-slot `Test` button signal.
- **Modify:** `raidbot/desktop/bot_actions/sequence.py`
  - Add a helper for building a one-slot ephemeral test sequence.
- **Modify:** `raidbot/desktop/controller.py`
  - Add `test_bot_action_slot(slot_index)` and the narrow runtime/status mapping for slot tests.
- **Modify:** `raidbot/desktop/main_window.py`
  - Wire the new Bot Actions slot-test signal into the controller and surface immediate status/error text cleanly.
- **Test:** `tests/desktop/bot_actions/test_page.py`
  - Cover button presence, smaller capture layout expectations, and per-slot test signal emission.
- **Test:** `tests/desktop/test_controller.py`
  - Cover missing template, missing Chrome, successful one-slot test routing, and failure-result mapping.
- **Test:** `tests/desktop/test_main_window.py`
  - Cover main-window wiring and visible status text after pressing `Test`.

### Task 1: Add Bot Actions Slot Test UI

**Files:**
- Modify: `raidbot/desktop/bot_actions/page.py`
- Test: `tests/desktop/bot_actions/test_page.py`

- [ ] **Step 1: Write the failing UI tests**

Add tests that verify:
- each slot exposes a `Test` button
- the page emits a new `slotTestRequested(int)` signal when a slot test button is pressed
- the capture button is visually reduced so the two buttons fit together under the thumbnail

Suggested test shape:

```python
def test_bot_actions_page_test_button_emits_slot_test_signal(qtbot) -> None:
    page = BotActionsPage(config=build_config())
    qtbot.addWidget(page)
    captured = []
    page.slotTestRequested.connect(captured.append)

    qtbot.mouseClick(page.slot_boxes[1].test_button, Qt.MouseButton.LeftButton)

    assert captured == [1]
```

- [ ] **Step 2: Run the UI tests to verify they fail**

Run:

```bash
python -m pytest -q tests\desktop\bot_actions\test_page.py -k "test_button or capture_button"
```

Expected: FAIL because the slot UI does not yet expose `test_button`/`slotTestRequested`, and the capture button layout is still the old single-button shape.

- [ ] **Step 3: Implement the minimal UI changes**

Update `raidbot/desktop/bot_actions/page.py`:
- add `slotTestRequested = Signal(int)`
- add `test_button` to each `SlotBox`
- place `Capture` and `Test` in one compact row beneath the thumbnail
- keep the thumbnail above both buttons
- keep existing checkbox and path/status label behavior intact

- [ ] **Step 4: Run the UI tests to verify they pass**

Run:

```bash
python -m pytest -q tests\desktop\bot_actions\test_page.py
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/desktop/bot_actions/page.py tests/desktop/bot_actions/test_page.py
git commit -m "feat: add bot action slot test button"
```

### Task 2: Add One-Slot Test Orchestration In The Controller

**Files:**
- Modify: `raidbot/desktop/bot_actions/sequence.py`
- Modify: `raidbot/desktop/controller.py`
- Test: `tests/desktop/test_controller.py`

- [ ] **Step 1: Write the failing controller tests**

Add tests that verify:
- `test_bot_action_slot()` rejects a slot with no template path
- `test_bot_action_slot()` rejects a slot whose file path does not exist
- `test_bot_action_slot()` rejects when no Chrome window is available
- `test_bot_action_slot()` chooses the most recently focused Chrome window
- `test_bot_action_slot()` runs a one-step sequence through the existing automation runtime
- result mapping produces simple Bot Actions result events/messages

Suggested test shape:

```python
def test_controller_rejects_slot_test_when_template_missing(qtbot) -> None:
    controller = DesktopController(...)
    errors = []
    controller.errorRaised.connect(errors.append)

    controller.test_bot_action_slot(0)

    assert errors == ["Slot 1 (R): template missing"]
```

- [ ] **Step 2: Run the controller tests to verify they fail**

Run:

```bash
python -m pytest -q tests\desktop\test_controller.py -k "slot_test"
```

Expected: FAIL because the controller has no slot-test entrypoint yet.

- [ ] **Step 3: Implement the minimal controller/runtime bridge**

Update `raidbot/desktop/bot_actions/sequence.py`:
- add a helper that builds a one-step ephemeral sequence from one slot

Update `raidbot/desktop/controller.py`:
- add `test_bot_action_slot(slot_index: int)`
- validate template presence and file existence
- load the automation runtime
- auto-pick the most recently focused Chrome window from `runtime.list_target_windows()`
- run the one-step sequence through the existing runtime/runner path
- block if queue-owned or manual automation is already active
- map success/failure into simple Bot Actions status/error output

Keep this narrow. Do not add a separate matching/click implementation.

- [ ] **Step 4: Run the controller tests to verify they pass**

Run:

```bash
python -m pytest -q tests\desktop\test_controller.py -k "slot_test"
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/desktop/bot_actions/sequence.py raidbot/desktop/controller.py tests/desktop/test_controller.py
git commit -m "feat: add bot action slot test flow"
```

### Task 3: Wire Main Window And User-Visible Status

**Files:**
- Modify: `raidbot/desktop/main_window.py`
- Test: `tests/desktop/test_main_window.py`

- [ ] **Step 1: Write the failing main-window tests**

Add tests that verify:
- pressing a slot `Test` button calls the controller with the correct slot index
- successful slot-test result shows simple status text
- failed slot-test result shows simple failure text

Suggested test shape:

```python
def test_main_window_test_button_calls_controller(qtbot) -> None:
    controller = FakeController()
    window = build_window(controller, FakeStorage())
    qtbot.addWidget(window)

    qtbot.mouseClick(window.bot_actions_page.slot_boxes[0].test_button, Qt.MouseButton.LeftButton)

    assert controller.bot_action_slot_test_calls == [0]
```

- [ ] **Step 2: Run the main-window tests to verify they fail**

Run:

```bash
python -m pytest -q tests\desktop\test_main_window.py -k "slot_test or test_button"
```

Expected: FAIL because the main window does not wire the new signal yet.

- [ ] **Step 3: Implement the minimal wiring**

Update `raidbot/desktop/main_window.py`:
- connect `slotTestRequested` to `controller.test_bot_action_slot`
- keep the existing Bot Actions status rendering simple
- ensure slot-test outcomes surface as user-readable status messages without reviving old runner UI

If needed, use existing `errorRaised`/Bot Actions status plumbing instead of inventing a second status channel.

- [ ] **Step 4: Run the main-window tests to verify they pass**

Run:

```bash
python -m pytest -q tests\desktop\test_main_window.py -k "slot_test or test_button"
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/desktop/main_window.py tests/desktop/test_main_window.py
git commit -m "feat: wire bot action slot test UI"
```

### Task 4: Final Regression Verification

**Files:**
- Re-run only; no new files expected unless regressions require fixes

- [ ] **Step 1: Run focused bot-actions and desktop regressions**

Run:

```bash
python -m pytest -q tests\desktop\bot_actions tests\desktop\test_controller.py tests\desktop\test_main_window.py
```

Expected: PASS

- [ ] **Step 2: Run the full suite**

Run:

```bash
python -m pytest -q
```

Expected: PASS

- [ ] **Step 3: Commit only if regression fixes were needed**

If any follow-up bugfixes were required:

```bash
git add <changed files>
git commit -m "fix: tighten bot action slot test flow"
```
