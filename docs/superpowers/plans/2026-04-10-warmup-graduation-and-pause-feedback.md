# Warmup Graduation And Pause Feedback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make warmup profiles graduate automatically after 20 full cycles, show warmup progress in the profile card, fix queue semantics so one profile failure does not block the whole bot, and make user-pause versus true global stop states visually obvious.

**Architecture:** Keep the existing desktop app model. Persist one extra warmup counter per profile, update the worker to treat warmup graduation and per-profile failures correctly, and let the main window derive pause/stop overlays from queue state instead of rewriting the core bot runtime enums. This keeps the runtime behavior narrow while fixing the user-facing confusion.

**Tech Stack:** PySide6, existing desktop worker/controller/runtime, pytest

---

### Task 1: Persist warmup completed cycles and reset them when warmup is re-enabled

**Files:**
- Modify: `raidbot/desktop/models.py`
- Modify: `raidbot/desktop/storage.py`
- Modify: `raidbot/desktop/controller.py`
- Test: `tests/desktop/test_storage.py`
- Test: `tests/desktop/test_controller.py`

- [ ] **Step 1: Write the failing storage test**

Add coverage in `tests/desktop/test_storage.py` for:

```python
def test_storage_round_trips_warmup_completed_cycles(tmp_path) -> None:
    storage = DesktopStorage(tmp_path)
    config = build_config(
        raid_profiles=(
            RaidProfileConfig(
                "Profile 3",
                "Maria",
                True,
                warmup_enabled=True,
                warmup_cycle_index=2,
                warmup_completed_cycles=7,
            ),
        ),
    )

    storage.save_config(config)
    loaded = storage.load_config()

    assert loaded.raid_profiles[0].warmup_completed_cycles == 7
```

and:

```python
def test_storage_defaults_warmup_completed_cycles_to_zero(tmp_path) -> None:
    storage = DesktopStorage(tmp_path)
    storage.save_config(build_config())

    loaded = storage.load_config()

    assert loaded.raid_profiles[0].warmup_completed_cycles == 0
```

- [ ] **Step 2: Write the failing controller reset test**

Add coverage in `tests/desktop/test_controller.py` for:

```python
def test_controller_reenabling_warmup_resets_warmup_counters(qtbot) -> None:
    controller = build_controller_with_profile(
        qtbot,
        RaidProfileConfig(
            "Profile 3",
            "Maria",
            True,
            warmup_enabled=False,
            warmup_cycle_index=2,
            warmup_completed_cycles=12,
        ),
    )

    controller.set_raid_profile_action_overrides(
        "Profile 3",
        reply_enabled=False,
        like_enabled=False,
        repost_enabled=False,
        bookmark_enabled=False,
        warmup_enabled=True,
    )

    profile = controller.config.raid_profiles[0]
    assert profile.warmup_enabled is True
    assert profile.warmup_cycle_index == 0
    assert profile.warmup_completed_cycles == 0
```

- [ ] **Step 3: Run the focused storage/controller slice to verify failure**

Run: `python -m pytest -q tests\desktop\test_storage.py -k "warmup_completed_cycles" tests\desktop\test_controller.py -k "warmup_resets"`

Expected: FAIL because the model/storage/controller do not yet own `warmup_completed_cycles`.

- [ ] **Step 4: Add the persisted field and reset behavior**

Update:

- `raidbot/desktop/models.py`
  - add `warmup_completed_cycles: int = 0` to `RaidProfileConfig`
- `raidbot/desktop/storage.py`
  - save/load `warmup_completed_cycles`
  - normalize missing values to `0`
- `raidbot/desktop/controller.py`
  - when `warmup_enabled` flips from `False` to `True`, reset:
    - `warmup_cycle_index = 0`
    - `warmup_completed_cycles = 0`

- [ ] **Step 5: Run the focused storage/controller slice again**

Run: `python -m pytest -q tests\desktop\test_storage.py -k "warmup_completed_cycles" tests\desktop\test_controller.py -k "warmup_resets"`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add raidbot/desktop/models.py raidbot/desktop/storage.py raidbot/desktop/controller.py tests/desktop/test_storage.py tests/desktop/test_controller.py
git commit -m "feat: persist warmup completed cycle counters"
```

### Task 2: Graduate warmup profiles after 20 full cycles

**Files:**
- Modify: `raidbot/desktop/worker.py`
- Test: `tests/desktop/test_worker.py`

- [ ] **Step 1: Write the failing worker graduation tests**

Add coverage in `tests/desktop/test_worker.py` for:

```python
def test_worker_graduates_warmup_profile_after_twentieth_completed_cycle(tmp_path) -> None:
    profile = RaidProfileConfig(
        "Default",
        "George",
        True,
        reply_enabled=False,
        like_enabled=False,
        repost_enabled=False,
        bookmark_enabled=False,
        warmup_enabled=True,
        warmup_cycle_index=2,
        warmup_completed_cycles=19,
    )
    worker = build_worker_with_warmup_real_action_success(tmp_path, profile)

    worker._handle_message(build_message("Likes 10 | 8 [%]\n\nhttps://x.com/i/status/654"))

    graduated = worker.config.raid_profiles[0]
    assert graduated.warmup_enabled is False
    assert graduated.warmup_cycle_index == 0
    assert graduated.warmup_completed_cycles == 0
    assert graduated.reply_enabled is True
    assert graduated.like_enabled is True
    assert graduated.repost_enabled is True
    assert graduated.bookmark_enabled is False
```

and:

```python
def test_worker_failed_warmup_real_action_does_not_advance_completed_cycles(tmp_path) -> None:
    profile = RaidProfileConfig(
        "Default",
        "George",
        True,
        warmup_enabled=True,
        warmup_cycle_index=2,
        warmup_completed_cycles=6,
    )
    worker = build_worker_with_warmup_real_action_failure(tmp_path, profile)

    worker._handle_message(build_message("Likes 10 | 8 [%]\n\nhttps://x.com/i/status/654"))

    current = worker.config.raid_profiles[0]
    assert current.warmup_enabled is True
    assert current.warmup_cycle_index == 2
    assert current.warmup_completed_cycles == 6
```

- [ ] **Step 2: Run the focused worker warmup slice to verify failure**

Run: `python -m pytest -q tests\desktop\test_worker.py -k "graduates_warmup_profile or warmup_completed_cycles"`

Expected: FAIL because the worker does not yet count completed warmup cycles or graduate the profile.

- [ ] **Step 3: Implement warmup completed-cycle advancement and graduation**

In `raidbot/desktop/worker.py`:

- increment `warmup_completed_cycles` only after the third warmup step succeeds
- if completed cycles are still below `20`, advance normally
- if the twentieth full cycle completes:
  - disable warmup
  - reset `warmup_cycle_index`
  - reset `warmup_completed_cycles`
  - enable `reply_enabled`, `like_enabled`, `repost_enabled`
  - disable `bookmark_enabled`
  - persist config immediately
- do not advance counters on failure

- [ ] **Step 4: Run the focused worker warmup slice again**

Run: `python -m pytest -q tests\desktop\test_worker.py -k "graduates_warmup_profile or warmup_completed_cycles"`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/desktop/worker.py tests/desktop/test_worker.py
git commit -m "feat: graduate warmup profiles after 20 cycles"
```

### Task 3: Keep profile failures local instead of pausing the whole auto queue

**Files:**
- Modify: `raidbot/desktop/automation/autorun.py`
- Modify: `raidbot/desktop/worker.py`
- Test: `tests/desktop/automation/test_autorun.py`
- Test: `tests/desktop/test_worker.py`

- [ ] **Step 1: Write the failing queue-semantics tests**

Add coverage in `tests/desktop/automation/test_autorun.py` for:

```python
def test_autorun_processor_profile_execution_failure_does_not_pause_future_admission() -> None:
    processor = build_processor_with_execution_failure("ui_did_not_change")
    item = PendingRaidWorkItem(normalized_url="https://x.com/i/status/1", trace_id="raid-1")

    processor.admit(item)
    processor.process_next()

    accepted = processor.admit(
        PendingRaidWorkItem(normalized_url="https://x.com/i/status/2", trace_id="raid-2")
    )

    assert accepted is True
    assert processor.state in {"queued", "idle"}
```

Add worker coverage in `tests/desktop/test_worker.py` for:

```python
def test_worker_one_profile_failure_does_not_block_later_raid_items(tmp_path) -> None:
    worker = build_worker_with_one_profile_failure_and_one_success(tmp_path)

    first = worker._handle_message(build_message("Likes 10 | 8 [%]\n\nhttps://x.com/i/status/111"))
    second = worker._handle_message(build_message("Likes 10 | 8 [%]\n\nhttps://x.com/i/status/222"))

    assert first.kind == "job_detected"
    assert second.kind == "job_detected"
    assert worker.state.automation_queue_state != "paused"
    assert worker.state.automation_last_error != "auto_run_paused"
```

- [ ] **Step 2: Run the focused autorun/worker slice to verify failure**

Run: `python -m pytest -q tests\desktop\automation\test_autorun.py -k "future_admission" tests\desktop\test_worker.py -k "one_profile_failure_does_not_block"`

Expected: FAIL because ordinary execution failures still pause the queue.

- [ ] **Step 3: Narrow queue-level pause to true global blockers**

In `raidbot/desktop/automation/autorun.py`:

- keep queue-level `paused` only for true global blockers such as:
  - `auto_run_disabled`
  - `default_sequence_missing`
  - automation runtime unavailable / similar app-wide blockers
- do not transition to queue-level `paused` for ordinary per-profile/per-item execution failures

In `raidbot/desktop/worker.py`:

- keep per-profile failures local
- continue the current raid across the remaining profiles
- allow later Telegram raid items to continue normally

- [ ] **Step 4: Run the focused autorun/worker slice again**

Run: `python -m pytest -q tests\desktop\automation\test_autorun.py -k "future_admission" tests\desktop\test_worker.py -k "one_profile_failure_does_not_block"`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/desktop/automation/autorun.py raidbot/desktop/worker.py tests/desktop/automation/test_autorun.py tests/desktop/test_worker.py
git commit -m "fix: keep profile automation failures local"
```

### Task 4: Add warmup progress bar and explicit pause/stop overlays in the main window

**Files:**
- Modify: `raidbot/desktop/main_window.py`
- Modify: `raidbot/desktop/theme.py`
- Test: `tests/desktop/test_main_window.py`
- Test: `tests/desktop/test_app.py`

- [ ] **Step 1: Write the failing UI tests**

Add coverage in `tests/desktop/test_main_window.py` for:

```python
def test_main_window_user_pause_renders_paused_top_state_and_orange_profiles(qtbot) -> None:
    window, controller = build_window(qtbot)

    controller.botStateChanged.emit("running")
    controller.automationQueueStateChanged.emit("suspended")

    assert window.bot_state_label.text() == "Paused"
    assert window._bot_dot.property("stateVariant") == "active"
    assert window.raid_profile_cards["Profile 3"].property("queueOverlay") == "paused"
```

```python
def test_main_window_global_block_renders_stopped_top_state_and_red_profiles(qtbot) -> None:
    window, controller = build_window(qtbot)

    controller.botStateChanged.emit("running")
    controller.automationQueueStateChanged.emit("paused")

    assert window.bot_state_label.text() == "Stopped"
    assert window._bot_dot.property("stateVariant") == "error"
    assert window.raid_profile_cards["Profile 3"].property("queueOverlay") == "stopped"
```

```python
def test_main_window_warmup_profile_card_shows_progress_percentage(qtbot) -> None:
    window = build_window_with_warmup_profile(qtbot, completed_cycles=5)
    card = window.raid_profile_cards["Default"]

    assert card.warmup_progress_bar.isVisible()
    assert card.warmup_progress_bar.value() == 25
```

- [ ] **Step 2: Run the focused main-window slice to verify failure**

Run: `python -m pytest -q tests\desktop\test_main_window.py -k "queueOverlay or warmup_profile_card_shows_progress_percentage or paused_top_state or global_block"`

Expected: FAIL because the top panel still mirrors raw bot state and warmup cards have no progress bar.

- [ ] **Step 3: Implement the overlays and progress bar**

In `raidbot/desktop/main_window.py`:

- add a warmup progress widget to `RaidProfileCard`
- show it only when `warmup_enabled` is true
- compute progress as `int(round((completed_cycles / 20) * 100))`
- derive displayed bot state from queue state:
  - `suspended` -> `Paused`
  - `paused` -> `Stopped`
  - otherwise use real bot state
- add profile-card queue overlays:
  - orange paused overlay for `suspended`
  - red stopped overlay for `paused`

In `raidbot/desktop/theme.py`:

- style the progress bar to match warmup cards
- add clear visual treatment for orange paused and red stopped overlays

- [ ] **Step 4: Run the focused UI slice again**

Run: `python -m pytest -q tests\desktop\test_main_window.py -k "queueOverlay or warmup_profile_card_shows_progress_percentage or paused_top_state or global_block" tests\desktop\test_app.py -k "stylesheet"`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/desktop/main_window.py raidbot/desktop/theme.py tests/desktop/test_main_window.py tests/desktop/test_app.py
git commit -m "feat: show pause stop overlays and warmup progress"
```

### Task 5: Bump version and run the release-facing regression slice

**Files:**
- Modify: `pyproject.toml`
- Modify: `raidbot/__init__.py`
- Modify: `tests/desktop/test_packaging.py`

- [ ] **Step 1: Update version expectations**

Adjust packaging/version expectations from `2.2.0` to the next version used for this pass.

- [ ] **Step 2: Bump the app version**

Update:

- `pyproject.toml`
- `raidbot/__init__.py`
- `tests/desktop/test_packaging.py`

- [ ] **Step 3: Run the release-facing regression slice**

Run:

```bash
python -m pytest -q tests\desktop\test_packaging.py
python -m pytest -q tests\desktop\test_storage.py -k "warmup_completed_cycles"
python -m pytest -q tests\desktop\test_controller.py -k "warmup_resets"
python -m pytest -q tests\desktop\automation\test_autorun.py -k "future_admission"
python -m pytest -q tests\desktop\test_worker.py -k "warmup_completed_cycles or one_profile_failure_does_not_block or raid_now or hotkey"
python -m pytest -q tests\desktop\test_main_window.py -k "queueOverlay or warmup_profile_card_shows_progress_percentage or paused_top_state or global_block"
```

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml raidbot/__init__.py tests/desktop/test_packaging.py
git commit -m "chore: bump version after warmup graduation and pause feedback"
```
