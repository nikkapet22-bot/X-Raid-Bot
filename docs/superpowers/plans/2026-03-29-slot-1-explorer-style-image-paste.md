# Slot 1 Explorer-Style Image Paste Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make slot-1 preset image paste mimic Windows Explorer file copy/paste instead of the current bitmap clipboard paste.

**Architecture:** Keep the existing bitmap paste path intact in the input layer, add a second Windows-specific file-reference clipboard paste path, and switch only the slot-1 preset image runtime branch to use that new method. This keeps the change narrow and reversible.

**Tech Stack:** Python, pywin32, existing desktop automation input/runner code, pytest.

---

### Task 1: Add A File-Reference Clipboard Paste Path

**Files:**
- Modify: `raidbot/desktop/automation/input.py`
- Test: `tests/desktop/automation/test_input.py`

- [ ] **Step 1: Write the failing input-layer tests**

Add a regression beside the current clipboard tests:

```python
def test_input_driver_pastes_image_file_reference_then_ctrl_v(tmp_path: Path) -> None:
    image_path = tmp_path / "reply.png"
    image_path.write_bytes(b"fake image")
    events = []
    clipboard = FakeClipboard()
    driver = InputDriver(send_hotkey=events.append, clipboard=clipboard)

    driver.paste_image_file(image_path)

    assert clipboard.file_image_path == image_path
    assert events == [("ctrl", "v")]
```

Also extend the default-backend test to verify the Windows clipboard backend exposes the file-reference path.

- [ ] **Step 2: Run the focused input tests to verify they fail**

Run:

```powershell
python -m pytest -q tests\desktop\automation\test_input.py -k "file_reference or paste_image_file"
```

Expected: FAIL because `paste_image_file(...)` does not exist yet.

- [ ] **Step 3: Implement the minimal file-reference clipboard path**

Add a second public method:

```python
def paste_image_file(self, image_path: Path) -> None:
    if not Path(image_path).exists():
        raise FileNotFoundError(str(image_path))
    self._clipboard.set_file_image(Path(image_path))
    self._send_hotkey(("ctrl", "v"))
```

Keep the current bitmap path untouched.

Add a matching clipboard backend method:

```python
class _WindowsClipboard:
    def set_file_image(self, image_path: Path) -> None:
        ...
```

Use a Windows file-drop style clipboard payload for the image file path.

- [ ] **Step 4: Run the focused input tests to verify they pass**

Run:

```powershell
python -m pytest -q tests\desktop\automation\test_input.py -k "file_reference or paste_image_file"
```

Expected: PASS

- [ ] **Step 5: Commit**

```powershell
git add raidbot/desktop/automation/input.py tests/desktop/automation/test_input.py
git commit -m "feat: add file-reference image paste path"
```

### Task 2: Switch Slot 1 Preset Images To Explorer-Style Paste

**Files:**
- Modify: `raidbot/desktop/automation/runner.py`
- Test: `tests/desktop/automation/test_runner.py`

- [ ] **Step 1: Write the failing slot-1 runner regression**

Extend the existing slot-1 preset image test to assert the runner uses the new method:

```python
class FakeInputDriver:
    ...
    self.file_pasted_images = []

    def paste_image_file(self, image_path: Path) -> None:
        self.file_pasted_images.append(image_path)
```

Then assert:

```python
assert input_driver.file_pasted_images == [reply_image_path]
assert input_driver.pasted_images == []
```

- [ ] **Step 2: Run the focused slot-1 runner test to verify it fails**

Run:

```powershell
python -m pytest -q tests\desktop\automation\test_runner.py -k "slot_1 and file_paste"
```

Expected: FAIL because slot 1 still calls `paste_image(...)`.

- [ ] **Step 3: Implement the minimal runtime switch**

In the slot-1 preset branch, change only:

```python
self.input_driver.paste_image_file(Path(step.preset_image_path))
```

Do not change text paste ordering or the rest of the slot-1 flow.

- [ ] **Step 4: Run the focused slot-1 runner test to verify it passes**

Run:

```powershell
python -m pytest -q tests\desktop\automation\test_runner.py -k "slot_1 and file_paste"
```

Expected: PASS

- [ ] **Step 5: Commit**

```powershell
git add raidbot/desktop/automation/runner.py tests/desktop/automation/test_runner.py
git commit -m "feat: use file-reference paste for slot 1 images"
```

### Task 3: Final Verification

**Files:**
- Modify: none unless a tiny test-only adjustment is needed

- [ ] **Step 1: Run the related focused tests**

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
git commit -m "test: cover slot 1 explorer-style image paste"
```

- [ ] **Step 4: Manual smoke check**

Launch the app and validate:

1. Configure a slot-1 preset with text + image
2. Run slot 1 test
3. Confirm text pastes first
4. Confirm the preset image is inserted through the new Explorer-style path
5. Compare behavior against your manual Explorer `Ctrl+C` / `Ctrl+V` flow
