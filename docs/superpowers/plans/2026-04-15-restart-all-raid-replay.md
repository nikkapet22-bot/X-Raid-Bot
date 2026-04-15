# Restart All Raid Replay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a persistent `Raid?` checkbox next to `Restart All` so pressing `Restart All` can optionally fetch the latest valid recent raid and replay it only for profiles that did not already succeed on that exact URL.

**Architecture:** Keep the change inside the existing desktop app surfaces. Persist one new config flag, render the checkbox in the Profiles header, route the action through the controller, and extend the worker’s `reset_all_raid_profiles()` path into a reset-plus-optional-replay flow that reuses the existing latest-valid-raid lookup and exact-URL success filtering.

**Tech Stack:** PySide6, existing desktop controller/worker runtime, Telethon-backed latest-raid lookup, pytest

---

### Task 1: Persist `raid_on_restart_enabled` in desktop config

**Files:**
- Modify: `raidbot/desktop/models.py`
- Modify: `raidbot/desktop/storage.py`
- Test: `tests/desktop/test_storage.py`

- [ ] **Step 1: Write the failing storage tests**

Add coverage for a new config flag:

```python
def test_storage_round_trips_raid_on_restart_enabled(tmp_path: Path) -> None:
    storage = DesktopStorage(tmp_path)
    config = build_config(raid_on_restart_enabled=True)

    storage.save_config(config)
    loaded = storage.load_config()

    assert loaded.raid_on_restart_enabled is True
```

and legacy-default behavior:

```python
def test_storage_defaults_raid_on_restart_enabled_to_false(tmp_path: Path) -> None:
    storage = DesktopStorage(tmp_path)
    config_path = storage.base_dir / "config.json"
    config_path.write_text(json.dumps({
        "telegram_api_id": 1,
        "telegram_api_hash": "hash",
        "telegram_session_path": "raidbot.session",
        "whitelisted_chat_ids": [-1001],
        "chrome_profile_directory": "Default"
    }), encoding="utf-8")

    loaded = storage.load_config()

    assert loaded.raid_on_restart_enabled is False
```

- [ ] **Step 2: Run the storage slice to verify failure**

Run: `python -m pytest -q tests\desktop\test_storage.py -k "raid_on_restart_enabled"`

Expected: FAIL because the config model and serializer do not know this field yet.

- [ ] **Step 3: Add the new config field**

Update:

- `DesktopAppConfig` in `raidbot/desktop/models.py`
- config serialization/deserialization helpers in `raidbot/desktop/storage.py`

Rules:

- default to `False`
- load older configs cleanly without the field
- emit the field in saved config JSON only once the model owns it

- [ ] **Step 4: Run the focused storage tests**

Run: `python -m pytest -q tests\desktop\test_storage.py -k "raid_on_restart_enabled"`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/desktop/models.py raidbot/desktop/storage.py tests/desktop/test_storage.py
git commit -m "feat: persist restart-all raid replay toggle"
```

### Task 2: Add `[Restart All] Raid? [ ]` to the Profiles header

**Files:**
- Modify: `raidbot/desktop/main_window.py`
- Modify: `raidbot/desktop/controller.py`
- Test: `tests/desktop/test_main_window.py`
- Test: `tests/desktop/test_controller.py`

- [ ] **Step 1: Write the failing UI and controller tests**

Add a Profiles header test that asserts the new checkbox exists and is placed next to the button:

```python
assert window.restart_all_profiles_button.text() == "Restart All"
assert window.restart_all_raid_checkbox.text() == "Raid?"
assert window.restart_all_raid_checkbox.isChecked() is False
```

Add an auto-save routing test:

```python
window.restart_all_raid_checkbox.setChecked(True)
assert controller.set_raid_on_restart_enabled_calls == [True]
```

Add a controller persistence test:

```python
controller.set_raid_on_restart_enabled(True)
assert storage.saved_configs[-1].raid_on_restart_enabled is True
```

- [ ] **Step 2: Run the focused UI/controller slice to verify failure**

Run: `python -m pytest -q tests\desktop\test_main_window.py -k "restart_all or raid_on_restart_enabled" tests\desktop\test_controller.py -k "raid_on_restart_enabled"`

Expected: FAIL because the checkbox and setter do not exist yet.

- [ ] **Step 3: Render the checkbox in the header row**

In `raidbot/desktop/main_window.py`:

- keep `Restart All` as the existing left control in the header action cluster
- add `self.restart_all_raid_checkbox = QCheckBox("Raid?")`
- place it immediately to the right of `Restart All`
- initialize it from `self.controller.config.raid_on_restart_enabled`
- connect `toggled` to the controller setter

Do not move the button elsewhere. The visual order must be:

- `Restart All`
- `Raid?`
- checkbox

- [ ] **Step 4: Persist the checkbox through the controller**

In `raidbot/desktop/controller.py`:

- add `set_raid_on_restart_enabled(enabled: bool) -> None`
- update `self.config`
- save through storage
- emit `configChanged`

This should match the repo’s existing config mutation pattern. Do not invent a second settings store.

- [ ] **Step 5: Run the focused UI/controller tests**

Run: `python -m pytest -q tests\desktop\test_main_window.py -k "restart_all or raid_on_restart_enabled" tests\desktop\test_controller.py -k "raid_on_restart_enabled"`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add raidbot/desktop/main_window.py raidbot/desktop/controller.py tests/desktop/test_main_window.py tests/desktop/test_controller.py
git commit -m "feat: add restart-all raid replay checkbox"
```

### Task 3: Extend the `Restart All` command path to carry replay intent

**Files:**
- Modify: `raidbot/desktop/controller.py`
- Test: `tests/desktop/test_controller.py`

- [ ] **Step 1: Write the failing controller behavior tests**

Cover both button modes:

```python
controller.config = build_config(raid_on_restart_enabled=False)
controller.reset_all_raid_profiles()
assert worker.reset_all_raid_profiles_calls == [False]
```

and:

```python
controller.config = build_config(raid_on_restart_enabled=True)
controller.reset_all_raid_profiles()
assert worker.reset_all_raid_profiles_calls == [True]
```

Also cover the stopped-app fallback:

```python
controller.config = build_config(raid_on_restart_enabled=True)
controller._worker = None
controller._runner = None

controller.reset_all_raid_profiles()

assert latest_saved_state.raid_profile_states[0].status == "green"
```

The stopped-app fallback should still do plain reset only.

- [ ] **Step 2: Run the controller slice to confirm failure**

Run: `python -m pytest -q tests\desktop\test_controller.py -k "reset_all_raid_profiles or raid_on_restart_enabled"`

Expected: FAIL because `reset_all_raid_profiles()` does not pass replay intent to the worker.

- [ ] **Step 3: Thread the config flag into the running-worker path**

In `raidbot/desktop/controller.py`:

- change the running-worker call from:
  - `self._worker.reset_all_raid_profiles()`
- to:
  - `self._worker.reset_all_raid_profiles(self.config.raid_on_restart_enabled)`

Keep the stopped-app fallback unchanged:

- plain green reset only
- no replay when there is no running worker/runtime

- [ ] **Step 4: Run the focused controller tests**

Run: `python -m pytest -q tests\desktop\test_controller.py -k "reset_all_raid_profiles or raid_on_restart_enabled"`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/desktop/controller.py tests/desktop/test_controller.py
git commit -m "refactor: thread restart-all replay intent through controller"
```

### Task 4: Implement reset-plus-optional-replay in the worker

**Files:**
- Modify: `raidbot/desktop/worker.py`
- Test: `tests/desktop/test_worker.py`

- [ ] **Step 1: Write the failing worker tests**

Add tests for the new worker behavior.

Reset-only mode:

```python
worker.reset_all_raid_profiles(False)
assert all(state.status == "green" for state in worker.state.raid_profile_states)
assert recent_lookup_calls == 0
```

Replay mode fetches latest valid raid:

```python
worker.reset_all_raid_profiles(True)
assert latest_lookup_calls == 1
```

Skip profiles that already succeeded on the fetched URL:

```python
assert replayed_profiles == ["Profile 2", "Profile 5"]
```

where `Profile 1` already has:

```python
ActivityRecord(
    action="automation_succeeded",
    profile_directory="Profile 1",
    url="https://x.com/i/status/777",
)
```

No recent valid raid:

```python
worker.reset_all_raid_profiles(True)
assert worker.state.raid_profile_states[0].status == "green"
assert emitted_errors[-1] == "No recent valid raid found"
```

Nothing to replay:

```python
worker.reset_all_raid_profiles(True)
assert replayed_profiles == []
assert emitted_errors[-1] == "All profiles already raided latest raid"
```

- [ ] **Step 2: Run the worker slice to verify failure**

Run: `python -m pytest -q tests\desktop\test_worker.py -k "reset_all_raid_profiles or restart_all_replay or latest_valid_raid"`

Expected: FAIL because the worker only resets state today and has no replay filtering.

- [ ] **Step 3: Extend the worker entry point**

In `raidbot/desktop/worker.py`:

- change `reset_all_raid_profiles()` to accept `raid_on_restart_enabled: bool = False`
- always reset profile states to green first
- if the flag is `False`, stop there
- if the flag is `True`:
  - fetch the latest valid recent raid via the same helper used by `Raid NOW!`
  - if lookup fails, leave the reset result in place and raise/emit a clear user-facing error

- [ ] **Step 4: Add exact-URL success filtering**

Implement a small helper in `raidbot/desktop/worker.py`, for example:

```python
def _profiles_missing_success_for_url(
    self,
    normalized_url: str,
    profiles: Sequence[RaidProfileConfig],
) -> tuple[RaidProfileConfig, ...]:
    ...
```

Rules:

- a profile counts as already complete only if activity contains:
  - `action == "automation_succeeded"`
  - same `profile_directory`
  - same normalized URL
- use the current config’s raid profiles as the source list
- preserve existing profile order

- [ ] **Step 5: Reuse the existing manual execution path**

Do not implement a second raid runner.

After lookup/filtering, build a `PendingRaidWorkItem` for the fetched latest raid URL and execute only the missing profiles through the existing profile execution path used by manual/latest-raid runs.

Expected structure:

- latest valid recent raid lookup
- dedupe mark for the URL
- existing `_execute_profiles_for_item(...)` or adjacent manual-run helper
- ordered profiles = only the missing ones

This keeps replay semantics aligned with `Raid NOW!` and avoids a parallel code path.

- [ ] **Step 6: Run the focused worker tests**

Run: `python -m pytest -q tests\desktop\test_worker.py -k "reset_all_raid_profiles or restart_all_replay or latest_valid_raid"`

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add raidbot/desktop/worker.py tests/desktop/test_worker.py
git commit -m "feat: replay latest raid for missing profiles after restart all"
```

### Task 5: Surface replay feedback and verify the full slice

**Files:**
- Modify: `raidbot/desktop/main_window.py`
- Modify: `raidbot/desktop/controller.py`
- Modify: `raidbot/desktop/worker.py`
- Test: `tests/desktop/test_main_window.py`
- Test: `tests/desktop/test_controller.py`
- Test: `tests/desktop/test_worker.py`
- Test: `tests/desktop/test_packaging.py`

- [ ] **Step 1: Write the failing feedback tests**

Add UI coverage for the two important replay outcomes:

```python
window.restart_all_raid_checkbox.setChecked(True)
qtbot.mouseClick(window.restart_all_profiles_button, Qt.MouseButton.LeftButton)
assert last_error_message == "No recent valid raid found"
```

and:

```python
assert last_error_message == "All profiles already raided latest raid"
```

Reuse the app’s existing error/status surface instead of creating a second bespoke message system unless the current path cannot represent these outcomes cleanly.

- [ ] **Step 2: Run the focused UI/integration slice**

Run: `python -m pytest -q tests\desktop\test_main_window.py -k "restart_all or raid_on_restart_enabled" tests\desktop\test_controller.py -k "reset_all_raid_profiles or raid_on_restart_enabled" tests\desktop\test_worker.py -k "reset_all_raid_profiles or restart_all_replay"`

Expected: FAIL because replay feedback is not surfaced yet.

- [ ] **Step 3: Route replay outcomes into the existing user-visible error path**

Ensure replay failures and “nothing to replay” outcomes are visible to the user. Prefer the current `errorRaised` / status path already used by manual actions instead of inventing a silent worker-only branch.

Rules:

- reset still completes first
- replay feedback should not masquerade as a profile automation failure
- successful replay of missing profiles should not disturb profiles that already succeeded

- [ ] **Step 4: Run the full focused regression**

Run: `python -m pytest -q tests\desktop\test_storage.py -k "raid_on_restart_enabled" tests\desktop\test_main_window.py -k "restart_all or raid_on_restart_enabled" tests\desktop\test_controller.py -k "reset_all_raid_profiles or raid_on_restart_enabled" tests\desktop\test_worker.py -k "reset_all_raid_profiles or restart_all_replay or latest_valid_raid" tests\desktop\test_packaging.py`

Expected: PASS

- [ ] **Step 5: Bump the version**

Update:

- `pyproject.toml`
- `raidbot/__init__.py`
- `tests/desktop/test_packaging.py`

Use the next patch version only after the feature and tests are green.

- [ ] **Step 6: Commit**

```bash
git add raidbot/desktop/main_window.py raidbot/desktop/controller.py raidbot/desktop/worker.py tests/desktop/test_main_window.py tests/desktop/test_controller.py tests/desktop/test_worker.py pyproject.toml raidbot/__init__.py tests/desktop/test_packaging.py
git commit -m "feat: replay latest missing profiles after restart all"
```

### Task 6: Final verification and release-readiness check

**Files:**
- Modify: none
- Test: `tests/desktop/test_storage.py`
- Test: `tests/desktop/test_main_window.py`
- Test: `tests/desktop/test_controller.py`
- Test: `tests/desktop/test_worker.py`
- Test: `tests/desktop/test_packaging.py`

- [ ] **Step 1: Run the final focused suite**

Run:

```bash
python -m pytest -q tests\desktop\test_storage.py -k "raid_on_restart_enabled" tests\desktop\test_main_window.py -k "restart_all or raid_on_restart_enabled" tests\desktop\test_controller.py -k "reset_all_raid_profiles or raid_on_restart_enabled" tests\desktop\test_worker.py -k "reset_all_raid_profiles or restart_all_replay or latest_valid_raid" tests\desktop\test_packaging.py
```

Expected: PASS

- [ ] **Step 2: Optionally run the broader desktop slice if the focused suite exposes coupling**

Run:

```bash
python -m pytest -q tests\desktop\test_main_window.py tests\desktop\test_controller.py tests\desktop\test_worker.py
```

Expected: PASS or known unrelated failures only. If unrelated failures appear, document them before release work.

- [ ] **Step 3: Commit any final plan-driven cleanup**

If the implementation required small test-name or message cleanups beyond the feature commits above, commit them explicitly before packaging/release work.
