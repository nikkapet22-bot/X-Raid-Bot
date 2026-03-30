# Raid On Restart Latest-Raid Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a restarted failed profile optionally replay only the most recent missed raid link, in configured profile order, without creating a backlog system.

**Architecture:** Extend persisted raid profile config with a per-profile `raid_on_restart` flag, expose that toggle on the dashboard profile cards, and keep one in-memory “latest replayable raid” record inside the worker. Restart continues to clear profile red state as today, but if the profile’s toggle is enabled and a latest replayable raid exists, the worker schedules a narrow replay pass for that one raid and only for restarted profiles that still need it.

**Tech Stack:** Python 3.10, PySide6 desktop UI, dataclass-based config/state models, JSON storage, pytest/pytest-qt.

---

## File Map

- Modify: `raidbot/desktop/models.py`
  - Add persisted `raid_on_restart` to `RaidProfileConfig`
- Modify: `raidbot/desktop/storage.py`
  - Save/load `raid_on_restart` in config JSON
- Modify: `raidbot/desktop/controller.py`
  - Add controller entry point for toggling `raid_on_restart`
  - Persist updated raid profile tuple through the existing config path
- Modify: `raidbot/desktop/main_window.py`
  - Add per-profile `Raid on Restart` toggle to `RaidProfileCard`
  - Wire toggle changes to controller
  - Keep `Restart` button behavior intact
- Modify: `raidbot/desktop/theme.py`
  - Style the new per-profile toggle so it fits the profile card layout
- Modify: `raidbot/desktop/worker.py`
  - Add one in-memory latest replayable raid record
  - Update normal raid execution to record latest-raid success/failure per profile
  - Extend restart flow to optionally schedule replay
  - Ensure replay runs restarted eligible profiles in configured order and continues on per-profile replay failure
- Modify: `tests/desktop/test_storage.py`
  - Cover config save/load of `raid_on_restart`
- Modify: `tests/desktop/test_controller.py`
  - Cover toggling `raid_on_restart` persistence through controller
- Modify: `tests/desktop/test_main_window.py`
  - Cover profile card toggle rendering and signal routing
- Modify: `tests/desktop/test_worker.py`
  - Cover latest-raid replay behavior, skip behavior, order, and in-memory-only semantics

## Task 1: Add Persisted Profile Toggle Model

**Files:**
- Modify: `raidbot/desktop/models.py`
- Test: `tests/desktop/test_storage.py`

- [ ] **Step 1: Write the failing storage test for `raid_on_restart` round-trip**

Add a test beside the existing raid profile storage coverage that saves and reloads:

```python
DesktopAppConfig(
    ...,
    raid_profiles=(
        RaidProfileConfig("Default", "George", True, False),
        RaidProfileConfig("Profile 3", "Maria", True, True),
    ),
)
```

Assert the loaded config preserves both profiles and the `raid_on_restart` booleans.

- [ ] **Step 2: Run the targeted storage test to verify it fails**

Run:

```bash
python -m pytest -q tests\desktop\test_storage.py -k raid_on_restart
```

Expected: FAIL because `RaidProfileConfig` and storage do not yet support the new field.

- [ ] **Step 3: Add the minimal model/storage implementation**

Update `raidbot/desktop/models.py`:

```python
@dataclass(eq=True)
class RaidProfileConfig:
    profile_directory: str
    label: str
    enabled: bool = True
    raid_on_restart: bool = False
```

Update `raidbot/desktop/storage.py`:

- include `raid_on_restart` in `_raid_profile_config_to_data()`
- read it in `_raid_profile_config_from_data()`
- default missing legacy data to `False`

- [ ] **Step 4: Run the targeted storage test to verify it passes**

Run:

```bash
python -m pytest -q tests\desktop\test_storage.py -k raid_on_restart
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/desktop/models.py raidbot/desktop/storage.py tests/desktop/test_storage.py
git commit -m "feat: persist raid on restart profile toggle"
```

## Task 2: Add Controller Support For Toggling `raid_on_restart`

**Files:**
- Modify: `raidbot/desktop/controller.py`
- Test: `tests/desktop/test_controller.py`

- [ ] **Step 1: Write the failing controller test**

Add a controller test that:

- starts with two raid profiles
- calls a new controller method like `set_raid_profile_raid_on_restart("Profile 3", True)`
- asserts the saved config contains:

```python
RaidProfileConfig("Profile 3", "Maria", True, True)
```

and that other profiles are unchanged.

- [ ] **Step 2: Run the targeted controller test to verify it fails**

Run:

```bash
python -m pytest -q tests\desktop\test_controller.py -k raid_on_restart
```

Expected: FAIL because the controller has no such method yet.

- [ ] **Step 3: Implement the minimal controller method**

In `raidbot/desktop/controller.py`, add a focused helper:

```python
def set_raid_profile_raid_on_restart(
    self,
    profile_directory: str,
    enabled: bool,
) -> None:
    ...
```

Implementation:

- normalize `profile_directory`
- rebuild `self.config.raid_profiles` with only the matching profile changed via `replace(profile, raid_on_restart=bool(enabled))`
- persist through `_persist_raid_profiles()`

- [ ] **Step 4: Run the targeted controller test to verify it passes**

Run:

```bash
python -m pytest -q tests\desktop\test_controller.py -k raid_on_restart
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/desktop/controller.py tests/desktop/test_controller.py
git commit -m "feat: add raid on restart controller toggle"
```

## Task 3: Add `Raid on Restart` Toggle To Profile Cards

**Files:**
- Modify: `raidbot/desktop/main_window.py`
- Modify: `raidbot/desktop/theme.py`
- Test: `tests/desktop/test_main_window.py`

- [ ] **Step 1: Write the failing UI tests**

Add `pytest-qt` coverage that asserts:

1. Each `RaidProfileCard` exposes a `Raid on Restart` toggle widget
2. The toggle reflects the current config value
3. Clicking/toggling it calls the new controller method with the profile directory and boolean

Use the existing fake controller pattern in `tests/desktop/test_main_window.py`.

- [ ] **Step 2: Run the targeted UI tests to verify they fail**

Run:

```bash
python -m pytest -q tests\desktop\test_main_window.py -k "raid_on_restart"
```

Expected: FAIL because the profile cards do not render or emit this toggle yet.

- [ ] **Step 3: Implement the minimal profile-card UI**

In `raidbot/desktop/main_window.py`:

- add a new signal to `RaidProfileCard`, for example:

```python
raidOnRestartChanged = Signal(str, bool)
```

- add a compact toggle in the lower-right card area labeled `Raid on Restart`
- initialize it from the profile config when the cards are refreshed
- emit `(profile_directory, checked)` when it changes
- connect that signal in `MainWindow` to `controller.set_raid_profile_raid_on_restart(...)`

In `raidbot/desktop/theme.py`:

- add compact styling for the new toggle so it fits the card footer without bloating the card

- [ ] **Step 4: Run the targeted UI tests to verify they pass**

Run:

```bash
python -m pytest -q tests\desktop\test_main_window.py -k "raid_on_restart"
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/desktop/main_window.py raidbot/desktop/theme.py tests/desktop/test_main_window.py
git commit -m "feat: add raid on restart toggle to profile cards"
```

## Task 4: Track The Latest Replayable Raid In Memory

**Files:**
- Modify: `raidbot/desktop/worker.py`
- Test: `tests/desktop/test_worker.py`

- [ ] **Step 1: Write the failing worker test for latest-raid memory**

Add a worker test that runs one multi-profile raid where:

- profile 1 succeeds
- profile 2 fails
- profile 3 fails

Then assert the worker keeps one in-memory latest replayable raid record equivalent to:

```python
{
    "url": latest_url,
    "succeeded_profiles": {"Default"},
    "failed_profiles": {"Profile 3", "Profile 9"},
}
```

Do not persist this into saved state; assert a freshly constructed worker does not load any replay memory.

- [ ] **Step 2: Run the targeted worker test to verify it fails**

Run:

```bash
python -m pytest -q tests\desktop\test_worker.py -k "latest_replayable_raid"
```

Expected: FAIL because the worker has no replay memory yet.

- [ ] **Step 3: Implement the in-memory replay record**

In `raidbot/desktop/worker.py`:

- add a small private in-memory structure, for example:

```python
self._latest_replayable_raid = None
```

with fields:

- `url`
- `succeeded_profiles`
- `failed_profiles`

Update the normal multi-profile execution path so that for the latest processed raid:

- successful profiles are added to `succeeded_profiles`
- failed profiles are added to `failed_profiles`

Do not write this structure to `DesktopAppState` or storage.

- [ ] **Step 4: Run the targeted worker test to verify it passes**

Run:

```bash
python -m pytest -q tests\desktop\test_worker.py -k "latest_replayable_raid"
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/desktop/worker.py tests/desktop/test_worker.py
git commit -m "feat: track latest replayable raid in memory"
```

## Task 5: Replay Latest Raid On Restart When Toggle Is Enabled

**Files:**
- Modify: `raidbot/desktop/worker.py`
- Test: `tests/desktop/test_worker.py`

- [ ] **Step 1: Write the failing restart replay tests**

Add worker tests for all core restart branches:

1. `Restart` with `raid_on_restart=False`:
   - clears red state
   - does not replay latest raid

2. `Restart` with `raid_on_restart=True` and latest replayable raid present:
   - replays only the latest raid
   - only for restarted profiles that still need it

3. Replay order:
   - restarted eligible profiles run in configured profile order

4. Replay skip behavior:
   - profiles that already succeeded that raid are skipped
   - profiles still red are skipped

5. Replay failure behavior:
   - if one replayed profile fails again, replay continues to the next eligible restarted profile

- [ ] **Step 2: Run the targeted worker tests to verify they fail**

Run:

```bash
python -m pytest -q tests\desktop\test_worker.py -k "raid_on_restart or replay_latest_raid"
```

Expected: FAIL because restart currently only clears red state.

- [ ] **Step 3: Implement the minimal restart replay flow**

In `raidbot/desktop/worker.py`:

- extend `restart_raid_profile()` to:
  - clear the profile red state as today
  - look up the profile config for `raid_on_restart`
  - if `raid_on_restart` is `False`, return
  - if no latest replayable raid exists, return
  - otherwise schedule a replay pass for that latest raid

Implement replay pass rules:

- iterate `self.config.raid_profiles` in order
- consider only profiles that:
  - match the latest replayable raid’s `failed_profiles`
  - are now green
  - have `raid_on_restart=True`
  - are enabled
- skip any profile already present in `succeeded_profiles`
- run the existing per-profile open/automation path for that one latest URL
- if replay succeeds, add the profile to `succeeded_profiles`
- if replay fails, keep marking that profile red but continue to the next eligible restarted profile

Keep this flow narrow:

- no replay queue
- no replay of older URLs
- no persistence

- [ ] **Step 4: Run the targeted worker tests to verify they pass**

Run:

```bash
python -m pytest -q tests\desktop\test_worker.py -k "raid_on_restart or replay_latest_raid"
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/desktop/worker.py tests/desktop/test_worker.py
git commit -m "feat: replay latest raid for restarted profiles"
```

## Task 6: Run Focused Regression Suites And Full Verification

**Files:**
- Test: `tests/desktop/test_storage.py`
- Test: `tests/desktop/test_controller.py`
- Test: `tests/desktop/test_main_window.py`
- Test: `tests/desktop/test_worker.py`

- [ ] **Step 1: Run focused desktop regressions**

Run:

```bash
python -m pytest -q tests\desktop\test_storage.py tests\desktop\test_controller.py tests\desktop\test_main_window.py tests\desktop\test_worker.py
```

Expected: PASS

- [ ] **Step 2: Run full suite**

Run:

```bash
python -m pytest -q
```

Expected: PASS

- [ ] **Step 3: Commit final integration**

```bash
git add raidbot/desktop/models.py raidbot/desktop/storage.py raidbot/desktop/controller.py raidbot/desktop/main_window.py raidbot/desktop/theme.py raidbot/desktop/worker.py tests/desktop/test_storage.py tests/desktop/test_controller.py tests/desktop/test_main_window.py tests/desktop/test_worker.py
git commit -m "feat: add raid on restart replay flow"
```

## Notes For The Implementer

- Keep replay memory in the worker only; do not add it to `DesktopAppState`
- Preserve existing `Restart` semantics when the toggle is off
- Reuse the existing multi-profile per-profile execution path instead of inventing a second automation pipeline
- Do not turn this into a backlog system
- Keep replay tied only to the most recent replayable raid URL
