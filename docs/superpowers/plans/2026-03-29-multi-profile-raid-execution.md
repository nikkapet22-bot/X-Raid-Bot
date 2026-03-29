# Multi-Profile Raid Execution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow each incoming raid link to run automatically across a user-managed ordered list of Chrome profiles, continuing after per-profile failures and showing per-profile health on the dashboard.

**Architecture:** Extend desktop config/state with a persisted raid-profile list and per-profile health metadata, replace the worker’s single-profile autorun path with an ordered per-profile execution loop, and add dashboard/profile-management UI for detection, ordering, failure display, and restart. The existing Bot Actions flow stays shared across all profiles.

**Tech Stack:** Python, PySide6, existing desktop worker/controller/main window stack, existing Chrome profile detection, pytest/pytest-qt.

---

## File Map

- Modify: `raidbot/desktop/models.py`
  - Add persisted raid-profile config/state models and normalize them inside `DesktopAppConfig` / `DesktopAppState`.
- Modify: `raidbot/desktop/storage.py`
  - Persist the raid-profile list and latest profile health state.
- Modify: `raidbot/desktop/chrome_profiles.py`
  - Reuse existing detected Chrome profiles as the source for addable raid profiles.
- Modify: `raidbot/desktop/controller.py`
  - Add profile add/remove/reorder/restart commands and emit profile-health updates to the UI.
- Modify: `raidbot/desktop/worker.py`
  - Replace the single-profile autorun path with ordered multi-profile processing and per-profile failure continuation.
- Modify: `raidbot/desktop/main_window.py`
  - Add dashboard profile cards and wire restart/failure-reason interactions.
- Modify: `raidbot/desktop/settings_page.py`
  - Replace the single raid-browser-profile control with an ordered detected-profile manager.
- Modify: `raidbot/chrome.py`
  - Ensure dedicated window open/close helpers can be called for arbitrary profile directories in sequence.
- Modify: `tests/desktop/test_storage.py`
  - Cover storage round-trip for raid-profile config/state.
- Modify: `tests/desktop/test_controller.py`
  - Cover profile management and restart commands.
- Modify: `tests/desktop/test_main_window.py`
  - Cover profile cards, restart action, and settings-page profile list interactions.
- Modify: `tests/desktop/test_worker.py`
  - Cover ordered multi-profile execution, continue-on-failure, skip-red, and restart recovery.

### Task 1: Add Raid Profile Models And Storage

**Files:**
- Modify: `raidbot/desktop/models.py`
- Modify: `raidbot/desktop/storage.py`
- Test: `tests/desktop/test_storage.py`

- [ ] **Step 1: Write the failing storage test for raid-profile config round-trip**

Add a test in `tests/desktop/test_storage.py` that builds a `DesktopAppConfig` with two raid profiles:

```python
config = DesktopAppConfig(
    ...,
    raid_profiles=(
        RaidProfileConfig(
            profile_directory="Default",
            label="George",
            enabled=True,
        ),
        RaidProfileConfig(
            profile_directory="Profile 3",
            label="Maria",
            enabled=True,
        ),
    ),
)
```

Assert that `save_config()` and `load_config()` preserve:
- order
- directory names
- labels
- enabled flags

- [ ] **Step 2: Run the storage test to verify it fails**

Run:

```bash
python -m pytest -q tests/desktop/test_storage.py -k raid_profile
```

Expected: FAIL because `raid_profiles` does not exist in the config model/storage path yet.

- [ ] **Step 3: Write the failing storage test for persisted profile health state**

Add a second test in `tests/desktop/test_storage.py` that saves `DesktopAppState` with profile statuses like:

```python
profile_states=(
    RaidProfileState(profile_directory="Default", status="green", last_error=None),
    RaidProfileState(profile_directory="Profile 3", status="red", last_error="not_logged_in"),
)
```

Assert `load_state()` preserves the latest profile status and failure reason.

- [ ] **Step 4: Run the storage test again to verify the second failure**

Run:

```bash
python -m pytest -q tests/desktop/test_storage.py -k profile_state
```

Expected: FAIL because profile health state is not modeled/persisted yet.

- [ ] **Step 5: Implement the minimal desktop model additions**

In `raidbot/desktop/models.py`, add focused dataclasses such as:

```python
@dataclass(eq=True)
class RaidProfileConfig:
    profile_directory: str
    label: str
    enabled: bool = True


@dataclass(eq=True)
class RaidProfileState:
    profile_directory: str
    label: str
    status: str = "green"
    last_error: str | None = None
```

Then extend:
- `DesktopAppConfig` with `raid_profiles`
- `DesktopAppState` with latest `raid_profile_states`

Keep normalization simple:
- empty/missing `raid_profiles` defaults to the existing single `chrome_profile_directory` as one profile
- empty/missing `raid_profile_states` defaults to healthy green entries for configured profiles

- [ ] **Step 6: Implement the minimal storage round-trip**

In `raidbot/desktop/storage.py`:
- serialize `raid_profiles`
- deserialize `raid_profiles`
- serialize `raid_profile_states`
- deserialize `raid_profile_states`
- keep backward compatibility with existing saved configs

- [ ] **Step 7: Run the focused storage tests**

Run:

```bash
python -m pytest -q tests/desktop/test_storage.py -k "raid_profile or profile_state"
```

Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add raidbot/desktop/models.py raidbot/desktop/storage.py tests/desktop/test_storage.py
git commit -m "feat: add persisted raid profile models"
```

### Task 2: Add Profile Management Commands To Controller

**Files:**
- Modify: `raidbot/desktop/controller.py`
- Test: `tests/desktop/test_controller.py`

- [ ] **Step 1: Write the failing controller test for adding a detected profile**

Add a test that starts with one profile and calls a new controller method like:

```python
controller.add_raid_profile("Profile 3", "Maria")
```

Assert:
- config is persisted
- new profile is appended in order
- duplicates are ignored or rejected cleanly

- [ ] **Step 2: Run the controller add-profile test to verify it fails**

Run:

```bash
python -m pytest -q tests/desktop/test_controller.py -k add_raid_profile
```

Expected: FAIL because the controller method and config plumbing do not exist.

- [ ] **Step 3: Write the failing controller test for restarting a red profile**

Add a test that seeds a red profile in state, calls:

```python
controller.restart_raid_profile("Profile 3")
```

Assert the controller emits the right worker command or state-reset path and the profile becomes eligible again.

- [ ] **Step 4: Run the restart test to verify it fails**

Run:

```bash
python -m pytest -q tests/desktop/test_controller.py -k restart_raid_profile
```

Expected: FAIL because restart handling does not exist.

- [ ] **Step 5: Implement minimal controller methods**

In `raidbot/desktop/controller.py`, add focused methods:

```python
def add_raid_profile(self, profile_directory: str, label: str) -> None: ...
def remove_raid_profile(self, profile_directory: str) -> None: ...
def move_raid_profile(self, profile_directory: str, direction: str) -> None: ...
def restart_raid_profile(self, profile_directory: str) -> None: ...
```

Rules:
- preserve user order
- no duplicate `profile_directory`
- restart clears the blocked state for future raids

- [ ] **Step 6: Run the focused controller tests**

Run:

```bash
python -m pytest -q tests/desktop/test_controller.py -k "raid_profile or restart_raid_profile"
```

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add raidbot/desktop/controller.py tests/desktop/test_controller.py
git commit -m "feat: add raid profile controller actions"
```

### Task 3: Add Settings UI For Ordered Detected Raid Profiles

**Files:**
- Modify: `raidbot/desktop/settings_page.py`
- Modify: `raidbot/desktop/main_window.py`
- Test: `tests/desktop/test_main_window.py`

- [ ] **Step 1: Write the failing main-window/settings test for adding detected profiles**

Add a test that feeds detected Chrome profiles like:

```python
[
    ChromeProfile(directory_name="Default", label="George"),
    ChromeProfile(directory_name="Profile 3", label="Maria"),
    ChromeProfile(directory_name="Profile 9", label="Pasok"),
]
```

Then simulate:
- add profile
- add second profile
- reorder profiles

Assert the controller receives the corresponding add/move calls.

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
python -m pytest -q tests/desktop/test_main_window.py -k raid_profile
```

Expected: FAIL because the settings UI still exposes only the old single profile selector.

- [ ] **Step 3: Implement the minimal settings-page UI**

In `raidbot/desktop/settings_page.py` replace the old single-profile control with:
- detected-profile picker
- `Add profile`
- configured profile list
- `Remove`
- `Move up`
- `Move down`

Do not add per-profile bot settings.

- [ ] **Step 4: Wire the UI in main window**

In `raidbot/desktop/main_window.py`:
- feed detected Chrome profiles into the new settings control
- connect add/remove/reorder actions to controller methods
- refresh the configured list after config changes

- [ ] **Step 5: Run the focused UI tests**

Run:

```bash
python -m pytest -q tests/desktop/test_main_window.py -k raid_profile
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add raidbot/desktop/settings_page.py raidbot/desktop/main_window.py tests/desktop/test_main_window.py
git commit -m "feat: add ordered raid profile settings ui"
```

### Task 4: Replace Single-Profile Worker Execution With Ordered Multi-Profile Execution

**Files:**
- Modify: `raidbot/desktop/worker.py`
- Modify: `raidbot/chrome.py`
- Test: `tests/desktop/test_worker.py`

- [ ] **Step 1: Write the failing worker test for ordered multi-profile success**

Add a worker test that configures two raid profiles:

```python
raid_profiles=(
    RaidProfileConfig(profile_directory="Default", label="George"),
    RaidProfileConfig(profile_directory="Profile 3", label="Maria"),
)
```

Assert that one detected raid link causes:
- open with `Default`
- run actions
- close window
- open with `Profile 3`
- run actions
- close window

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
python -m pytest -q tests/desktop/test_worker.py -k multi_profile_success
```

Expected: FAIL because worker still uses one profile per raid.

- [ ] **Step 3: Write the failing worker test for continue-after-failure**

Add a second test:
- profile 1 succeeds
- profile 2 fails
- profile 3 still runs

Assert:
- failed profile window stays open
- later profile still executes
- failed profile is marked blocked for future raids

- [ ] **Step 4: Run the failure-continuation test to verify it fails**

Run:

```bash
python -m pytest -q tests/desktop/test_worker.py -k continue_after_profile_failure
```

Expected: FAIL because worker currently pauses the whole raid on failure.

- [ ] **Step 5: Implement the minimal worker multi-profile loop**

In `raidbot/desktop/worker.py`:
- resolve the configured eligible green profile list
- for each profile in order:
  - open dedicated raid window with that profile
  - run the current bot-action sequence
  - update profile state/result
- on failure:
  - leave window open
  - mark profile red with reason
  - continue to next healthy profile

Do not queue failed profiles for retry.

- [ ] **Step 6: Update chrome helper usage if needed**

In `raidbot/chrome.py`, make sure the dedicated window opener can be invoked repeatedly with different profile directories in one raid cycle without mutating hidden shared state incorrectly.

- [ ] **Step 7: Run the focused worker tests**

Run:

```bash
python -m pytest -q tests/desktop/test_worker.py -k "multi_profile_success or continue_after_profile_failure"
```

Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add raidbot/desktop/worker.py raidbot/chrome.py tests/desktop/test_worker.py
git commit -m "feat: execute raids across ordered profiles"
```

### Task 5: Add Dashboard Profile Cards And Restart Behavior

**Files:**
- Modify: `raidbot/desktop/main_window.py`
- Modify: `raidbot/desktop/controller.py`
- Test: `tests/desktop/test_main_window.py`
- Test: `tests/desktop/test_controller.py`

- [ ] **Step 1: Write the failing dashboard test for profile cards**

Add a main-window test that seeds:

```python
raid_profile_states=(
    RaidProfileState(profile_directory="Default", label="George", status="green"),
    RaidProfileState(profile_directory="Profile 3", label="Maria", status="red", last_error="not_logged_in"),
)
```

Assert the dashboard shows:
- one green card
- one red card
- red card includes `Restart`

- [ ] **Step 2: Run the dashboard-card test to verify it fails**

Run:

```bash
python -m pytest -q tests/desktop/test_main_window.py -k profile_card
```

Expected: FAIL because dashboard has no profile-card surface yet.

- [ ] **Step 3: Write the failing main-window/controller test for restart action**

Add a test that clicks `Restart` on a red card and asserts the controller receives:

```python
controller.restart_raid_profile("Profile 3")
```

- [ ] **Step 4: Run the restart-card test to verify it fails**

Run:

```bash
python -m pytest -q tests/desktop/test_main_window.py -k restart_profile
```

Expected: FAIL because the dashboard action does not exist.

- [ ] **Step 5: Implement dashboard cards**

In `raidbot/desktop/main_window.py`:
- add a `Profiles` dashboard section
- render one rectangle per configured profile
- green glow for healthy
- red glow for blocked
- click/show last error for red profiles
- show `Restart` button on red profiles

- [ ] **Step 6: Wire restart and state refresh**

Connect the dashboard restart action to `controller.restart_raid_profile(...)` and refresh profile-card state from worker/controller events.

- [ ] **Step 7: Run the focused dashboard/controller tests**

Run:

```bash
python -m pytest -q tests/desktop/test_main_window.py -k "profile_card or restart_profile" tests/desktop/test_controller.py -k restart_raid_profile
```

Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add raidbot/desktop/main_window.py raidbot/desktop/controller.py tests/desktop/test_main_window.py tests/desktop/test_controller.py
git commit -m "feat: add dashboard raid profile health cards"
```

### Task 6: Skip Red Profiles And Re-Enable On Restart

**Files:**
- Modify: `raidbot/desktop/worker.py`
- Modify: `raidbot/desktop/controller.py`
- Test: `tests/desktop/test_worker.py`

- [ ] **Step 1: Write the failing worker test for skipping red profiles on future raids**

Add a worker test where:
- profile `Maria` is already red/blocked from a previous failure
- a new raid arrives

Assert:
- `Maria` is skipped
- healthy profiles still execute

- [ ] **Step 2: Run the skip-red test to verify it fails**

Run:

```bash
python -m pytest -q tests/desktop/test_worker.py -k skip_red_profile
```

Expected: FAIL because blocked profile state is not consulted yet.

- [ ] **Step 3: Write the failing worker test for restart re-enabling a blocked profile**

Add a test that:
- marks `Maria` red
- issues restart
- next raid includes `Maria` again

- [ ] **Step 4: Run the restart-reenable test to verify it fails**

Run:

```bash
python -m pytest -q tests/desktop/test_worker.py -k restart_reenables_profile
```

Expected: FAIL because restart currently does not affect profile eligibility.

- [ ] **Step 5: Implement blocked-profile skip and restart recovery**

In `raidbot/desktop/worker.py` and `raidbot/desktop/controller.py`:
- skip profiles with red/blocked state
- clear blocked state on restart
- keep restart as a future-eligibility reset only

- [ ] **Step 6: Run the focused worker tests**

Run:

```bash
python -m pytest -q tests/desktop/test_worker.py -k "skip_red_profile or restart_reenables_profile"
```

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add raidbot/desktop/worker.py raidbot/desktop/controller.py tests/desktop/test_worker.py
git commit -m "feat: skip blocked raid profiles until restart"
```

### Task 7: Full Verification

**Files:**
- Verify only

- [ ] **Step 1: Run the full desktop-focused verification**

Run:

```bash
python -m pytest -q tests/desktop/test_storage.py tests/desktop/test_controller.py tests/desktop/test_main_window.py tests/desktop/test_worker.py
```

Expected: PASS

- [ ] **Step 2: Run the full suite**

Run:

```bash
python -m pytest -q
```

Expected: PASS

- [ ] **Step 3: Commit any final test-only adjustments**

```bash
git add -u
git commit -m "test: cover multi-profile raid execution"
```
