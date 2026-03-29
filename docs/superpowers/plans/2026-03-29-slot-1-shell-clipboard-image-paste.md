# Slot 1 Shell Clipboard Image Paste Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current slot-1 preset image `CF_HDROP`-only paste payload with a richer Windows shell clipboard payload that more closely matches Explorer copy/paste.

**Architecture:** Keep the public slot-1 runtime flow unchanged and swap only the low-level Windows clipboard behavior behind `paste_image_file(...)`. Preserve the old bitmap path for non-slot-1 uses and do not silently fall back to it if the new shell clipboard path fails.

**Tech Stack:** Python, pywin32 (`pythoncom`, `win32com.shell`, `win32clipboard`), existing desktop automation input/runner code, pytest.

---

### Task 1: Replace `CF_HDROP`-Only Paste With A Shell Clipboard Path

**Files:**
- Modify: `raidbot/desktop/automation/input.py`
- Test: `tests/desktop/automation/test_input.py`

- [ ] **Step 1: Write the failing input-layer test**

Add a regression that verifies `set_file_image(...)` no longer goes through the raw `CF_HDROP` helper path alone and instead uses a dedicated shell clipboard helper.

Example test shape:

```python
def test_input_driver_uses_shell_clipboard_path_for_file_image(monkeypatch, tmp_path: Path) -> None:
    import raidbot.desktop.automation.input as input_module

    events = []
    image_path = tmp_path / "reply.png"
    image_path.write_bytes(b"fake image")
    calls = []

    monkeypatch.setattr(
        input_module,
        "_set_windows_shell_file_clipboard",
        lambda path: calls.append(path),
    )

    driver = InputDriver(send_hotkey=events.append)
    driver.paste_image_file(image_path)

    assert calls == [image_path]
    assert events == [("ctrl", "v")]
```

- [ ] **Step 2: Run the focused input test to verify it fails**

Run:

```powershell
python -m pytest -q tests\desktop\automation\test_input.py -k "shell_clipboard_path"
```

Expected: FAIL because the shell clipboard helper does not exist yet.

- [ ] **Step 3: Implement the minimal shell clipboard helper**

Inside `input.py`:

- keep `paste_image(...)` unchanged
- keep `paste_image_file(...)` public method unchanged
- replace the `CF_HDROP`-only implementation behind `set_file_image(...)`

Refactor shape:

```python
class _WindowsClipboard:
    def set_file_image(self, image_path: Path) -> None:
        _set_windows_shell_file_clipboard(Path(image_path))
```

Add a dedicated helper:

```python
def _set_windows_shell_file_clipboard(image_path: Path) -> None:
    ...
```

Use the Windows shell/COM modules already confirmed present:

- `pythoncom`
- `win32com.shell`
- `win32clipboard`

Do not keep the old raw `CF_HDROP`-only implementation as the slot-1 path.

- [ ] **Step 4: Run the focused input test to verify it passes**

Run:

```powershell
python -m pytest -q tests\desktop\automation\test_input.py -k "shell_clipboard_path"
```

Expected: PASS

- [ ] **Step 5: Commit**

```powershell
git add raidbot/desktop/automation/input.py tests/desktop/automation/test_input.py
git commit -m "feat: add shell clipboard file paste path"
```

### Task 2: Keep Slot 1 Bound To `paste_image_file(...)`

**Files:**
- Modify: `tests/desktop/automation/test_runner.py`
- Modify: `raidbot/desktop/automation/runner.py` only if needed

- [ ] **Step 1: Confirm the slot-1 runner regression still targets `paste_image_file(...)`**

Ensure the existing slot-1 runner test still asserts:

```python
assert input_driver.file_pasted_images == [reply_image_path]
assert input_driver.pasted_images == []
```

If no code change is needed in `runner.py`, leave it alone.

- [ ] **Step 2: Run the focused slot-1 runner tests**

Run:

```powershell
python -m pytest -q tests\desktop\automation\test_runner.py -k "slot_1"
```

Expected: PASS if the shell-clipboard refactor did not disturb slot-1 routing.

- [ ] **Step 3: Commit only if runner/test adjustments were required**

```powershell
git add raidbot/desktop/automation/runner.py tests/desktop/automation/test_runner.py
git commit -m "test: keep slot 1 bound to file clipboard path"
```

### Task 3: Final Verification

**Files:**
- Modify: none unless a tiny verification-only cleanup is needed

- [ ] **Step 1: Run the focused verification suite**

Run:

```powershell
python -m pytest -q tests\desktop\automation\test_input.py tests\desktop\automation\test_runner.py
```

Expected: all pass

- [ ] **Step 2: Run the full suite**

Run:

```powershell
python -m pytest -q
```

Expected: full suite passes

- [ ] **Step 3: Commit any tiny verification-only cleanup if needed**

```powershell
git add <adjusted-files>
git commit -m "test: cover slot 1 shell clipboard paste"
```

- [ ] **Step 4: Manual smoke check**

Launch the app and validate:

1. configure a slot-1 preset with text + image
2. run slot-1 test
3. verify text still pastes first
4. verify the image now uses the richer shell clipboard path
5. compare the result against manual Explorer copy/paste behavior
