# Slot 1 Presets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a slot-1-only `Presets` modal so slot 1 can choose a random saved text/image preset, paste it into Chrome, and finish the action with a shared finish-image click.

**Architecture:** Keep the existing fixed 4-slot Bot Actions UI and extend only slot 1. Persist slot-1 preset data on `BotActionSlotConfig`, add a small slot-1 modal for editing that data, and extend the existing automation step/runner path with a narrow slot-1 preset-aware branch instead of creating a second runtime.

**Tech Stack:** Python, PySide6 desktop app, existing bot action capture flow, existing automation runtime (`models.py`, `runner.py`, `input.py`), pytest

---

## File Map

### Create

- `raidbot/desktop/bot_actions/presets_dialog.py`
  - Slot-1-only modal for editing preset text, optional preset image, and the shared finish image.
- `tests/desktop/bot_actions/test_presets_dialog.py`
  - Covers add/remove/save behavior and finish-image capture state in the new modal.

### Modify

- `raidbot/desktop/models.py`
  - Add persisted slot-1 preset data structures and normalize them with the fixed 4-slot layout.
- `raidbot/desktop/storage.py`
  - Serialize and deserialize slot-1 presets and shared finish image without breaking old configs.
- `raidbot/desktop/bot_actions/page.py`
  - Add `Presets` button only on slot 1 and emit a dedicated signal for it.
- `raidbot/desktop/bot_actions/capture.py`
  - Add a generic "capture to explicit path" helper so slot 1 can save its shared finish image without pretending it is another slot.
- `raidbot/desktop/bot_actions/sequence.py`
  - Build slot-1 preset-aware automation steps and return skip warnings when slot 1 is enabled with no presets.
- `raidbot/desktop/automation/models.py`
  - Extend `AutomationStep` with the narrow metadata needed for slot-1 preset execution.
- `raidbot/desktop/automation/input.py`
  - Add paste-text and paste-image primitives that reuse the current input/hotkey path.
- `raidbot/desktop/automation/runner.py`
  - Execute slot-1 preset-aware steps: paste text, optionally paste an image, then find/click the shared finish image.
- `raidbot/desktop/controller.py`
  - Persist slot-1 preset data, reject invalid slot-1 tests early, and keep slot-test result mapping clear.
- `raidbot/desktop/main_window.py`
  - Open the slot-1 modal, wire save/capture actions, and surface skip/failure messages cleanly in the Bot Actions status area.
- `raidbot/desktop/worker.py`
  - Consume slot-1 skip warnings during Telegram-triggered runs and keep later enabled slots running.
- `tests/desktop/bot_actions/test_models.py`
  - Cover slot-1 preset defaults and config normalization.
- `tests/desktop/test_storage.py`
  - Cover config round-trip for slot-1 presets and finish image.
- `tests/desktop/bot_actions/test_page.py`
  - Cover slot-1 `Presets` button visibility and signal wiring.
- `tests/desktop/bot_actions/test_sequence.py`
  - Cover slot-1 preset-aware sequence building and skip behavior.
- `tests/desktop/automation/test_input.py`
  - Cover paste-text and paste-image helpers.
- `tests/desktop/automation/test_runner.py`
  - Cover slot-1 multi-step execution behavior.
- `tests/desktop/test_controller.py`
  - Cover slot-1 preset persistence and slot-test validation.
- `tests/desktop/test_main_window.py`
  - Cover slot-1 modal launch/save wiring and status updates.
- `tests/desktop/test_worker.py`
  - Cover slot-1 skip-warning behavior during Telegram-triggered runs.

### Do Not Touch Unless A Failing Test Proves It

- `raidbot/desktop/settings_page.py`
- `raidbot/desktop/automation/windowing.py`
- `raidbot/desktop/automation/autorun.py`

This feature is slot-1-specific Bot Actions work, not another queueing/window-selection redesign.

---

### Task 1: Persist Slot-1 Presets And Finish Image

**Files:**
- Modify: `raidbot/desktop/models.py`
- Modify: `raidbot/desktop/storage.py`
- Modify: `tests/desktop/bot_actions/test_models.py`
- Modify: `tests/desktop/test_storage.py`

- [ ] **Step 1: Write the failing model/storage tests**

```python
def test_default_bot_action_slots_include_empty_slot_1_preset_state() -> None:
    slot_1 = default_bot_action_slots()[0]
    assert slot_1.presets == ()
    assert slot_1.finish_template_path is None


def test_storage_round_trips_slot_1_presets_and_finish_template(tmp_path: Path) -> None:
    storage = DesktopStorage(tmp_path)
    config = DesktopAppConfig(
        ...,
        bot_action_slots=(
            BotActionSlotConfig(
                key="slot_1_r",
                label="R",
                enabled=True,
                template_path=Path("bot_actions/slot_1_r.png"),
                finish_template_path=Path("bot_actions/slot_1_r_finish.png"),
                presets=(
                    BotActionPreset(
                        id="preset-1",
                        text="gm",
                        image_path=Path("bot_actions/presets/gm.png"),
                    ),
                ),
            ),
            *default_bot_action_slots()[1:],
        ),
    )

    storage.save_config(config)
    loaded = storage.load_config()

    assert loaded.bot_action_slots[0].presets == config.bot_action_slots[0].presets
    assert loaded.bot_action_slots[0].finish_template_path == Path(
        "bot_actions/slot_1_r_finish.png"
    )
```

- [ ] **Step 2: Run the targeted tests to verify they fail**

Run:

```bash
python -m pytest -q tests/desktop/bot_actions/test_models.py tests/desktop/test_storage.py
```

Expected:
- FAIL because `BotActionPreset`, `presets`, and `finish_template_path` do not exist yet

- [ ] **Step 3: Implement the minimal model/storage changes**

```python
@dataclass(eq=True)
class BotActionPreset:
    id: str
    text: str
    image_path: Path | None = None


@dataclass(eq=True)
class BotActionSlotConfig:
    key: str
    label: str
    enabled: bool = False
    template_path: Path | None = None
    updated_at: str | None = None
    presets: tuple[BotActionPreset, ...] = ()
    finish_template_path: Path | None = None
```

Then:
- keep slot defaults empty for all 4 slots
- normalize loaded/provided slots through the fixed `slot_1_r`, `slot_2_l`, `slot_3_r`, `slot_4_b` layout
- round-trip preset data and finish-template path in `DesktopStorage`
- keep older configs loading cleanly with empty preset state

- [ ] **Step 4: Run the targeted tests to verify they pass**

Run:

```bash
python -m pytest -q tests/desktop/bot_actions/test_models.py tests/desktop/test_storage.py
```

Expected:
- PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/desktop/models.py raidbot/desktop/storage.py tests/desktop/bot_actions/test_models.py tests/desktop/test_storage.py
git commit -m "feat: persist slot 1 preset data"
```

---

### Task 2: Add The Slot-1 Presets Modal And Button

**Files:**
- Create: `raidbot/desktop/bot_actions/presets_dialog.py`
- Modify: `raidbot/desktop/bot_actions/page.py`
- Modify: `tests/desktop/bot_actions/test_page.py`
- Create: `tests/desktop/bot_actions/test_presets_dialog.py`

- [ ] **Step 1: Write the failing UI tests**

```python
def test_bot_actions_page_shows_presets_button_only_for_slot_1(qtbot) -> None:
    page = BotActionsPage(config=build_config())
    assert page.slot_boxes[0].presets_button is not None
    assert page.slot_boxes[1].presets_button is None


def test_slot_1_presets_dialog_adds_removes_and_saves_presets(qtbot) -> None:
    dialog = Slot1PresetsDialog(slot=slot_1_config())
    dialog.add_preset()
    dialog.current_text_edit.setPlainText("gm")
    dialog.add_preset()
    dialog.remove_selected_preset()

    updated_slot = dialog.build_updated_slot()

    assert updated_slot.presets == (
        BotActionPreset(id=updated_slot.presets[0].id, text="gm", image_path=None),
    )
```

- [ ] **Step 2: Run the targeted tests to verify they fail**

Run:

```bash
python -m pytest -q tests/desktop/bot_actions/test_page.py tests/desktop/bot_actions/test_presets_dialog.py
```

Expected:
- FAIL because slot 1 has no `Presets` button and the dialog module does not exist

- [ ] **Step 3: Implement the slot-1-only modal and page signal**

```python
class SlotBox(QFrame):
    def __init__(...):
        ...
        self.presets_button: QPushButton | None = None
        if slot.key == "slot_1_r":
            self.presets_button = QPushButton("Presets")
            self.button_row_layout.addWidget(self.presets_button)


class BotActionsPage(QWidget):
    slotPresetsRequested = Signal(int)
```

Create `Slot1PresetsDialog` with:
- preset list
- add/remove buttons
- text editor for the selected preset
- optional image upload/clear controls for the selected preset
- shared finish-image preview and `Capture finish image` button
- `Save` / `Cancel`

Keep the dialog slot-1-specific. Do not generalize it for other slots.

- [ ] **Step 4: Run the targeted tests to verify they pass**

Run:

```bash
python -m pytest -q tests/desktop/bot_actions/test_page.py tests/desktop/bot_actions/test_presets_dialog.py
```

Expected:
- PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/desktop/bot_actions/page.py raidbot/desktop/bot_actions/presets_dialog.py tests/desktop/bot_actions/test_page.py tests/desktop/bot_actions/test_presets_dialog.py
git commit -m "feat: add slot 1 presets dialog"
```

---

### Task 3: Wire Slot-1 Preset Save And Finish Capture Through The Desktop UI

**Files:**
- Modify: `raidbot/desktop/bot_actions/capture.py`
- Modify: `raidbot/desktop/controller.py`
- Modify: `raidbot/desktop/main_window.py`
- Modify: `tests/desktop/test_controller.py`
- Modify: `tests/desktop/test_main_window.py`

- [ ] **Step 1: Write the failing controller/main-window tests**

```python
def test_controller_persists_slot_1_presets_and_finish_template(qtbot) -> None:
    controller = DesktopController(...)
    presets = (
        BotActionPreset(id="preset-1", text="gm", image_path=Path("preset.png")),
    )

    controller.set_bot_action_slot_1_presets(
        presets=presets,
        finish_template_path=Path("finish.png"),
    )

    saved_slot = controller.config.bot_action_slots[0]
    assert saved_slot.presets == presets
    assert saved_slot.finish_template_path == Path("finish.png")


def test_main_window_slot_1_presets_dialog_capture_updates_finish_preview(qtbot) -> None:
    window = MainWindow(...)
    window._open_slot_1_presets_dialog()
    window._capture_slot_1_finish_template()
    assert window._slot_1_presets_dialog.finish_template_path == Path(
        "bot_actions/slot_1_r_finish.png"
    )
```

- [ ] **Step 2: Run the targeted tests to verify they fail**

Run:

```bash
python -m pytest -q tests/desktop/test_controller.py tests/desktop/test_main_window.py -k "slot_1_preset or finish_template"
```

Expected:
- FAIL because there is no slot-1 preset persistence method and no finish-image capture wiring

- [ ] **Step 3: Implement the minimal controller/window plumbing**

```python
class DesktopController:
    def set_bot_action_slot_1_presets(
        self,
        *,
        presets: tuple[BotActionPreset, ...],
        finish_template_path: Path | None,
    ) -> None:
        ...


class SlotCaptureService:
    def capture_to_path(self, relative_path: Path, *, existing_path: Path | None = None) -> Path | None:
        ...
```

In `MainWindow`:
- listen for `slotPresetsRequested`
- only open the modal for slot index `0`
- keep slot-1 finish image at a deterministic path such as `bot_actions/slot_1_r_finish.png`
- save modal output through the controller
- update Bot Actions status text after save/cancel/capture failures

Do not add another standalone tab or settings section for presets.

- [ ] **Step 4: Run the targeted tests to verify they pass**

Run:

```bash
python -m pytest -q tests/desktop/test_controller.py tests/desktop/test_main_window.py -k "slot_1_preset or finish_template"
```

Expected:
- PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/desktop/bot_actions/capture.py raidbot/desktop/controller.py raidbot/desktop/main_window.py tests/desktop/test_controller.py tests/desktop/test_main_window.py
git commit -m "feat: wire slot 1 preset editing into desktop ui"
```

---

### Task 4: Add Paste Text/Image Primitives To The Existing Automation Input Layer

**Files:**
- Modify: `raidbot/desktop/automation/input.py`
- Modify: `tests/desktop/automation/test_input.py`

- [ ] **Step 1: Write the failing input tests**

```python
def test_input_driver_pastes_text_then_ctrl_v() -> None:
    clipboard = FakeClipboard()
    sent = []
    driver = InputDriver(send_hotkey=sent.append, clipboard=clipboard)

    driver.paste_text("gm")

    assert clipboard.text == "gm"
    assert sent == [("ctrl", "v")]


def test_input_driver_pastes_image_then_ctrl_v(tmp_path: Path) -> None:
    image_path = tmp_path / "reply.png"
    image_path.write_bytes(b"fake")
    clipboard = FakeClipboard()
    sent = []
    driver = InputDriver(send_hotkey=sent.append, clipboard=clipboard)

    driver.paste_image(image_path)

    assert clipboard.image_path == image_path
    assert sent == [("ctrl", "v")]
```

- [ ] **Step 2: Run the targeted tests to verify they fail**

Run:

```bash
python -m pytest -q tests/desktop/automation/test_input.py
```

Expected:
- FAIL because `paste_text()` / `paste_image()` and `ctrl+v` hotkey support do not exist yet

- [ ] **Step 3: Implement the minimal paste primitives**

```python
class InputDriver:
    def paste_text(self, text: str) -> None:
        self._clipboard.set_text(text)
        self._send_hotkey(("ctrl", "v"))

    def paste_image(self, image_path: Path) -> None:
        self._clipboard.set_image(image_path)
        self._send_hotkey(("ctrl", "v"))
```

Keep this small:
- support `("ctrl", "v")` alongside the existing close-tab/window hotkeys
- use one injected clipboard helper object so tests do not need a real system clipboard
- if the image path is missing, raise a normal `FileNotFoundError` here and let the runner decide whether to ignore it

- [ ] **Step 4: Run the targeted tests to verify they pass**

Run:

```bash
python -m pytest -q tests/desktop/automation/test_input.py
```

Expected:
- PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/desktop/automation/input.py tests/desktop/automation/test_input.py
git commit -m "feat: add paste primitives for bot actions"
```

---

### Task 5: Teach The Bot-Action Builder And Runner About Slot 1 Presets

**Files:**
- Modify: `raidbot/desktop/bot_actions/sequence.py`
- Modify: `raidbot/desktop/automation/models.py`
- Modify: `raidbot/desktop/automation/runner.py`
- Modify: `raidbot/desktop/controller.py`
- Modify: `raidbot/desktop/main_window.py`
- Modify: `raidbot/desktop/worker.py`
- Modify: `tests/desktop/bot_actions/test_sequence.py`
- Modify: `tests/desktop/automation/test_runner.py`
- Modify: `tests/desktop/test_controller.py`
- Modify: `tests/desktop/test_worker.py`

- [ ] **Step 1: Write the failing sequence/runner/worker tests**

```python
def test_build_bot_action_sequence_chooses_random_slot_1_preset() -> None:
    slot = BotActionSlotConfig(
        key="slot_1_r",
        label="R",
        enabled=True,
        template_path=Path("slot-1.png"),
        finish_template_path=Path("finish.png"),
        presets=(
            BotActionPreset(id="a", text="gm"),
            BotActionPreset(id="b", text="wagmi"),
        ),
    )

    result = build_bot_action_sequence((slot,), choose_preset=lambda presets: presets[1])

    step = result.sequence.steps[0]
    assert step.preset_text == "wagmi"
    assert step.finish_template_path == Path("finish.png")


def test_build_bot_action_sequence_skips_slot_1_when_no_presets_exist() -> None:
    result = build_bot_action_sequence((enabled_slot_1_without_presets(), enabled_slot_2()), ...)
    assert [step.name for step in result.sequence.steps] == ["slot_2_l"]
    assert result.warnings == (BotActionBuildWarning(slot_index=0, reason="no_presets_configured"),)


def test_runner_slot_1_pastes_text_optional_image_and_clicks_finish_template() -> None:
    runner = SequenceRunner(..., input_driver=fake_driver)
    result = runner.run_sequence(_sequence(slot_1_step(...)), selected_window=_window())
    assert result.status == "completed"
    assert fake_driver.pasted_text == ["gm"]
    assert fake_driver.pasted_images == [Path("reply.png")]
    assert fake_driver.clicks == [(25, 15), (45, 15)]


def test_worker_emits_skip_message_when_slot_1_has_no_presets_but_continues() -> None:
    worker = build_worker_with_slot_1_enabled_no_presets_and_slot_2_enabled(...)
    worker._execute_automation_sequence(...)
    assert emitted_events[-1]["type"] == "automation_runtime_event"
    assert emitted_events[-1]["event"]["reason"] == "no_presets_configured"
```

- [ ] **Step 2: Run the targeted tests to verify they fail**

Run:

```bash
python -m pytest -q tests/desktop/bot_actions/test_sequence.py tests/desktop/automation/test_runner.py tests/desktop/test_controller.py tests/desktop/test_worker.py -k "slot_1 or preset"
```

Expected:
- FAIL because the builder only knows simple single-template clicks
- FAIL because the runner cannot paste text/image or search a second finish template
- FAIL because worker/controller do not yet surface slot-1 skip/failure rules

- [ ] **Step 3: Implement the minimal slot-1 preset-aware runtime**

```python
@dataclass
class AutomationStep:
    ...
    preset_text: str | None = None
    preset_image_path: Path | None = None
    finish_template_path: Path | None = None


def build_bot_action_sequence(...):
    if slot.key == "slot_1_r" and not slot.presets:
        warnings.append(BotActionBuildWarning(slot_index=0, reason="no_presets_configured"))
        continue
```

Implementation rules:
- choose the random slot-1 preset in `build_bot_action_sequence()` / `build_slot_test_sequence()` so one run uses one fixed preset
- if slot 1 has no presets during a real bot run:
  - emit a clear skip warning
  - skip slot 1
  - keep later enabled slots
- if slot 1 has no presets during `Test`:
  - reject the test early with `Slot 1 (R): no presets configured`
- in `SequenceRunner`, keep the current click/match loop for all slots, but after the first slot-1 click:
  - wait `0.5s`
  - paste `step.preset_text`
  - if `step.preset_image_path` exists on disk, paste it too
  - then search/click `step.finish_template_path`
  - use the normal UI-change confirmation on the finish click
- if the chosen preset image path is missing on disk:
  - treat it as absent
  - do not fail slot 1 for that alone
- if the shared finish image is missing:
  - fail slot 1 normally

Refactor `runner.py` into small helpers if needed so the finish-click logic can reuse the existing search/click/confirm flow instead of copy-pasting `_run_step()`.

- [ ] **Step 4: Run the targeted tests to verify they pass**

Run:

```bash
python -m pytest -q tests/desktop/bot_actions/test_sequence.py tests/desktop/automation/test_runner.py tests/desktop/test_controller.py tests/desktop/test_worker.py -k "slot_1 or preset"
```

Expected:
- PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/desktop/bot_actions/sequence.py raidbot/desktop/automation/models.py raidbot/desktop/automation/runner.py raidbot/desktop/controller.py raidbot/desktop/main_window.py raidbot/desktop/worker.py tests/desktop/bot_actions/test_sequence.py tests/desktop/automation/test_runner.py tests/desktop/test_controller.py tests/desktop/test_worker.py
git commit -m "feat: add slot 1 preset-aware bot action flow"
```

---

### Task 6: Full Regression Verification

**Files:**
- Modify only touched files above if verification exposes a real issue

- [ ] **Step 1: Run the focused regression suite**

Run:

```bash
python -m pytest -q tests/desktop/bot_actions/test_models.py tests/desktop/test_storage.py tests/desktop/bot_actions/test_page.py tests/desktop/bot_actions/test_presets_dialog.py tests/desktop/automation/test_input.py tests/desktop/bot_actions/test_sequence.py tests/desktop/automation/test_runner.py tests/desktop/test_controller.py tests/desktop/test_main_window.py tests/desktop/test_worker.py
```

Expected:
- PASS

- [ ] **Step 2: Run the full suite**

Run:

```bash
python -m pytest -q
```

Expected:
- PASS

- [ ] **Step 3: Manual desktop smoke**

Run:

```bash
python -m raidbot.desktop.app
```

Verify:
- slot 1 shows `Presets`, slots 2/3/4 do not
- slot-1 modal can add/remove presets and save them
- slot-1 modal can capture the shared finish image
- slot-1 `Test` pastes random preset text, optionally pastes a preset image, and finishes with the shared finish image
- real Telegram-triggered bot run uses the same slot-1 flow
- slot 1 enabled with no presets shows a visible skip warning and later slots still run

- [ ] **Step 4: Commit**

```bash
git add raidbot/desktop/models.py raidbot/desktop/storage.py raidbot/desktop/bot_actions/capture.py raidbot/desktop/bot_actions/page.py raidbot/desktop/bot_actions/presets_dialog.py raidbot/desktop/bot_actions/sequence.py raidbot/desktop/automation/models.py raidbot/desktop/automation/input.py raidbot/desktop/automation/runner.py raidbot/desktop/controller.py raidbot/desktop/main_window.py raidbot/desktop/worker.py tests/desktop/bot_actions/test_models.py tests/desktop/test_storage.py tests/desktop/bot_actions/test_page.py tests/desktop/bot_actions/test_presets_dialog.py tests/desktop/automation/test_input.py tests/desktop/bot_actions/test_sequence.py tests/desktop/automation/test_runner.py tests/desktop/test_controller.py tests/desktop/test_main_window.py tests/desktop/test_worker.py
git commit -m "test: verify slot 1 presets flow end to end"
```

---

## Notes For The Implementer

- Keep slot 1 special-cased in a small, explicit way. Do not build a generic preset engine for all slots.
- Do not reintroduce the removed generic automation UI. The only new visible control on the Bot Actions page is `Presets` on slot 1.
- Prefer reusing the existing runner/input path over inventing a second slot-1 executor. One narrow branch in the current runtime is enough.
- Keep `no presets configured` as:
  - a skip warning during normal bot runs
  - a direct test failure during slot-1 `Test`
- Follow `@superpowers:test-driven-development` strictly. Each task starts with a failing test and ends with a small green commit.
