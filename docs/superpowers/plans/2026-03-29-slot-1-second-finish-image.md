# Slot 1 Second Finish Image Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a second shared slot-1 finish capture so slot 1 clicks finish image 1, waits `0.5s`, then clicks finish image 2 before confirming UI change.

**Architecture:** Keep this as a narrow extension of the existing slot-1 preset flow. Persist one additional shared path on slot 1, expose one extra capture control in the slot-1 presets dialog, and extend the slot-1 runner branch to require and click the second finish image in order.

**Tech Stack:** Python, PySide6, existing desktop storage/config models, existing automation runner/tests, pytest, pytest-qt.

---

### Task 1: Persist `finish_template_path_2` On Slot 1

**Files:**
- Modify: `raidbot/desktop/models.py`
- Modify: `raidbot/desktop/storage.py`
- Test: `tests/desktop/test_storage.py`

- [ ] **Step 1: Write the failing storage round-trip test**

Add a regression beside the existing slot-1 preset storage test:

```python
def test_storage_round_trips_slot_1_second_finish_template(tmp_path) -> None:
    storage = DesktopStorage(tmp_path)
    config = DesktopAppConfig(
        ...,
        bot_action_slots=(
            BotActionSlotConfig(
                key="slot_1_r",
                label="R",
                enabled=True,
                finish_template_path=Path("bot_actions/slot_1_r_finish.png"),
                finish_template_path_2=Path("bot_actions/slot_1_r_finish_2.png"),
                presets=(BotActionPreset(id="preset-1", text="gm"),),
            ),
            *default_bot_action_slots()[1:],
        ),
    )

    storage.save_config(config)
    loaded = storage.load_config()

    assert loaded.bot_action_slots[0].finish_template_path_2 == Path(
        "bot_actions/slot_1_r_finish_2.png"
    )
```

- [ ] **Step 2: Run the storage test to verify it fails**

Run:

```powershell
python -m pytest -q tests\desktop\test_storage.py -k "second_finish_template"
```

Expected: FAIL because `BotActionSlotConfig` does not yet have `finish_template_path_2`.

- [ ] **Step 3: Add the minimal model and storage support**

Update `BotActionSlotConfig` and the slot normalization path:

```python
@dataclass(eq=True)
class BotActionSlotConfig:
    ...
    finish_template_path: Path | None = None
    finish_template_path_2: Path | None = None
```

Preserve it in:

```python
"finish_template_path_2": (
    str(slot.finish_template_path_2)
    if slot.finish_template_path_2 is not None
    else None
)
```

and load it back with:

```python
finish_template_path_2 = data.get("finish_template_path_2")
...
finish_template_path_2=(
    Path(finish_template_path_2) if finish_template_path_2 is not None else None
)
```

- [ ] **Step 4: Run the storage test to verify it passes**

Run:

```powershell
python -m pytest -q tests\desktop\test_storage.py -k "second_finish_template"
```

Expected: PASS

- [ ] **Step 5: Commit**

```powershell
git add raidbot/desktop/models.py raidbot/desktop/storage.py tests/desktop/test_storage.py
git commit -m "feat: persist slot 1 second finish image"
```

### Task 2: Add `Capture finish image 2` To The Slot-1 Presets Dialog

**Files:**
- Modify: `raidbot/desktop/bot_actions/presets_dialog.py`
- Modify: `raidbot/desktop/main_window.py`
- Test: `tests/desktop/bot_actions/test_presets_dialog.py`
- Test: `tests/desktop/test_main_window.py`

- [ ] **Step 1: Write the failing dialog and main-window tests**

Add one dialog-level test and one wiring test.

Dialog test shape:

```python
def test_slot_1_presets_dialog_tracks_second_finish_image(qtbot, tmp_path: Path) -> None:
    path_2 = tmp_path / "finish2.png"
    path_2.write_bytes(b"fake image")
    dialog = Slot1PresetsDialog(slot=_slot_1_config())
    qtbot.addWidget(dialog)

    dialog.finish_template_path_2 = path_2
    dialog.finish_image_2_status_label.setText(str(path_2))

    updated_slot = dialog.build_updated_slot()

    assert updated_slot.finish_template_path_2 == path_2
```

Main-window wiring test shape:

```python
def test_main_window_slot_1_presets_dialog_capture_updates_second_finish_preview(qtbot) -> None:
    finish_path_2 = Path("bot_actions/slot_1_r_finish_2.png")
    capture_service = FakeSlotCaptureService(finish_path_2)
    window = build_window(FakeController(), FakeStorage(), slot_capture_service=capture_service)
    qtbot.addWidget(window)

    qtbot.mouseClick(window.bot_actions_page.slot_boxes[0].presets_button, Qt.MouseButton.LeftButton)
    dialog = window._slot_1_presets_dialog
    qtbot.mouseClick(dialog.capture_finish_button_2, Qt.MouseButton.LeftButton)

    assert dialog.finish_template_path_2 == finish_path_2
    assert dialog.finish_image_2_status_label.text() == str(finish_path_2)
```

- [ ] **Step 2: Run the focused tests to verify they fail**

Run:

```powershell
python -m pytest -q tests\desktop\bot_actions\test_presets_dialog.py tests\desktop\test_main_window.py -k "second_finish"
```

Expected: FAIL because the second finish capture widgets and fields do not exist yet.

- [ ] **Step 3: Add the minimal UI and save wiring**

Extend `Slot1PresetsDialog` with:

```python
self.finish_image_2_status_label = QLabel(
    str(self.finish_template_path_2) if self.finish_template_path_2 is not None else "No finish image 2"
)
self.capture_finish_button_2 = QPushButton("Capture finish image 2")
```

Return it from `build_updated_slot()`:

```python
return replace(
    self._slot,
    presets=tuple(self._presets),
    finish_template_path=self.finish_template_path,
    finish_template_path_2=self.finish_template_path_2,
)
```

Extend main-window wiring with a dedicated handler:

```python
dialog.capture_finish_button_2.clicked.connect(self._capture_slot_1_finish_template_2)
```

and:

```python
finish_template_path_2 = self.slot_capture_service.capture_to_path(
    Path("bot_actions/slot_1_r_finish_2.png"),
    existing_path=dialog.finish_template_path_2,
)
dialog.finish_template_path_2 = finish_template_path_2
dialog.finish_image_2_status_label.setText(str(finish_template_path_2))
```

Persist it through:

```python
self.controller.set_bot_action_slot_1_presets(
    presets=updated_slot.presets,
    finish_template_path=updated_slot.finish_template_path,
    finish_template_path_2=updated_slot.finish_template_path_2,
)
```

- [ ] **Step 4: Run the focused tests to verify they pass**

Run:

```powershell
python -m pytest -q tests\desktop\bot_actions\test_presets_dialog.py tests\desktop\test_main_window.py -k "second_finish"
```

Expected: PASS

- [ ] **Step 5: Commit**

```powershell
git add raidbot/desktop/bot_actions/presets_dialog.py raidbot/desktop/main_window.py tests/desktop/bot_actions/test_presets_dialog.py tests/desktop/test_main_window.py
git commit -m "feat: add slot 1 second finish capture ui"
```

### Task 3: Extend Slot-1 Runtime To Click Finish Image 2

**Files:**
- Modify: `raidbot/desktop/controller.py`
- Modify: `raidbot/desktop/automation/models.py`
- Modify: `raidbot/desktop/automation/runner.py`
- Modify: `raidbot/desktop/bot_actions/sequence.py`
- Test: `tests/desktop/automation/test_runner.py`
- Test: `tests/desktop/bot_actions/test_sequence.py`
- Test: `tests/desktop/test_controller.py`

- [ ] **Step 1: Write the failing runtime tests**

Add two regressions:

```python
def test_runner_slot_1_clicks_finish_image_1_then_finish_image_2(tmp_path: Path) -> None:
    runner = SequenceRunner(...)
    result = runner.run_sequence(
        _sequence(
            _step(
                name="slot_1_r",
                preset_text="gm",
                finish_template_path=finish_1,
                finish_template_path_2=finish_2,
            )
        ),
        selected_window=_window(),
    )

    assert result.status == "completed"
    assert input_driver.clicks == [(25, 15), (45, 15), (65, 15)]
```

```python
def test_runner_slot_1_fails_when_second_finish_image_is_missing(tmp_path: Path) -> None:
    result = runner.run_sequence(
        _sequence(
            _step(
                name="slot_1_r",
                preset_text="gm",
                finish_template_path=finish_1,
                finish_template_path_2=missing_finish_2,
            )
        ),
        selected_window=_window(),
    )

    assert result.status == "failed"
    assert result.failure_reason == "finish_template_2_missing"
```

Also update sequence/controller expectations so the second finish path is carried through and mapped into a simple user-facing error.

- [ ] **Step 2: Run the focused tests to verify they fail**

Run:

```powershell
python -m pytest -q tests\desktop\automation\test_runner.py tests\desktop\bot_actions\test_sequence.py tests\desktop\test_controller.py -k "finish_image_2 or second_finish"
```

Expected: FAIL because the second finish path is not part of the step model or runtime yet.

- [ ] **Step 3: Implement the minimal runtime extension**

Add the extra field to `AutomationStep`:

```python
finish_template_path_2: Path | None = None
```

Carry it through sequence building:

```python
AutomationStep(
    name="slot_1_r",
    ...,
    finish_template_path=slot.finish_template_path,
    finish_template_path_2=slot.finish_template_path_2,
)
```

Extend slot-1 runtime:

```python
finish_template_path_2 = step.finish_template_path_2
if finish_template_path_2 is None or not Path(finish_template_path_2).exists():
    return RunResult(
        status="failed",
        failure_reason="finish_template_2_missing",
        window_handle=finish_window.handle,
        step_index=step_index,
    )

self.sleep(0.5)
finish_template_2 = self.template_loader(finish_template_path_2)
finish_location_2 = self._find_match_for_template(...)
...
self.input_driver.move_click(finish_point_2, delay_seconds=0.5)
confirmation = self._confirm_ui_changed_after_click(...)
```

Map the new reason in controller status text:

```python
"finish_template_2_missing": "finish image 2 missing",
```

- [ ] **Step 4: Run the focused tests to verify they pass**

Run:

```powershell
python -m pytest -q tests\desktop\automation\test_runner.py tests\desktop\bot_actions\test_sequence.py tests\desktop\test_controller.py -k "finish_image_2 or second_finish"
```

Expected: PASS

- [ ] **Step 5: Commit**

```powershell
git add raidbot/desktop/controller.py raidbot/desktop/automation/models.py raidbot/desktop/automation/runner.py raidbot/desktop/bot_actions/sequence.py tests/desktop/automation/test_runner.py tests/desktop/bot_actions/test_sequence.py tests/desktop/test_controller.py
git commit -m "feat: add slot 1 second finish runtime"
```

### Task 4: Final Verification

**Files:**
- Modify: none
- Test: entire suite

- [ ] **Step 1: Run the related focused tests**

Run:

```powershell
python -m pytest -q tests\desktop\test_storage.py tests\desktop\bot_actions\test_presets_dialog.py tests\desktop\test_main_window.py tests\desktop\bot_actions\test_sequence.py tests\desktop\automation\test_runner.py tests\desktop\test_controller.py
```

Expected: all pass

- [ ] **Step 2: Run the full suite**

Run:

```powershell
python -m pytest -q
```

Expected: full suite passes with no new failures

- [ ] **Step 3: Commit verification-only follow-up if needed**

If any tiny test-only cleanup was needed:

```powershell
git add <adjusted-files>
git commit -m "test: cover slot 1 second finish image flow"
```

- [ ] **Step 4: Manual smoke check**

Launch the app and validate:

1. Open slot 1 `Presets`
2. Capture `finish image`
3. Capture `finish image 2`
4. Save
5. Reopen `Presets` and confirm both are preserved
6. Run slot 1 test and verify:
   - text pastes
   - optional image pastes
   - finish image 1 clicks
   - finish image 2 clicks

