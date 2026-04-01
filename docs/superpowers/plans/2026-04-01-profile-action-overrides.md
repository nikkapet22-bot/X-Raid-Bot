# Profile Action Overrides Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-profile action checkboxes over the existing global bot-action slots so each profile can choose Reply/Like/Repost/Bookmark independently, with an orange `Paused` state when all four are disabled.

**Architecture:** Keep the existing global slot templates as the source of truth and layer a per-profile action mask on top. Store four booleans on each raid profile, expose them through a small cog dialog on each profile card, and make the worker filter global actions through that per-profile mask before running.

**Tech Stack:** Python, PySide6 desktop UI, existing desktop storage/controller/worker layers, pytest

---

## File Map

- Modify: `raidbot/desktop/models.py`
  - Extend `RaidProfileConfig` with four action booleans and default compatibility behavior.
- Modify: `raidbot/desktop/storage.py`
  - Persist the new per-profile action booleans and load older configs with all four set to `True`.
- Modify: `raidbot/desktop/controller.py`
  - Add a focused config update path for per-profile action settings.
- Modify: `raidbot/desktop/main_window.py`
  - Add cog button, per-profile action dialog, paused visual state, and settings wiring from the card to the controller.
- Modify: `raidbot/desktop/worker.py`
  - Filter global slots per profile and skip fully disabled profiles.
- Modify: `tests/desktop/test_storage.py`
  - Cover backward-compatible storage loading and persistence of action booleans.
- Modify: `tests/desktop/test_controller.py`
  - Cover controller persistence of per-profile action changes.
- Modify: `tests/desktop/test_main_window.py`
  - Cover cog dialog behavior and paused card rendering.
- Modify: `tests/desktop/test_worker.py`
  - Cover per-profile slot masking and skipping paused profiles.

### Task 1: Persist Per-Profile Action Booleans

**Files:**
- Modify: `raidbot/desktop/models.py`
- Modify: `raidbot/desktop/storage.py`
- Test: `tests/desktop/test_storage.py`

- [ ] **Step 1: Write the failing storage tests**

Add focused tests in `tests/desktop/test_storage.py` proving:

- old stored raid profiles without action booleans load with:

```python
reply_enabled is True
like_enabled is True
repost_enabled is True
bookmark_enabled is True
```

- saving a profile with mixed values round-trips correctly.

- [ ] **Step 2: Run storage tests to verify failure**

Run:

```bash
python -m pytest -q tests\desktop\test_storage.py -k "raid_profile and action"
```

Expected: FAIL because the model/storage do not yet know these fields.

- [ ] **Step 3: Implement the minimal model/storage change**

In `raidbot/desktop/models.py`:

- extend `RaidProfileConfig` with:

```python
reply_enabled: bool = True
like_enabled: bool = True
repost_enabled: bool = True
bookmark_enabled: bool = True
```

- update any profile coercion helpers so missing values default to `True`

In `raidbot/desktop/storage.py`:

- persist those fields in config serialization
- default missing older values to `True` when reading

- [ ] **Step 4: Run storage tests to verify pass**

Run:

```bash
python -m pytest -q tests\desktop\test_storage.py -k "raid_profile and action"
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/desktop/models.py raidbot/desktop/storage.py tests/desktop/test_storage.py
git commit -m "feat: persist per-profile action masks"
```

### Task 2: Add Controller Update Path

**Files:**
- Modify: `raidbot/desktop/controller.py`
- Test: `tests/desktop/test_controller.py`

- [ ] **Step 1: Write the failing controller test**

Add a focused test in `tests/desktop/test_controller.py` proving a call like:

```python
controller.set_raid_profile_action_mask(
    "Profile 3",
    reply_enabled=False,
    like_enabled=True,
    repost_enabled=False,
    bookmark_enabled=True,
)
```

persists the updated profile config while leaving other profiles unchanged.

- [ ] **Step 2: Run controller test to verify failure**

Run:

```bash
python -m pytest -q tests\desktop\test_controller.py -k "raid_profile_action_mask"
```

Expected: FAIL because the setter does not exist yet.

- [ ] **Step 3: Implement the minimal controller change**

In `raidbot/desktop/controller.py`:

- add a focused setter method for per-profile action booleans
- update only the targeted profile
- persist using the existing raid-profile config save flow

Do not add unrelated profile logic.

- [ ] **Step 4: Run controller test to verify pass**

Run:

```bash
python -m pytest -q tests\desktop\test_controller.py -k "raid_profile_action_mask"
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/desktop/controller.py tests/desktop/test_controller.py
git commit -m "feat: update per-profile action masks"
```

### Task 3: Add Cog Dialog And Paused Card State

**Files:**
- Modify: `raidbot/desktop/main_window.py`
- Test: `tests/desktop/test_main_window.py`

- [ ] **Step 1: Write the failing UI tests**

Add focused tests in `tests/desktop/test_main_window.py` proving:

- each profile card exposes a cog/settings button
- clicking it opens a dialog with:
  - `Reply`
  - `Like`
  - `Repost`
  - `Bookmark`
- saving all four as unchecked:
  - updates the config via the controller
  - makes the card show `Paused`
  - applies the orange visual variant

- [ ] **Step 2: Run focused UI tests to verify failure**

Run:

```bash
python -m pytest -q tests\desktop\test_main_window.py -k "profile action dialog or paused profile"
```

Expected: FAIL because the cog dialog and paused rendering do not exist yet.

- [ ] **Step 3: Implement the minimal UI**

In `raidbot/desktop/main_window.py`:

- add a cog button to `RaidProfileCard`
- add a small dialog with four checkboxes
- initialize checkbox state from the profile config
- on save, call the new controller setter
- update card rendering so:
  - all-off => `Paused`
  - card uses orange state styling

Keep the existing `Raid on Restart` control untouched.

- [ ] **Step 4: Run focused UI tests to verify pass**

Run:

```bash
python -m pytest -q tests\desktop\test_main_window.py -k "profile action dialog or paused profile"
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/desktop/main_window.py tests/desktop/test_main_window.py
git commit -m "feat: add per-profile action dialog"
```

### Task 4: Filter Global Slots Per Profile At Runtime

**Files:**
- Modify: `raidbot/desktop/worker.py`
- Test: `tests/desktop/test_worker.py`

- [ ] **Step 1: Write the failing worker tests**

Add focused tests in `tests/desktop/test_worker.py` proving:

- a profile with only `like_enabled=True` and `bookmark_enabled=True` runs only slots 2 and 4 from the global slot set
- a profile with all four action booleans `False` is skipped as paused and does not attempt automation

- [ ] **Step 2: Run worker tests to verify failure**

Run:

```bash
python -m pytest -q tests\desktop\test_worker.py -k "profile action mask or paused profile"
```

Expected: FAIL because runtime currently only honors global slot enabled flags.

- [ ] **Step 3: Implement the minimal worker change**

In `raidbot/desktop/worker.py`:

- derive each profile’s active slot list from:
  - global slot enabled state
  - profile action booleans
- skip profiles where all four action booleans are `False`

Do not change global slot semantics or add any per-profile template logic.

- [ ] **Step 4: Run worker tests to verify pass**

Run:

```bash
python -m pytest -q tests\desktop\test_worker.py -k "profile action mask or paused profile"
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/desktop/worker.py tests/desktop/test_worker.py
git commit -m "feat: apply per-profile action masks at runtime"
```

### Task 5: Run Focused Regression Slice

**Files:**
- Uses: `tests/desktop/test_storage.py`
- Uses: `tests/desktop/test_controller.py`
- Uses: `tests/desktop/test_main_window.py`
- Uses: `tests/desktop/test_worker.py`

- [ ] **Step 1: Run focused regression tests**

Run:

```bash
python -m pytest -q tests\desktop\test_storage.py tests\desktop\test_controller.py tests\desktop\test_main_window.py tests\desktop\test_worker.py -k "raid_profile or profile action or paused profile"
```

Expected: PASS

- [ ] **Step 2: Run one broader desktop smoke slice**

Run:

```bash
python -m pytest -q tests\desktop\test_controller.py tests\desktop\test_main_window.py tests\desktop\test_worker.py
```

Expected: PASS or known unrelated teardown issue only; if a real regression appears, stop and fix it before proceeding.

- [ ] **Step 3: Commit verification checkpoint**

```bash
git add raidbot/desktop/models.py raidbot/desktop/storage.py raidbot/desktop/controller.py raidbot/desktop/main_window.py raidbot/desktop/worker.py tests/desktop/test_storage.py tests/desktop/test_controller.py tests/desktop/test_main_window.py tests/desktop/test_worker.py
git commit -m "test: verify per-profile action overrides"
```

