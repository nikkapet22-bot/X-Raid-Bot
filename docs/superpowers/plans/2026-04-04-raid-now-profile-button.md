# Raid NOW Profile Button Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the profile-card restart/replay controls with a `Raid NOW!` button that fetches the most recent valid Telegram raid and runs it for exactly one selected profile.

**Architecture:** Keep the change inside the existing desktop app. The UI swaps profile-card controls, the controller exposes a single manual-run command, and the worker performs a newest-first Telegram lookup using current allowlists before executing the chosen profile through the existing raid automation path.

**Tech Stack:** PySide6, Telethon, existing desktop controller/worker runtime, pytest

---

### Task 1: Remove `raid_on_restart` persistence and legacy UI assumptions

**Files:**
- Modify: `raidbot/desktop/models.py`
- Modify: `raidbot/desktop/storage.py`
- Test: `tests/desktop/test_storage.py`

- [ ] **Step 1: Write the failing legacy-load test**

```python
def test_storage_ignores_legacy_raid_on_restart_field(tmp_path: Path) -> None:
    storage = DesktopStorage(tmp_path)
    config_path = storage.base_dir / "config.json"
    config_path.write_text(json.dumps({
        "telegram_api_id": 1,
        "telegram_api_hash": "hash",
        "telegram_session_path": "raidbot.session",
        "telegram_phone_number": "+40123",
        "whitelisted_chat_ids": [-1001],
        "allowed_sender_ids": [42],
        "allowed_sender_entries": ["@raidar"],
        "chrome_profile_directory": "Profile 3",
        "raid_profiles": [{
            "profile_directory": "Profile 3",
            "label": "Profile 3",
            "enabled": True,
            "raid_on_restart": True
        }]
    }), encoding="utf-8")

    loaded = storage.load_config()

    assert loaded.raid_profiles[0].profile_directory == "Profile 3"
```

- [ ] **Step 2: Run the storage test to verify current behavior**

Run: `python -m pytest -q tests\desktop\test_storage.py -k raid_on_restart`

Expected: existing assertions still mention `raid_on_restart`, showing the model/storage surface still owns that field.

- [ ] **Step 3: Remove the field from the config model and serializer**

Update:

- `RaidProfileConfig` in `raidbot/desktop/models.py`
- `_raid_profile_config_to_data()` in `raidbot/desktop/storage.py`
- `_raid_profile_config_from_data()` in `raidbot/desktop/storage.py`

Rules:

- do not emit `raid_on_restart` anymore
- ignore `raid_on_restart` if found in legacy config JSON
- keep other profile action booleans unchanged

- [ ] **Step 4: Run the focused storage tests**

Run: `python -m pytest -q tests\desktop\test_storage.py -k "raid_profile or raid_on_restart"`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/desktop/models.py raidbot/desktop/storage.py tests/desktop/test_storage.py
git commit -m "refactor: remove raid on restart profile config"
```

### Task 2: Replace profile-card restart/toggle controls with `Raid NOW!`

**Files:**
- Modify: `raidbot/desktop/main_window.py`
- Modify: `raidbot/desktop/theme.py`
- Test: `tests/desktop/test_main_window.py`

- [ ] **Step 1: Write the failing profile-card UI tests**

Add tests that assert:

```python
assert hasattr(card, "raid_now_button")
assert card.raid_now_button.text() == "Raid NOW!"
assert not hasattr(card, "restart_button")
assert not hasattr(card, "raid_on_restart_toggle")
```

and:

```python
assert card.raid_now_button.isEnabled() is False
window._handle_connection_state_changed("connected")
assert card.raid_now_button.isEnabled() is True
```

- [ ] **Step 2: Run the main-window slice to confirm failure**

Run: `python -m pytest -q tests\desktop\test_main_window.py -k "raid_now or raid_on_restart or profile_card"`

Expected: FAIL because the old restart/toggle controls still exist.

- [ ] **Step 3: Replace the card footer controls**

In `RaidProfileCard`:

- remove `restartRequested`
- remove `raidOnRestartChanged`
- add `raidNowRequested`
- remove `Restart`
- remove `Raid on Restart`
- add `self.raid_now_button = QPushButton("Raid NOW!")`

In `apply_state()`:

- stop referencing `profile.raid_on_restart`
- keep paused/red/green styling behavior
- do not hide the button when the profile is red

In `MainWindow._sync_raid_profile_cards()`:

- connect `raidNowRequested` to the new controller method

- [ ] **Step 4: Add connection-state-driven enablement**

Use the existing connection state flow in `MainWindow` to set each card’s `Raid NOW!` enabled state only when Telegram is `connected`.

- [ ] **Step 5: Run focused UI tests**

Run: `python -m pytest -q tests\desktop\test_main_window.py -k "raid_now or raid_on_restart or profile_action_cog or renders_raid_profile_cards"`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add raidbot/desktop/main_window.py raidbot/desktop/theme.py tests/desktop/test_main_window.py
git commit -m "feat: replace profile restart controls with raid now"
```

### Task 3: Add Telegram helper to fetch the latest valid recent raid candidate

**Files:**
- Modify: `raidbot/desktop/telegram_setup.py`
- Test: `tests/desktop/test_telegram_setup.py`

- [ ] **Step 1: Write the failing Telegram helper tests**

Add tests for a new helper that:

- iterates allowed chats newest-first
- converts messages into the same `IncomingMessage` shape used by live detection
- returns recent candidates in descending freshness order

Example expectation:

```python
result = asyncio.run(service.list_recent_messages([1001, 2002], message_limit=10))
assert result[0].chat_id == 2002
assert result[0].sender_id == 42
```

- [ ] **Step 2: Run the Telegram setup slice**

Run: `python -m pytest -q tests\desktop\test_telegram_setup.py -k "recent_messages or infer_recent_sender_candidates"`

Expected: FAIL because no recent-message helper exists yet.

- [ ] **Step 3: Implement the helper**

In `raidbot/desktop/telegram_setup.py`:

- add a focused helper that copies the session as current lookup helpers do
- reads recent messages from allowed chats
- yields or returns newest-first message records with:
  - `chat_id`
  - `sender_id`
  - `text`
  - `has_video`

Do not duplicate the raid-detection logic here. This helper only fetches candidates.

- [ ] **Step 4: Run the Telegram tests**

Run: `python -m pytest -q tests\desktop\test_telegram_setup.py -k "recent_messages or infer_recent_sender_candidates"`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/desktop/telegram_setup.py tests/desktop/test_telegram_setup.py
git commit -m "feat: add recent telegram raid lookup helper"
```

### Task 4: Add controller `run_raid_now_for_profile()` and manual-run gating

**Files:**
- Modify: `raidbot/desktop/controller.py`
- Test: `tests/desktop/test_controller.py`

- [ ] **Step 1: Write the failing controller tests**

Add coverage for:

```python
controller.run_raid_now_for_profile("Profile 3")
assert worker.run_raid_now_calls == ["Profile 3"]
```

and:

```python
controller._connection_state = "connecting"
controller.run_raid_now_for_profile("Profile 3")
assert errors == ["Telegram must be connected"]
```

Also cover queue/manual blocking using existing `_automation_queue_blocks_manual_actions()`.

- [ ] **Step 2: Run the controller slice**

Run: `python -m pytest -q tests\desktop\test_controller.py -k "raid_now or slot_test or troubleshoot_test"`

Expected: FAIL because the controller has no `run_raid_now_for_profile()` path.

- [ ] **Step 3: Implement the controller command**

In `raidbot/desktop/controller.py`:

- add `run_raid_now_for_profile(profile_directory: str)`
- reject when:
  - worker/runner not running
  - Telegram connection state is not `connected`
  - queue owns manual actions
- submit a worker call on the runner thread

Reuse existing manual-run lifecycle notifications so queue pausing/resume behavior stays consistent.

- [ ] **Step 4: Run the controller tests**

Run: `python -m pytest -q tests\desktop\test_controller.py -k "raid_now or slot_test or troubleshoot_test"`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/desktop/controller.py tests/desktop/test_controller.py
git commit -m "feat: add controller raid now command"
```

### Task 5: Implement worker-side latest-valid-raid lookup and single-profile execution

**Files:**
- Modify: `raidbot/desktop/worker.py`
- Test: `tests/desktop/test_worker.py`

- [ ] **Step 1: Write the failing worker tests**

Add tests for a new worker entry point, for example `run_raid_now_for_profile("Profile 3")`, that:

- fetches recent messages from allowed chats
- reuses `self._service.handle_message(...)`
- chooses the first valid `job_detected`
- executes only the requested profile

Example assertions:

```python
assert opener.open_raid_window_calls[0].profile_directory == "Profile 3"
assert worker.state.raids_detected == 1
assert worker.state.raids_opened == 1
```

Add a failure case:

```python
assert error_reason == "no_recent_valid_raid_found"
```

- [ ] **Step 2: Run the worker slice**

Run: `python -m pytest -q tests\desktop\test_worker.py -k "raid_now or latest_valid_raid or page_ready"`

Expected: FAIL because the worker has no such manual current-raid entry point.

- [ ] **Step 3: Implement worker-side `Raid NOW!`**

In `raidbot/desktop/worker.py`:

- add a worker method to run one chosen profile against the latest valid recent raid
- fetch candidates through the new Telegram helper
- pass each candidate through existing `RaidService.handle_message(...)`
- stop on the first `job_detected`
- build a one-profile execution path that reuses `_execute_raid_for_profile()`
- do not use `_latest_replayable_raid`

Keep failure reasons explicit:

- `telegram_recent_lookup_failed`
- `no_recent_valid_raid_found`
- normal automation failure reasons for actual execution

- [ ] **Step 4: Run the worker tests**

Run: `python -m pytest -q tests\desktop\test_worker.py -k "raid_now or latest_valid_raid or page_ready"`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/desktop/worker.py tests/desktop/test_worker.py
git commit -m "feat: run latest valid raid for a selected profile"
```

### Task 6: Remove remaining replay-on-restart references and verify end-to-end slices

**Files:**
- Modify: `raidbot/desktop/main_window.py`
- Modify: `raidbot/desktop/controller.py`
- Modify: `raidbot/desktop/worker.py`
- Test: `tests/desktop/test_main_window.py`
- Test: `tests/desktop/test_controller.py`
- Test: `tests/desktop/test_worker.py`
- Test: `tests/desktop/test_storage.py`

- [ ] **Step 1: Remove dead restart/toggle code paths**

Delete remaining now-unused references to:

- `restart_raid_profile()` from the profile-card UI path
- `set_raid_profile_raid_on_restart()` from the profile-card UI path
- replay-on-restart specific tests that no longer reflect shipped behavior

Do not remove unrelated replay internals unless they are truly unused by the codebase after `Raid NOW!` is wired.

- [ ] **Step 2: Run the combined targeted release slice**

Run:

```bash
python -m pytest -q tests\desktop\test_storage.py -k "raid_profile or raid_on_restart" tests\desktop\test_main_window.py -k "raid_now or profile_card" tests\desktop\test_controller.py -k "raid_now" tests\desktop\test_worker.py -k "raid_now or latest_valid_raid"
```

Expected: PASS

- [ ] **Step 3: Run a broader desktop confidence slice**

Run:

```bash
python -m pytest -q tests\desktop\test_main_window.py -k "profile or bot_actions or troubleshoot" tests\desktop\test_controller.py -k "slot_test or troubleshoot_test or raid_now" tests\desktop\test_worker.py -k "page_ready or raid_now or restart_raid_profile"
```

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add raidbot/desktop/main_window.py raidbot/desktop/controller.py raidbot/desktop/worker.py tests/desktop/test_main_window.py tests/desktop/test_controller.py tests/desktop/test_worker.py tests/desktop/test_storage.py
git commit -m "feat: ship raid now profile flow"
```
