# Slot 1 Finish Delay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a slot-1-only `Finish Delay` setting to Bot Actions, remove the visible slot labels, and use the configured delay instead of the hardcoded slot-1 finish wait.

**Architecture:** Extend `DesktopAppConfig` with a persisted `slot_1_finish_delay_seconds` value, surface that setting only on the slot 1 Bot Actions card, and thread it into the slot-1 finish wait path in the automation runner. Keep the change narrow: no per-slot generalization and no timing changes for slots 2/3/4.

**Tech Stack:** Python, PySide6, existing desktop config/storage/controller architecture, pytest/pytest-qt

---

## File Map

- Modify: `raidbot/desktop/models.py`
  - Add `slot_1_finish_delay_seconds` to `DesktopAppConfig`
- Modify: `raidbot/desktop/storage.py`
  - Save/load the new config value with a default of `2`
- Modify: `raidbot/desktop/bot_actions/page.py`
  - Remove visible `Slot 1/2/3/4` labels
  - Add the slot-1-only `Finish Delay` input and emit change events
- Modify: `raidbot/desktop/controller.py`
  - Persist `slot_1_finish_delay_seconds` changes
- Modify: `raidbot/desktop/automation/runner.py`
  - Replace the hardcoded slot-1 finish wait with the configured value
- Modify: `raidbot/desktop/bot_actions/sequence.py`
  - Thread slot-1 finish delay into the sequence/step data if needed by the runner path
- Test: `tests/desktop/test_storage.py`
- Test: `tests/desktop/bot_actions/test_page.py`
- Test: `tests/desktop/test_controller.py`
- Test: `tests/desktop/automation/test_runner.py`

### Task 1: Persist Slot 1 Finish Delay In Config

**Files:**
- Modify: `raidbot/desktop/models.py`
- Modify: `raidbot/desktop/storage.py`
- Test: `tests/desktop/test_storage.py`

- [ ] **Step 1: Write the failing storage/config tests**

Add focused tests in `tests/desktop/test_storage.py` for:
- defaulting `slot_1_finish_delay_seconds` to `2` when missing
- persisting a non-default value like `4`

- [ ] **Step 2: Run the focused storage test to verify it fails**

Run: `python -m pytest -q tests\desktop\test_storage.py -k "slot_1_finish_delay_seconds"`
Expected: FAIL because the config model/storage do not know about `slot_1_finish_delay_seconds`

- [ ] **Step 3: Add the minimal config/storage implementation**

In `raidbot/desktop/models.py`:
- add `slot_1_finish_delay_seconds: int` to `DesktopAppConfig`
- accept it in `__init__`
- default it to `2`

In `raidbot/desktop/storage.py`:
- include the value in `_config_to_data`
- load it in `_config_from_data`
- default to `2` when the saved config does not contain it

- [ ] **Step 4: Run the focused storage test to verify it passes**

Run: `python -m pytest -q tests\desktop\test_storage.py -k "slot_1_finish_delay_seconds"`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/desktop/models.py raidbot/desktop/storage.py tests/desktop/test_storage.py
git commit -m "feat: persist slot 1 finish delay"
```

### Task 2: Update Bot Actions UI

**Files:**
- Modify: `raidbot/desktop/bot_actions/page.py`
- Test: `tests/desktop/bot_actions/test_page.py`

- [ ] **Step 1: Write the failing Bot Actions page tests**

Add focused tests in `tests/desktop/bot_actions/test_page.py` for:
- slot labels (`Slot 1/2/3/4`) are no longer shown
- slot 1 shows a `Finish Delay` field
- slots 2/3/4 do not show that field
- changing slot 1 delay emits the expected signal/value

- [ ] **Step 2: Run the focused Bot Actions page tests to verify they fail**

Run: `python -m pytest -q tests\desktop\bot_actions\test_page.py -k "finish_delay or slot_label"`
Expected: FAIL because the page still shows slot labels and has no finish-delay control

- [ ] **Step 3: Add the minimal Bot Actions page implementation**

In `raidbot/desktop/bot_actions/page.py`:
- remove visible slot label text from card headers
- add a compact integer input labeled `Finish Delay` to slot 1 only
- initialize it from config
- emit a dedicated signal when it changes

Keep slots 2/3/4 unchanged except for the removed header label text.

- [ ] **Step 4: Run the focused Bot Actions page tests to verify they pass**

Run: `python -m pytest -q tests\desktop\bot_actions\test_page.py -k "finish_delay or slot_label"`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/desktop/bot_actions/page.py tests/desktop/bot_actions/test_page.py
git commit -m "feat: add slot 1 finish delay control"
```

### Task 3: Persist UI Changes Through Controller

**Files:**
- Modify: `raidbot/desktop/controller.py`
- Test: `tests/desktop/test_controller.py`

- [ ] **Step 1: Write the failing controller test**

Add a focused test in `tests/desktop/test_controller.py` proving that changing the slot-1 finish delay updates the saved config without forcing sender resolution.

- [ ] **Step 2: Run the focused controller test to verify it fails**

Run: `python -m pytest -q tests\desktop\test_controller.py -k "slot_1_finish_delay"`
Expected: FAIL because the controller has no persistence path for the new field

- [ ] **Step 3: Add the minimal controller implementation**

In `raidbot/desktop/controller.py`:
- add a `set_slot_1_finish_delay_seconds(...)` method
- persist the updated config using the existing `_persist_config(..., resolve_sender_entries=False)` path

- [ ] **Step 4: Run the focused controller test to verify it passes**

Run: `python -m pytest -q tests\desktop\test_controller.py -k "slot_1_finish_delay"`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/desktop/controller.py tests/desktop/test_controller.py
git commit -m "feat: persist slot 1 finish delay from controller"
```

### Task 4: Use Configured Finish Delay In Runner

**Files:**
- Modify: `raidbot/desktop/automation/runner.py`
- Modify: `raidbot/desktop/bot_actions/sequence.py`
- Test: `tests/desktop/automation/test_runner.py`

- [ ] **Step 1: Write the failing runner test**

Add a focused test in `tests/desktop/automation/test_runner.py` proving that slot 1 uses the configured finish delay (for example `4s`) instead of the old hardcoded `2.0s`.

- [ ] **Step 2: Run the focused runner test to verify it fails**

Run: `python -m pytest -q tests\desktop\automation\test_runner.py -k "configured_finish_delay"`
Expected: FAIL because the runner still sleeps the hardcoded `2.0s`

- [ ] **Step 3: Add the minimal runner implementation**

In `raidbot/desktop/bot_actions/sequence.py` and/or `raidbot/desktop/automation/runner.py`:
- thread the configured `slot_1_finish_delay_seconds` value into the slot-1 finish path
- replace `_SLOT_1_FINISH_POST_CLICK_DELAY_SECONDS = 2.0` usage with the configured value

Do not alter slots 2/3/4 or other step timings.

- [ ] **Step 4: Run the focused runner test to verify it passes**

Run: `python -m pytest -q tests\desktop\automation\test_runner.py -k "configured_finish_delay"`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/desktop/automation/runner.py raidbot/desktop/bot_actions/sequence.py tests/desktop/automation/test_runner.py
git commit -m "feat: use configured slot 1 finish delay"
```

### Task 5: Final Verification

**Files:**
- Verify: `tests/desktop/test_storage.py`
- Verify: `tests/desktop/bot_actions/test_page.py`
- Verify: `tests/desktop/test_controller.py`
- Verify: `tests/desktop/automation/test_runner.py`

- [ ] **Step 1: Run the full focused verification slice**

Run:

```bash
python -m pytest -q tests\desktop\test_storage.py tests\desktop\bot_actions\test_page.py tests\desktop\test_controller.py tests\desktop\automation\test_runner.py
```

Expected: PASS

- [ ] **Step 2: Smoke-check related desktop UI slice**

Run:

```bash
python -m pytest -q tests\desktop\test_main_window.py -k "bot_actions or config"
```

Expected: PASS or no relevant failures

- [ ] **Step 3: Commit final polish if needed**

```bash
git add raidbot/desktop/models.py raidbot/desktop/storage.py raidbot/desktop/bot_actions/page.py raidbot/desktop/controller.py raidbot/desktop/automation/runner.py raidbot/desktop/bot_actions/sequence.py tests/desktop/test_storage.py tests/desktop/bot_actions/test_page.py tests/desktop/test_controller.py tests/desktop/automation/test_runner.py
git commit -m "feat: add slot 1 finish delay setting"
```
