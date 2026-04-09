# Global Pause Hotkey And Clipboard Retry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a system-wide configurable pause/resume hotkey that pauses active raids immediately and resumes the interrupted run before queued raids, while also hardening reply image pasting against transient Windows clipboard locks.

**Architecture:** Keep the feature inside the existing desktop app. Persist the hotkey in desktop config, capture it in Settings, register it through a small Windows hotkey helper in the main window, and route presses through new controller/worker pause-resume APIs. Extend the automation queue/runtime so a hotkey pause suspends the current run without dropping queued raids, and add bounded retry around Windows clipboard operations used by slot 1 image pasting.

**Tech Stack:** PySide6, Windows native hotkey APIs, existing desktop controller/worker runtime, pytest

---

### Task 1: Persist the pause/resume hotkey in desktop config

**Files:**
- Modify: `raidbot/desktop/models.py`
- Modify: `raidbot/desktop/storage.py`
- Test: `tests/desktop/test_storage.py`

- [ ] **Step 1: Write the failing storage tests**

Add coverage for:

```python
def test_storage_round_trips_pause_resume_hotkey(tmp_path: Path) -> None:
    storage = DesktopStorage(tmp_path)
    config = build_config(pause_resume_hotkey="Ctrl+P")

    storage.save_config(config)
    loaded = storage.load_config()

    assert loaded.pause_resume_hotkey == "Ctrl+P"
```

and:

```python
def test_storage_defaults_pause_resume_hotkey_to_none(tmp_path: Path) -> None:
    storage = DesktopStorage(tmp_path)
    storage.save_config(build_config())

    loaded = storage.load_config()

    assert loaded.pause_resume_hotkey is None
```

- [ ] **Step 2: Run the storage slice to confirm failure**

Run: `python -m pytest -q tests\desktop\test_storage.py -k "pause_resume_hotkey or hotkey"`

Expected: FAIL because `DesktopAppConfig` and storage do not yet own the field.

- [ ] **Step 3: Add the config field and serializer support**

Update:

- `DesktopAppConfig` in `raidbot/desktop/models.py`
- `_config_to_data()` in `raidbot/desktop/storage.py`
- `_config_from_data()` in `raidbot/desktop/storage.py`

Rules:

- add `pause_resume_hotkey: str | None = None`
- persist it as a plain string
- normalize blank values back to `None`
- keep older configs loading cleanly without the field

- [ ] **Step 4: Run the focused storage tests**

Run: `python -m pytest -q tests\desktop\test_storage.py -k "pause_resume_hotkey or hotkey"`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/desktop/models.py raidbot/desktop/storage.py tests/desktop/test_storage.py
git commit -m "feat: persist pause resume hotkey config"
```

### Task 2: Add Windows hotkey parsing, capture, and registration helpers

**Files:**
- Create: `raidbot/desktop/hotkeys.py`
- Test: `tests/desktop/test_hotkeys.py`

- [ ] **Step 1: Write the failing hotkey helper tests**

Add coverage for:

```python
def test_normalize_ctrl_hotkey_accepts_ctrl_letter() -> None:
    assert normalize_ctrl_hotkey("Ctrl+P") == "Ctrl+P"
```

```python
def test_normalize_ctrl_hotkey_rejects_non_ctrl_combo() -> None:
    with pytest.raises(ValueError, match="Ctrl"):
        normalize_ctrl_hotkey("Alt+P")
```

```python
def test_windows_hotkey_registrar_dispatches_registered_callback() -> None:
    fired = []
    registrar = WindowsGlobalHotkeyRegistrar(
        register_hotkey=lambda *_args: True,
        unregister_hotkey=lambda *_args: None,
    )
    registrar.set_hotkey("Ctrl+P", lambda: fired.append(True))

    registrar.handle_hotkey_message(registrar.hotkey_id)

    assert fired == [True]
```

- [ ] **Step 2: Run the helper tests to verify they fail**

Run: `python -m pytest -q tests\desktop\test_hotkeys.py`

Expected: FAIL because the hotkey helper module does not exist yet.

- [ ] **Step 3: Implement the helper module**

In `raidbot/desktop/hotkeys.py`:

- add `normalize_ctrl_hotkey(...)`
- add a small capture-aware widget/helper for `Ctrl + key` entry
- add `WindowsGlobalHotkeyRegistrar` that:
  - registers a single configured hotkey
  - unregisters old registrations safely
  - handles `WM_HOTKEY`
  - exposes a callback-based dispatch hook

Rules:

- accept only `Ctrl + key`
- keep all Windows-specific code in this file
- allow dependency injection so tests do not need real OS registration

- [ ] **Step 4: Run the helper tests**

Run: `python -m pytest -q tests\desktop\test_hotkeys.py`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/desktop/hotkeys.py tests/desktop/test_hotkeys.py
git commit -m "feat: add windows pause hotkey helpers"
```

### Task 3: Add the hotkey capture field to Settings

**Files:**
- Modify: `raidbot/desktop/settings_page.py`
- Test: `tests/desktop/test_settings_page.py`

- [ ] **Step 1: Write the failing Settings tests**

Add coverage for:

```python
assert hasattr(page, "pause_resume_hotkey_input")
```

and:

```python
page.pause_resume_hotkey_input.set_hotkey("Ctrl+P")
page._emit_apply_request()
assert captured_config.pause_resume_hotkey == "Ctrl+P"
```

and:

```python
page.pause_resume_hotkey_input.set_invalid_state("Alt+P")
page._emit_apply_request()
assert "Ctrl" in page.status_label.text()
```

- [ ] **Step 2: Run the Settings slice to verify failure**

Run: `python -m pytest -q tests\desktop\test_settings_page.py -k "hotkey or settings"`

Expected: FAIL because Settings has no hotkey field yet.

- [ ] **Step 3: Add the Settings capture control**

In `raidbot/desktop/settings_page.py`:

- import the hotkey capture helper from `raidbot/desktop/hotkeys.py`
- add a `Pause / Resume Hotkey` row in the Settings form
- initialize it from `config.pause_resume_hotkey`
- include the normalized value in `_build_config()`

Rules:

- clicking the field must enter capture mode
- only valid `Ctrl + key` combos should save
- blank should mean `None`

- [ ] **Step 4: Run the focused Settings tests**

Run: `python -m pytest -q tests\desktop\test_settings_page.py -k "hotkey or settings"`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/desktop/settings_page.py tests/desktop/test_settings_page.py
git commit -m "feat: add settings pause hotkey capture"
```

### Task 4: Extend the auto-run processor to support user pause without dropping queued raids

**Files:**
- Modify: `raidbot/desktop/automation/autorun.py`
- Test: `tests/desktop/automation/test_autorun.py`

- [ ] **Step 1: Write the failing autorun tests**

Add coverage for:

```python
def test_autorun_processor_user_pause_keeps_accepting_new_items() -> None:
    processor.request_user_pause(current_item, current_context)
    assert processor.admit(build_item(trace_id="queued-2")) is True
    assert processor.state == "suspended"
```

and:

```python
def test_autorun_processor_resume_retries_interrupted_item_before_pending_queue() -> None:
    processor.request_user_pause(current_item, current_context)
    processor.admit(build_item(trace_id="queued-2"))
    processor.resume()
    assert execute_calls[0][0].trace_id == current_item.trace_id
```

- [ ] **Step 2: Run the autorun tests to confirm failure**

Run: `python -m pytest -q tests\desktop\automation\test_autorun.py -k "user_pause or suspended or resume"`

Expected: FAIL because the processor only knows `idle`, `queued`, `running`, and failure `paused`.

- [ ] **Step 3: Add an explicit user-suspended state**

In `raidbot/desktop/automation/autorun.py`:

- add a distinct state for hotkey/user pause
- keep the current interrupted item/context
- allow `admit()` while user-suspended
- ensure `resume()` retries the interrupted item/context before queued items
- keep existing failure-paused semantics unchanged

- [ ] **Step 4: Run the autorun tests**

Run: `python -m pytest -q tests\desktop\automation\test_autorun.py -k "user_pause or suspended or resume"`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/desktop/automation/autorun.py tests/desktop/automation/test_autorun.py
git commit -m "feat: add user suspended autorun state"
```

### Task 5: Add worker/controller hotkey pause-resume and interrupted-run snapshots

**Files:**
- Modify: `raidbot/desktop/controller.py`
- Modify: `raidbot/desktop/worker.py`
- Test: `tests/desktop/test_controller.py`
- Test: `tests/desktop/test_worker.py`

- [ ] **Step 1: Write the failing controller and worker tests**

Add controller coverage for:

```python
controller.toggle_pause_resume()
assert worker.pause_hotkey_calls == 1
controller._hotkey_pause_state = True
controller.toggle_pause_resume()
assert worker.resume_hotkey_calls == 1
```

Add worker coverage for:

```python
worker.request_hotkey_pause()
assert runtime.request_stop_calls == 1
assert worker.is_hotkey_paused() is True
```

```python
worker._handle_message(build_message("Likes 10 | 8 [%]\\n\\nhttps://x.com/i/status/222"))
assert worker.state.automation_queue_length == 1
```

```python
worker.resume_hotkey_pause()
assert resumed_run_urls[0] == interrupted_url
```

- [ ] **Step 2: Run the focused controller/worker slice**

Run: `python -m pytest -q tests\desktop\test_controller.py -k "hotkey or pause_resume" tests\desktop\test_worker.py -k "hotkey or interrupted_run or queue_length"`

Expected: FAIL because neither controller nor worker owns hotkey pause state yet.

- [ ] **Step 3: Add controller toggle and worker event plumbing**

In `raidbot/desktop/controller.py`:

- add `toggle_pause_resume()`
- track current hotkey pause state from worker events
- submit `request_hotkey_pause()` or `resume_hotkey_pause()` onto the worker runner

In `raidbot/desktop/worker.py`:

- add hotkey pause state
- add an interrupted-run snapshot for:
  - auto-run
  - `Raid NOW!`
  - warmup browse
  - warmup real action
- when `runtime.run_sequence(...)` returns `stopped` under an active hotkey pause:
  - do not mark the profile failed
  - store the safe resume boundary instead

- [ ] **Step 4: Resume from the safe step boundary**

Continue the worker changes so resume:

- runs the interrupted profile first
- restarts from the current safe step boundary
- fails normally if the saved window/context is gone
- then drains queued raids

Keep the existing failure-driven auto-run paused state distinct from hotkey pause.

- [ ] **Step 5: Run the controller/worker tests**

Run: `python -m pytest -q tests\desktop\test_controller.py -k "hotkey or pause_resume" tests\desktop\test_worker.py -k "hotkey or interrupted_run or queue_length or raid_now"`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add raidbot/desktop/controller.py raidbot/desktop/worker.py tests/desktop/test_controller.py tests/desktop/test_worker.py
git commit -m "feat: add hotkey pause resume runtime flow"
```

### Task 6: Register the system-wide hotkey in the main window

**Files:**
- Modify: `raidbot/desktop/main_window.py`
- Test: `tests/desktop/test_main_window.py`

- [ ] **Step 1: Write the failing main-window tests**

Add coverage for:

```python
window._sync_config(build_config(pause_resume_hotkey="Ctrl+P"))
assert registrar.register_calls == ["Ctrl+P"]
```

and:

```python
registrar.fire_registered_hotkey()
assert controller.pause_resume_toggle_calls == 1
```

and:

```python
window._sync_config(build_config(pause_resume_hotkey="Ctrl+Q"))
assert registrar.unregister_calls == 1
assert registrar.register_calls[-1] == "Ctrl+Q"
```

- [ ] **Step 2: Run the main-window slice to confirm failure**

Run: `python -m pytest -q tests\desktop\test_main_window.py -k "hotkey or pause_resume or settings"`

Expected: FAIL because the main window does not manage a global hotkey registrar.

- [ ] **Step 3: Wire registration and dispatch**

In `raidbot/desktop/main_window.py`:

- create/load the hotkey registrar
- register the configured hotkey after config load
- re-register when config changes
- unregister on shutdown
- route hotkey callbacks to `controller.toggle_pause_resume()`
- surface registration failures through the existing error path

- [ ] **Step 4: Run the focused main-window tests**

Run: `python -m pytest -q tests\desktop\test_main_window.py -k "hotkey or pause_resume or settings"`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/desktop/main_window.py tests/desktop/test_main_window.py
git commit -m "feat: register global pause resume hotkey"
```

### Task 7: Add bounded retry around Windows clipboard operations

**Files:**
- Modify: `raidbot/desktop/automation/input.py`
- Test: `tests/desktop/automation/test_input.py`

- [ ] **Step 1: Write the failing clipboard retry tests**

Add coverage for:

```python
def test_input_driver_retries_file_image_clipboard_when_first_attempt_fails(tmp_path: Path) -> None:
    driver = InputDriver(clipboard=FlakyClipboard(failures=1), wait=waits.append, send_hotkey=events.append)
    driver.paste_image_file(image_path)
    assert clipboard.file_image_calls == 2
    assert events[-1] == ("ctrl", "v")
```

and:

```python
def test_input_driver_raises_after_clipboard_retry_exhaustion(tmp_path: Path) -> None:
    driver = InputDriver(clipboard=FlakyClipboard(failures=10), wait=waits.append, send_hotkey=events.append)
    with pytest.raises(RuntimeError, match="OpenClipboard Failed"):
        driver.paste_image_file(image_path)
```

- [ ] **Step 2: Run the input tests to verify failure**

Run: `python -m pytest -q tests\desktop\automation\test_input.py -k "clipboard or paste_image_file"`

Expected: FAIL because clipboard writes are currently single-shot.

- [ ] **Step 3: Implement bounded retry in the input layer**

In `raidbot/desktop/automation/input.py`:

- add a small retry helper around clipboard set operations
- use it for:
  - `paste_image_file(...)`
  - shared clipboard write paths where the same transient failure can happen
- keep retry count and wait short and bounded
- preserve the real error if all retries fail

- [ ] **Step 4: Run the focused input tests**

Run: `python -m pytest -q tests\desktop\automation\test_input.py -k "clipboard or paste_image_file"`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/desktop/automation/input.py tests/desktop/automation/test_input.py
git commit -m "fix: retry transient clipboard failures for reply images"
```

### Task 8: Bump version to `v2.2.0` and run the release-facing regression slice

**Files:**
- Modify: `pyproject.toml`
- Modify: `raidbot/__init__.py`
- Test: `tests/desktop/test_packaging.py`

- [ ] **Step 1: Update version assertions**

Adjust packaging/version expectations to `2.2.0`.

- [ ] **Step 2: Bump the app version**

Update:

- `pyproject.toml`
- `raidbot/__init__.py`
- any packaging/version test fixtures that assert the version string

- [ ] **Step 3: Run the release-facing regression slice**

Run: `python -m pytest -q tests\desktop\test_packaging.py tests\desktop\test_storage.py -k "version or hotkey or pause_resume" tests\desktop\test_settings_page.py -k "hotkey" tests\desktop\test_hotkeys.py tests\desktop\automation\test_autorun.py -k "user_pause or suspended or resume" tests\desktop\test_controller.py -k "hotkey or pause_resume" tests\desktop\test_worker.py -k "hotkey or interrupted_run or queue_length or raid_now" tests\desktop\test_main_window.py -k "hotkey or pause_resume or settings" tests\desktop\automation\test_input.py -k "clipboard or paste_image_file"`

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml raidbot/__init__.py tests/desktop/test_packaging.py
git commit -m "chore: bump version to v2.2.0"
```
