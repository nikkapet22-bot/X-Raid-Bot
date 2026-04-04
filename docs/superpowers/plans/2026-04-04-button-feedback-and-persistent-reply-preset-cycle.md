# Button Feedback And Persistent Reply Preset Cycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every desktop-app button family react clearly on hover and click, and make slot 1 reply presets rotate without reuse until the pool is exhausted across raids and app restarts.

**Architecture:** Keep the button work centralized in the shared Qt stylesheet so interaction feedback stays consistent across the app. Persist slot 1 preset-cycle state in `DesktopAppState`, thread that state through the preset chooser, and let the worker update it as raids are prepared so preset rotation survives separate runs and restarts.

**Tech Stack:** Python, PySide6, dataclasses, desktop storage JSON persistence, pytest

---

### Task 1: Complete Custom Button Hover And Pressed Feedback

**Files:**
- Modify: `raidbot/desktop/theme.py`
- Test: `tests/desktop/test_app.py`

- [ ] **Step 1: Write the failing stylesheet assertions**

Add or extend tests in `tests/desktop/test_app.py` to assert that the stylesheet includes explicit `:hover` and `:pressed` blocks for the custom button families that currently override the base button behavior:

```python
assert "QPushButton#shellTabButton:hover" in stylesheet
assert "QPushButton#shellTabButton:pressed" in stylesheet
assert 'QPushButton[variant="quiet"]:hover' in stylesheet
assert 'QPushButton[variant="quiet"]:pressed' in stylesheet
```

- [ ] **Step 2: Run the stylesheet test to verify it fails**

Run: `python -m pytest -q tests\desktop\test_app.py -k "stylesheet_contains_dark_surface_and_accent"`

Expected: FAIL because at least one custom family is missing an explicit `:pressed` rule.

- [ ] **Step 3: Add the minimal stylesheet rules**

Update `raidbot/desktop/theme.py` so custom button selectors that override base behavior also define explicit pressed feedback.

Target shape:

```python
QPushButton#shellTabButton:pressed {{
    background-color: #081223;
    color: {TEXT};
    border-color: {ACCENT};
}}
QPushButton[variant="quiet"]:pressed {{
    background-color: #0a1627;
    color: {TEXT};
    border-color: transparent;
}}
```

Reuse the repo’s existing dark/accent palette rather than inventing new colors.

- [ ] **Step 4: Run the stylesheet test to verify it passes**

Run: `python -m pytest -q tests\desktop\test_app.py -k "stylesheet_contains_dark_surface_and_accent"`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/desktop/test_app.py raidbot/desktop/theme.py
git commit -m "fix: complete custom button interaction states"
```

### Task 2: Persist Slot 1 Preset Cycle State

**Files:**
- Modify: `raidbot/desktop/models.py`
- Modify: `raidbot/desktop/storage.py`
- Test: `tests/desktop/test_storage.py`

- [ ] **Step 1: Write the failing storage round-trip test**

Add a test in `tests/desktop/test_storage.py` that saves and reloads desktop state containing slot 1 preset-cycle memory:

```python
state = DesktopAppState(slot_1_used_preset_ids=("preset-2", "preset-3"))
storage.save_state(state)
reloaded = storage.load_state()
assert reloaded.slot_1_used_preset_ids == ("preset-2", "preset-3")
```

Also add a normalization case showing stale preset ids are dropped when the current slot 1 preset pool no longer contains them.

- [ ] **Step 2: Run the storage test to verify it fails**

Run: `python -m pytest -q tests\desktop\test_storage.py -k "slot_1_used_preset_ids or stale_preset_ids"`

Expected: FAIL because `DesktopAppState` and storage serialization do not yet know about the new field.

- [ ] **Step 3: Add the new state field and persistence**

Update `raidbot/desktop/models.py`:

```python
@dataclass
class DesktopAppState:
    ...
    slot_1_used_preset_ids: tuple[str, ...] = ()
```

Update `raidbot/desktop/storage.py` to:
- serialize that field in `_state_to_data`
- load it in `_state_from_data`
- normalize it in `_normalize_loaded_state` against the current slot 1 preset ids from config

- [ ] **Step 4: Run the storage test to verify it passes**

Run: `python -m pytest -q tests\desktop\test_storage.py -k "slot_1_used_preset_ids or stale_preset_ids"`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/desktop/test_storage.py raidbot/desktop/models.py raidbot/desktop/storage.py
git commit -m "feat: persist slot 1 preset cycle state"
```

### Task 3: Make The Slot 1 Preset Chooser Consume And Return Cycle State

**Files:**
- Modify: `raidbot/desktop/bot_actions/sequence.py`
- Test: `tests/desktop/bot_actions/test_sequence.py`

- [ ] **Step 1: Write the failing chooser-state tests**

Add tests in `tests/desktop/bot_actions/test_sequence.py` for two behaviors:

1. Existing used ids are honored across separate chooser calls:

```python
selected, used_ids = choose_slot_1_preset_with_cycle(
    presets,
    used_ids=("preset-1",),
    choose_preset=lambda available: available[0],
)
assert selected.id == "preset-2"
assert used_ids == ("preset-1", "preset-2")
```

2. Exhausted pools reset cleanly:

```python
selected, used_ids = choose_slot_1_preset_with_cycle(
    presets,
    used_ids=("preset-1", "preset-2", "preset-3"),
    choose_preset=lambda available: available[0],
)
assert selected.id == "preset-1"
assert used_ids == ("preset-1",)
```

- [ ] **Step 2: Run the sequence test to verify it fails**

Run: `python -m pytest -q tests\desktop\bot_actions\test_sequence.py -k "cycle or preset_chooser"`

Expected: FAIL because the chooser only keeps in-memory state inside one closure.

- [ ] **Step 3: Add the minimal chooser API**

Refactor `raidbot/desktop/bot_actions/sequence.py` so slot 1 preset selection can work from an explicit used-id set and return the updated set.

One acceptable shape:

```python
def choose_slot_1_preset_with_cycle(
    presets: Sequence[BotActionPreset],
    *,
    used_ids: Sequence[str],
    choose_preset=choice,
) -> tuple[BotActionPreset, tuple[str, ...]]:
    ...
```

Keep the current no-repeat-until-exhausted behavior, but make it deterministic from the passed-in state rather than a long-lived closure only.

- [ ] **Step 4: Run the sequence test to verify it passes**

Run: `python -m pytest -q tests\desktop\bot_actions\test_sequence.py -k "cycle or preset_chooser"`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/desktop/bot_actions/test_sequence.py raidbot/desktop/bot_actions/sequence.py
git commit -m "refactor: make slot 1 preset chooser stateful"
```

### Task 4: Thread Persistent Preset Rotation Through The Worker

**Files:**
- Modify: `raidbot/desktop/worker.py`
- Test: `tests/desktop/test_worker.py`
- Verify: `tests/desktop/test_storage.py`
- Verify: `tests/desktop/bot_actions/test_sequence.py`

- [ ] **Step 1: Write the failing worker behavior tests**

Add a focused test in `tests/desktop/test_worker.py` that proves separate raids reuse the persisted cycle instead of restarting from a fresh chooser:

```python
worker.state = DesktopAppState(slot_1_used_preset_ids=("preset-1",))
sequence = worker._build_active_bot_action_sequence_result(profile=profile, choose_preset=...)
assert sequence.sequence.steps[-1].preset_text == "preset 2"
assert worker.state.slot_1_used_preset_ids == ("preset-1", "preset-2")
```

Add a second case proving that an exhausted pool resets and starts a new cycle.

- [ ] **Step 2: Run the worker test to verify it fails**

Run: `python -m pytest -q tests\desktop\test_worker.py -k "slot_1_preset_cycle"`

Expected: FAIL because the worker recreates `build_slot_1_preset_chooser()` for each raid and does not persist the result.

- [ ] **Step 3: Write the minimal worker integration**

Update `raidbot/desktop/worker.py` to:
- read `self.state.slot_1_used_preset_ids`
- pass it into the new chooser API when building slot 1 sequences
- persist the updated used-id tuple back into `self.state`
- call the existing state persistence path after updating it

Keep the behavior narrow:
- no UI changes
- no config changes
- only slot 1 preset rotation state

- [ ] **Step 4: Run the focused verification**

Run:
- `python -m pytest -q tests\desktop\test_worker.py -k "slot_1_preset_cycle"`
- `python -m pytest -q tests\desktop\test_storage.py -k "slot_1_used_preset_ids or stale_preset_ids"`
- `python -m pytest -q tests\desktop\bot_actions\test_sequence.py -k "cycle or preset_chooser"`

Expected: PASS for all three commands.

- [ ] **Step 5: Commit**

```bash
git add tests/desktop/test_worker.py tests/desktop/test_storage.py tests/desktop/bot_actions/test_sequence.py raidbot/desktop/worker.py
git commit -m "feat: persist slot 1 preset rotation across raids"
```
