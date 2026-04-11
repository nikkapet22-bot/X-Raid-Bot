# Granular Pause Resume Restart All And Animated Actions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let pause/resume stop and continue from practical runtime action boundaries, add a bulk `Restart All` profile reset control, and add pulse-style motion to `Start`, `Raid NOW!`, and `Restart All`.

**Architecture:** Keep the existing worker-owned paused execution snapshot model, but extend it to capture finer-grained action boundaries inside runner and warmup flows instead of only whole-profile checkpoints. Add the bulk reset through the existing controller/worker profile-reset seam, and introduce a small reusable animated action button widget so motion stays isolated from the rest of `main_window.py`.

**Tech Stack:** PySide6, existing desktop worker/controller architecture, pytest

---

## File Map

- `raidbot/desktop/automation/input.py`
  - low-level runtime actions that need pause-aware before/after checkpoints
- `raidbot/desktop/automation/runner.py`
  - normal action flow and slot 1 reply flow; needs finer-grained resumable boundaries
- `raidbot/desktop/worker.py`
  - stores paused execution snapshots, resumes interrupted work, and owns bulk profile reset behavior
- `raidbot/desktop/controller.py`
  - exposes `reset_all_raid_profiles()` through the runner thread
- `raidbot/desktop/main_window.py`
  - profiles dashboard header, `RaidProfileCard`, and wiring for the new bulk reset button
- `raidbot/desktop/animated_button.py`
  - new focused widget for hover/press/pulse motion on high-value actions
- `raidbot/desktop/theme.py`
  - static color/state support for the animated buttons
- `tests/desktop/automation/test_runner.py`
  - fine-grained resume behavior for slot execution and slot 1 reply
- `tests/desktop/test_worker.py`
  - paused execution snapshots and bulk reset worker behavior
- `tests/desktop/test_controller.py`
  - controller wiring for `reset_all_raid_profiles()`
- `tests/desktop/test_main_window.py`
  - `Restart All` button placement/wiring and animated button usage on `Start` and `Raid NOW!`
- `tests/desktop/test_app.py`
  - stylesheet expectations for any new animated/static button selectors
- `pyproject.toml`
  - version bump
- `raidbot/__init__.py`
  - version bump
- `tests/desktop/test_packaging.py`
  - versioned artifact expectations

### Task 1: Add Bulk `Restart All` Profile Reset

**Files:**
- Modify: `tests/desktop/test_controller.py`
- Modify: `tests/desktop/test_worker.py`
- Modify: `tests/desktop/test_main_window.py`
- Modify: `raidbot/desktop/controller.py`
- Modify: `raidbot/desktop/worker.py`
- Modify: `raidbot/desktop/main_window.py`

- [ ] **Step 1: Write the failing controller test**

Add a test in `tests/desktop/test_controller.py` beside the single-profile reset tests:

```python
def test_controller_reset_all_raid_profiles_submits_worker_command(qtbot) -> None:
    controller = DesktopController(...)
    controller.start_bot()

    controller.reset_all_raid_profiles()

    assert created["worker"].reset_all_raid_profiles_calls == 1
```

- [ ] **Step 2: Run the controller test to verify it fails**

Run: `python -m pytest -q tests\desktop\test_controller.py -k "reset_all_raid_profiles"`

Expected: FAIL with missing controller method / missing fake worker hook.

- [ ] **Step 3: Write the failing worker test**

Add a worker test in `tests/desktop/test_worker.py` near `test_worker_reset_raid_profile_turns_red_profile_green`:

```python
def test_worker_reset_all_raid_profiles_turns_all_profiles_green(tmp_path) -> None:
    storage = FakeStorage(
        DesktopAppState(
            raid_profile_states=(
                RaidProfileState("Default", "George", "red", "login required"),
                RaidProfileState("Profile 3", "Maria", "red", "not_logged_in"),
                RaidProfileState("Profile 5", "John", "green", None),
            )
        ),
        base_dir=tmp_path,
    )
    worker, *_ = build_worker(storage, events, timestamp, config=build_config(...))

    worker.reset_all_raid_profiles()

    assert worker.state.raid_profile_states == (
        RaidProfileState("Default", "George", "green", None),
        RaidProfileState("Profile 3", "Maria", "green", None),
        RaidProfileState("Profile 5", "John", "green", None),
    )
```

- [ ] **Step 4: Run the worker test to verify it fails**

Run: `python -m pytest -q tests\desktop\test_worker.py -k "reset_all_raid_profiles"`

Expected: FAIL with missing worker method.

- [ ] **Step 5: Write the failing main window test**

Add a dashboard UI test in `tests/desktop/test_main_window.py`:

```python
def test_main_window_profiles_header_renders_restart_all_button(qtbot) -> None:
    window = build_window(controller, storage)
    qtbot.addWidget(window)

    assert window.restart_all_profiles_button.text() == "Restart All"
```

and a routing test:

```python
def test_main_window_restart_all_profiles_button_routes_to_controller(qtbot) -> None:
    qtbot.mouseClick(window.restart_all_profiles_button, Qt.MouseButton.LeftButton)
    assert controller.reset_all_raid_profiles_calls == 1
```

- [ ] **Step 6: Run the main window tests to verify they fail**

Run: `python -m pytest -q tests\desktop\test_main_window.py -k "restart_all_profiles"`

Expected: FAIL because the button and controller hook do not exist yet.

- [ ] **Step 7: Implement the controller, worker, and main window changes**

Implement only the missing bulk-reset behavior:

- add `reset_all_raid_profiles()` to `raidbot/desktop/controller.py`
- add `reset_all_raid_profiles()` to `raidbot/desktop/worker.py`
- add `Restart All` button to the far right of the Profiles section in `raidbot/desktop/main_window.py`

- [ ] **Step 8: Run the focused reset-all tests to verify they pass**

Run: `python -m pytest -q tests\desktop\test_controller.py -k "reset_all_raid_profiles" tests\desktop\test_worker.py -k "reset_all_raid_profiles" tests\desktop\test_main_window.py -k "restart_all_profiles"`

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add tests/desktop/test_controller.py tests/desktop/test_worker.py tests/desktop/test_main_window.py raidbot/desktop/controller.py raidbot/desktop/worker.py raidbot/desktop/main_window.py
git commit -m "feat: add bulk profile reset control"
```

### Task 2: Add a Reusable Animated Action Button Widget

**Files:**
- Create: `raidbot/desktop/animated_button.py`
- Modify: `raidbot/desktop/main_window.py`
- Modify: `raidbot/desktop/theme.py`
- Modify: `tests/desktop/test_main_window.py`
- Modify: `tests/desktop/test_app.py`

- [ ] **Step 1: Write the failing main window test for animated action buttons**

Add tests in `tests/desktop/test_main_window.py`:

```python
def test_main_window_uses_animated_button_for_start_and_restart_all(qtbot) -> None:
    window = build_window(controller, storage)
    qtbot.addWidget(window)

    from raidbot.desktop.animated_button import AttentionPulseButton

    assert isinstance(window.start_button, AttentionPulseButton)
    assert isinstance(window.restart_all_profiles_button, AttentionPulseButton)
    assert isinstance(window.raid_profile_cards["Profile 3"].raid_now_button, AttentionPulseButton)
```

and:

```python
def test_main_window_animated_buttons_do_not_pulse_while_disabled(qtbot) -> None:
    card = window.raid_profile_cards["Profile 3"]
    assert card.raid_now_button.isEnabled() is False
    assert card.raid_now_button.pulse_enabled() is False
```

- [ ] **Step 2: Run the main window animation tests to verify they fail**

Run: `python -m pytest -q tests\desktop\test_main_window.py -k "animated_button or pulse"`

Expected: FAIL because the widget class and wiring do not exist.

- [ ] **Step 3: Write the failing stylesheet/static support test**

Add a focused assertion in `tests/desktop/test_app.py`:

```python
def test_build_application_stylesheet_contains_attention_button_support() -> None:
    css = build_application_stylesheet()
    assert "attentionPulseButton" in css
```

- [ ] **Step 4: Run the stylesheet test to verify it fails**

Run: `python -m pytest -q tests\desktop\test_app.py -k "attention_button_support"`

Expected: FAIL because the selector does not exist.

- [ ] **Step 5: Implement the animated button widget and wire it in**

Implement:

- new `AttentionPulseButton` in `raidbot/desktop/animated_button.py`
- use it for:
  - `Start`
  - `Restart All`
  - `Raid NOW!`
- add minimal theme support in `raidbot/desktop/theme.py`

- [ ] **Step 6: Run the focused animation tests to verify they pass**

Run: `python -m pytest -q tests\desktop\test_main_window.py -k "animated_button or pulse" tests\desktop\test_app.py -k "attention_button_support"`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add raidbot/desktop/animated_button.py raidbot/desktop/main_window.py raidbot/desktop/theme.py tests/desktop/test_main_window.py tests/desktop/test_app.py
git commit -m "feat: add animated high-priority action buttons"
```

### Task 3: Add Finer-Grained Pause Boundaries for Standard Steps

**Files:**
- Modify: `tests/desktop/automation/test_runner.py`
- Modify: `tests/desktop/test_worker.py`
- Modify: `raidbot/desktop/automation/runner.py`
- Modify: `raidbot/desktop/worker.py`

- [ ] **Step 1: Write the failing runner test for resumable click-confirm boundaries**

Add a runner test in `tests/desktop/automation/test_runner.py` that proves a stopped run can resume from inside a normal step boundary:

```python
def test_sequence_runner_resumes_step_from_saved_action_boundary() -> None:
    runner = SequenceRunner(...)
    runner.request_stop()

    result = runner.run_sequence(sequence, selected_window=window, start_step_index=0)

    assert result.status == "stopped"
    assert result.step_index == 0
    assert result.resume_phase == "post_click_confirmation"
```

Use the real naming you introduce for the resumable phase field.

- [ ] **Step 2: Run the runner test to verify it fails**

Run: `python -m pytest -q tests\desktop\automation\test_runner.py -k "saved_action_boundary"`

Expected: FAIL because runner results/snapshots do not carry a finer-grained phase yet.

- [ ] **Step 3: Write the failing worker test for resumed auto/manual execution**

Add a worker test in `tests/desktop/test_worker.py`:

```python
def test_worker_resume_continues_interrupted_profile_from_saved_boundary(tmp_path) -> None:
    worker, *_ = build_worker(...)
    worker.toggle_pause_resume()

    assert worker._paused_execution is not None
    assert worker._paused_execution.profile_snapshot is not None
    assert worker._paused_execution.profile_snapshot.mode == "sequence"
    assert worker._paused_execution.profile_snapshot.action_phase == "post_click_confirmation"
```

- [ ] **Step 4: Run the worker test to verify it fails**

Run: `python -m pytest -q tests\desktop\test_worker.py -k "saved_boundary"`

Expected: FAIL because worker snapshots do not yet track the finer-grained phase.

- [ ] **Step 5: Implement the minimal runner and worker snapshot changes**

Implement only:

- a finer-grained action phase in the runner stop result / resume path
- worker snapshot storage and restore for the standard non-slot-1 step path

- [ ] **Step 6: Run the focused standard pause/resume tests to verify they pass**

Run: `python -m pytest -q tests\desktop\automation\test_runner.py -k "saved_action_boundary" tests\desktop\test_worker.py -k "saved_boundary"`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add tests/desktop/automation/test_runner.py tests/desktop/test_worker.py raidbot/desktop/automation/runner.py raidbot/desktop/worker.py
git commit -m "feat: resume interrupted runs from standard step boundaries"
```

### Task 4: Add Finer-Grained Pause Boundaries for Slot 1 Reply And Warmup

**Files:**
- Modify: `tests/desktop/automation/test_runner.py`
- Modify: `tests/desktop/test_worker.py`
- Modify: `raidbot/desktop/automation/runner.py`
- Modify: `raidbot/desktop/worker.py`
- Modify: `raidbot/desktop/automation/input.py`

- [ ] **Step 1: Write the failing runner test for slot 1 reply resume**

Add a test in `tests/desktop/automation/test_runner.py` for the slot 1 flow:

```python
def test_slot_1_reply_resume_continues_from_text_pasted_before_image_paste() -> None:
    result = runner.run_sequence(sequence, selected_window=window, start_step_index=0)

    assert result.status == "stopped"
    assert result.resume_phase == "slot_1_image_paste"
```

- [ ] **Step 2: Run the slot 1 runner test to verify it fails**

Run: `python -m pytest -q tests\desktop\automation\test_runner.py -k "slot_1_reply_resume"`

Expected: FAIL because slot 1 phases are not resumable yet.

- [ ] **Step 3: Write the failing worker test for warmup scroll resume**

Add a warmup-specific test in `tests/desktop/test_worker.py`:

```python
def test_worker_resume_warmup_continues_from_remaining_scrolls(tmp_path) -> None:
    worker, *_ = build_worker(...)

    assert worker._paused_execution.profile_snapshot.remaining_scroll_amounts == (...)
```

- [ ] **Step 4: Run the warmup worker test to verify it fails**

Run: `python -m pytest -q tests\desktop\test_worker.py -k "remaining_scrolls"`

Expected: FAIL because the interrupted warmup boundary is not fine-grained enough for this case.

- [ ] **Step 5: Implement the slot 1 and warmup resume phases**

Implement the minimal pause-aware action phases in:

- `raidbot/desktop/automation/input.py`
- `raidbot/desktop/automation/runner.py`
- `raidbot/desktop/worker.py`

Use before/after checkpoints around:

- `move_click`
- `paste_text`
- `paste_image_file`
- scroll loops
- close-window / page-exit actions

- [ ] **Step 6: Run the focused slot 1 and warmup pause/resume tests to verify they pass**

Run: `python -m pytest -q tests\desktop\automation\test_runner.py -k "slot_1_reply_resume" tests\desktop\test_worker.py -k "remaining_scrolls or warmup"`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add tests/desktop/automation/test_runner.py tests/desktop/test_worker.py raidbot/desktop/automation/input.py raidbot/desktop/automation/runner.py raidbot/desktop/worker.py
git commit -m "feat: resume slot 1 and warmup flows from fine-grained boundaries"
```

### Task 5: Finish Integration, Bump Version, And Verify

**Files:**
- Modify: `pyproject.toml`
- Modify: `raidbot/__init__.py`
- Modify: `tests/desktop/test_packaging.py`
- Verify: `tests/desktop/test_controller.py`
- Verify: `tests/desktop/test_main_window.py`
- Verify: `tests/desktop/test_worker.py`
- Verify: `tests/desktop/automation/test_runner.py`
- Verify: `tests/desktop/test_app.py`

- [ ] **Step 1: Update packaging/version expectations**

Bump the version in:

- `pyproject.toml`
- `raidbot/__init__.py`
- `tests/desktop/test_packaging.py`

- [ ] **Step 2: Run focused integration coverage**

Run:

```bash
python -m pytest -q tests\desktop\test_controller.py -k "reset_all_raid_profiles or pause_resume"
python -m pytest -q tests\desktop\test_main_window.py -k "restart_all_profiles or animated_button or pulse or raid_now"
python -m pytest -q tests\desktop\test_worker.py -k "reset_all_raid_profiles or saved_boundary or warmup or toggle_pause_resume"
python -m pytest -q tests\desktop\automation\test_runner.py -k "saved_action_boundary or slot_1_reply_resume"
python -m pytest -q tests\desktop\test_app.py -k "attention_button_support"
python -m pytest -q tests\desktop\test_packaging.py
```

Expected: PASS on the new focused slice.

- [ ] **Step 3: Commit the finishing integration pass**

```bash
git add pyproject.toml raidbot/__init__.py tests/desktop/test_packaging.py tests/desktop/test_controller.py tests/desktop/test_main_window.py tests/desktop/test_worker.py tests/desktop/automation/test_runner.py tests/desktop/test_app.py
git commit -m "feat: finish granular pause resume and dashboard recovery controls"
```

