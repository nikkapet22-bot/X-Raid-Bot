# Bot Actions Panel Simplification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the generic Automation tab with a fixed four-slot bot-actions panel that captures one image per slot and automatically runs enabled slots left-to-right after a Telegram-opened link settles.

**Architecture:** Keep the existing image-matching runtime and Telegram queue internals, but move the user-facing product to a new fixed-slot `bot_actions` surface. Persist four slot configs directly in `DesktopAppConfig`, add a small capture module for slot images, and adapt the worker to build an internal ephemeral action chain from enabled slots instead of loading a saved generic sequence.

**Tech Stack:** Python, PySide6, existing desktop automation runtime (`capture.py`, `matching.py`, `runner.py`, `input.py`), pytest/pytest-qt

---

## File Map

### Create

- `raidbot/desktop/bot_actions/__init__.py`
  - Export the fixed-slot UI/model helpers.
- `raidbot/desktop/bot_actions/models.py`
  - Define the four fixed slot configs and helpers to build the default panel state.
- `raidbot/desktop/bot_actions/page.py`
  - Render the simplified four-box panel, settle-delay control, and status area.
- `raidbot/desktop/bot_actions/capture.py`
  - Provide the snipping overlay / capture helper used when the user clicks a slot.
- `raidbot/desktop/bot_actions/sequence.py`
  - Convert enabled slot configs into the existing internal step/sequence shape used by the automation runner.
- `tests/desktop/bot_actions/test_models.py`
  - Cover default slot generation and slot validation helpers.
- `tests/desktop/bot_actions/test_page.py`
  - Cover the simplified panel rendering, enabled/disabled state, and emitted signals.
- `tests/desktop/bot_actions/test_capture.py`
  - Cover capture-save and capture-cancel behavior with fake images.
- `tests/desktop/bot_actions/test_sequence.py`
  - Cover conversion from fixed slots to internal ordered automation steps.

### Modify

- `raidbot/desktop/models.py`
  - Add persisted bot-actions config to `DesktopAppConfig`.
- `raidbot/desktop/storage.py`
  - Save/load bot-actions config and migrate older configs safely.
- `raidbot/desktop/main_window.py`
  - Replace the visible `AutomationPage` tab with the new `BotActionsPage` and wire capture/save/error flow.
- `raidbot/desktop/controller.py`
  - Add bot-actions config update methods and capture-path persistence helpers; stop routing UI through generic sequence-management paths.
- `raidbot/desktop/worker.py`
  - Preflight validate slots, build the ephemeral internal sequence from enabled slots, and run it after Telegram link open/settle.
- `raidbot/desktop/automation/runtime.py`
  - Add a narrow helper entrypoint if needed so the worker can execute an ephemeral generated sequence without a visible sequence ID.
- `raidbot/desktop/automation/runner.py`
  - Add the post-click confirmation polling that treats a stable-in-place match as `ui_did_not_change`.
- `tests/desktop/test_models.py`
  - Update config equality/default tests for bot-actions fields.
- `tests/desktop/test_storage.py`
  - Extend config round-trip and migration tests.
- `tests/desktop/test_main_window.py`
  - Replace current Automation-tab expectations with Bot Actions panel expectations and error propagation checks.
- `tests/desktop/test_controller.py`
  - Cover bot-actions config updates and capture-path persistence.
- `tests/desktop/test_worker.py`
  - Cover preflight validation, fixed slot order, disabled-slot skipping, success-close, and failure-pause behavior.
- `tests/desktop/test_app.py`
  - Adjust any visible tab-title/count assertions if the tab label changes from `Automation` to `Bot Actions`.

### Keep But Do Not Extend Publicly

- `raidbot/desktop/automation/page.py`
- `raidbot/desktop/automation/storage.py`
- existing manual-run sequence tests

These remain temporary internal/legacy code during this simplification. Do not spend plan scope deleting them unless the implementation becomes simpler by doing so after all new behavior is green.

---

### Task 1: Add Fixed Bot-Action Config And Storage Migration

**Files:**
- Create: `tests/desktop/bot_actions/test_models.py`
- Modify: `raidbot/desktop/models.py`
- Modify: `raidbot/desktop/storage.py`
- Modify: `tests/desktop/test_models.py`
- Modify: `tests/desktop/test_storage.py`

- [ ] **Step 1: Write the failing model/storage tests**

```python
def test_default_bot_action_slots_are_four_fixed_labels():
    slots = default_bot_action_slots()
    assert [slot.label for slot in slots] == ["R", "L", "R", "B"]
    assert all(slot.enabled is False for slot in slots)


def test_storage_round_trip_includes_bot_action_slots(tmp_path):
    config = DesktopAppConfig(..., bot_action_slots=default_bot_action_slots())
    storage = DesktopStorage(tmp_path)
    storage.save_config(config)
    assert storage.load_config() == config
```

- [ ] **Step 2: Run the targeted tests to verify they fail**

Run:

```bash
python -m pytest -q tests/desktop/bot_actions/test_models.py tests/desktop/test_models.py tests/desktop/test_storage.py
```

Expected:
- FAIL because `bot_actions` models do not exist yet
- or FAIL because `DesktopAppConfig`/`DesktopStorage` do not know about bot-action slot fields

- [ ] **Step 3: Add the minimal bot-action model and config fields**

```python
@dataclass(eq=True)
class BotActionSlotConfig:
    key: str
    label: str
    enabled: bool = False
    template_path: Path | None = None
    updated_at: str | None = None


def default_bot_action_slots() -> tuple[BotActionSlotConfig, ...]:
    return (
        BotActionSlotConfig(key="slot_1_r", label="R"),
        BotActionSlotConfig(key="slot_2_l", label="L"),
        BotActionSlotConfig(key="slot_3_r", label="R"),
        BotActionSlotConfig(key="slot_4_b", label="B"),
    )
```

Also update `DesktopAppConfig` and `DesktopStorage` so:
- older configs load with all slots disabled and no images
- new configs round-trip bot-action slot state plus settle delay

- [ ] **Step 4: Run the targeted tests to verify they pass**

Run:

```bash
python -m pytest -q tests/desktop/bot_actions/test_models.py tests/desktop/test_models.py tests/desktop/test_storage.py
```

Expected:
- PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/desktop/models.py raidbot/desktop/storage.py tests/desktop/bot_actions/test_models.py tests/desktop/test_models.py tests/desktop/test_storage.py
git commit -m "feat: add persisted bot action slot config"
```

---

### Task 2: Replace The Visible Automation Tab With A Fixed Bot Actions Panel

**Files:**
- Create: `raidbot/desktop/bot_actions/page.py`
- Modify: `raidbot/desktop/main_window.py`
- Modify: `tests/desktop/bot_actions/test_page.py`
- Modify: `tests/desktop/test_main_window.py`

- [ ] **Step 1: Write the failing UI tests for the new panel**

```python
def test_bot_actions_page_renders_four_fixed_slots(qtbot):
    page = BotActionsPage(config=build_config())
    assert [box.label_text() for box in page.slot_boxes] == ["R", "L", "R", "B"]
    assert not hasattr(page, "sequence_list")
    assert not hasattr(page, "dry_run_button")
    assert page.settle_delay_input.minimum() == 0
    assert page.settle_delay_input.maximum() == 10000
    assert page.settle_delay_input.value() == 1500


def test_main_window_uses_bot_actions_page_instead_of_generic_automation_page(qtbot):
    window = MainWindow(...)
    assert window.tabs.tabText(2) == "Bot Actions"
    assert hasattr(window, "bot_actions_page")
```

- [ ] **Step 2: Run the targeted UI tests to verify they fail**

Run:

```bash
python -m pytest -q tests/desktop/bot_actions/test_page.py tests/desktop/test_main_window.py -k "bot_actions or automation_tab"
```

Expected:
- FAIL because `BotActionsPage` does not exist
- FAIL because `MainWindow` still mounts the generic `AutomationPage`

- [ ] **Step 3: Implement the minimal fixed-slot page and wire it into the main window**

```python
class BotActionsPage(QWidget):
    slotCaptureRequested = Signal(int)
    slotEnabledChanged = Signal(int, bool)
    settleDelayChanged = Signal(int)

    def set_slots(self, slots):
        ...

    def show_error(self, message: str) -> None:
        self.status_label.setText(message)
```

And in `MainWindow`:

```python
self.bot_actions_page = BotActionsPage(config=self.controller.config)
self.tabs.addTab(self._wrap_tab_content(self.bot_actions_page), "Bot Actions")
```

Do not expose:
- sequence list
- step editor
- dry run
- manual runner controls
- queue controls
- target-window selection

- [ ] **Step 4: Run the targeted UI tests to verify they pass**

Run:

```bash
python -m pytest -q tests/desktop/bot_actions/test_page.py tests/desktop/test_main_window.py -k "bot_actions or automation_tab"
```

Expected:
- PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/desktop/bot_actions/page.py raidbot/desktop/main_window.py tests/desktop/bot_actions/test_page.py tests/desktop/test_main_window.py
git commit -m "feat: replace automation tab with bot actions panel"
```

---

### Task 3: Add Slot Capture And Deterministic Image Saving

**Files:**
- Create: `raidbot/desktop/bot_actions/capture.py`
- Modify: `raidbot/desktop/controller.py`
- Modify: `raidbot/desktop/main_window.py`
- Modify: `tests/desktop/bot_actions/test_capture.py`
- Modify: `tests/desktop/test_controller.py`
- Modify: `tests/desktop/test_main_window.py`

- [ ] **Step 1: Write the failing capture tests**

```python
def test_capture_saves_slot_image_to_deterministic_path(tmp_path):
    service = SlotCaptureService(base_dir=tmp_path, snip_image=fake_image)
    slot = BotActionSlotConfig(key="slot_1_r", label="R")
    path = service.capture_slot(slot)
    assert path.name == "slot_1_r.png"


def test_capture_cancel_keeps_existing_slot_image(tmp_path):
    service = SlotCaptureService(base_dir=tmp_path, snip_image=lambda: None)
    slot = BotActionSlotConfig(key="slot_1_r", label="R")
    assert service.capture_slot(slot, existing_path=Path("existing.png")) == Path("existing.png")
```

- [ ] **Step 2: Run the targeted capture/controller tests to verify they fail**

Run:

```bash
python -m pytest -q tests/desktop/bot_actions/test_capture.py tests/desktop/test_controller.py tests/desktop/test_main_window.py -k "capture or bot_actions"
```

Expected:
- FAIL because there is no capture service and no slot-capture wiring

- [ ] **Step 3: Implement the minimal capture service and persistence hook**

```python
class SlotCaptureService:
    def capture_slot(
        self,
        slot: BotActionSlotConfig,
        existing_path: Path | None = None,
    ) -> Path | None:
        image = self.capture_overlay.capture()
        if image is None:
            return existing_path
        target_path = self.base_dir / "bot_actions" / f"{slot.key}.png"
        image.save(str(target_path))
        return target_path
```

Then:
- have `BotActionsPage` emit `slotCaptureRequested(slot_index)`
- let `MainWindow` invoke the capture service
- push the resulting path into `DesktopController`
- persist updated slot config immediately

- [ ] **Step 4: Run the targeted capture/controller tests to verify they pass**

Run:

```bash
python -m pytest -q tests/desktop/bot_actions/test_capture.py tests/desktop/test_controller.py tests/desktop/test_main_window.py -k "capture or bot_actions"
```

Expected:
- PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/desktop/bot_actions/capture.py raidbot/desktop/controller.py raidbot/desktop/main_window.py tests/desktop/bot_actions/test_capture.py tests/desktop/test_controller.py tests/desktop/test_main_window.py
git commit -m "feat: add bot action slot capture flow"
```

---

### Task 4: Convert Enabled Slots Into An Internal Ordered Action Chain

**Files:**
- Create: `raidbot/desktop/bot_actions/sequence.py`
- Modify: `raidbot/desktop/worker.py`
- Modify: `raidbot/desktop/automation/runtime.py`
- Modify: `raidbot/desktop/automation/runner.py`
- Create: `tests/desktop/bot_actions/test_sequence.py`
- Modify: `tests/desktop/test_worker.py`
- Modify: `tests/desktop/automation/test_runtime.py`
- Modify: `tests/desktop/automation/test_runner.py`

- [ ] **Step 1: Write the failing sequence-builder and worker tests**

```python
def test_enabled_slots_build_internal_sequence_left_to_right():
    slots = (
        BotActionSlotConfig(key="slot_1_r", label="R", enabled=True, template_path=Path("r1.png")),
        BotActionSlotConfig(key="slot_2_l", label="L", enabled=False, template_path=Path("l.png")),
        BotActionSlotConfig(key="slot_3_r", label="R", enabled=True, template_path=Path("r2.png")),
    )
    sequence = build_bot_action_sequence(slots)
    assert [step.template_path for step in sequence.steps] == [Path("r1.png"), Path("r2.png")]


def test_worker_refuses_to_open_chrome_when_enabled_slot_has_no_image(...):
    result = worker._handle_message(message)
    assert emitted_errors == ["missing_captured_image"]
    assert chrome_open_calls == []


def test_runtime_returns_ui_did_not_change_when_clicked_template_stays_in_place(...):
    result = runtime.run_sequence(...)
    assert result.reason == "ui_did_not_change"


def test_runner_reports_ui_did_not_change_for_stable_post_click_match(...):
    outcome = runner.run_step(...)
    assert outcome.reason == "ui_did_not_change"


def test_worker_pauses_remaining_queue_after_first_bot_action_failure(...):
    worker.enqueue(opened_raid_context("first"))
    worker.enqueue(opened_raid_context("second"))
    worker._drain_auto_queue()
    assert worker.auto_queue_state == "paused"
    assert worker.pending_auto_count == 1
```

- [ ] **Step 2: Run the targeted worker tests to verify they fail**

Run:

```bash
python -m pytest -q tests/desktop/bot_actions/test_sequence.py tests/desktop/automation/test_runtime.py tests/desktop/automation/test_runner.py tests/desktop/test_worker.py -k "bot_action or captured_image or ui_did_not_change or queue"
```

Expected:
- FAIL because the worker still depends on default sequence IDs and the generic automation storage path

- [ ] **Step 3: Implement the minimal slot-to-sequence adapter and worker preflight**

```python
def build_bot_action_sequence(slots: Sequence[BotActionSlotConfig]) -> AutomationSequence:
    return AutomationSequence(
        id="bot-actions",
        name="Bot Actions",
        steps=[
            AutomationStep(
                name=slot.key,
                template_path=slot.template_path,
                match_threshold=0.9,
                max_search_seconds=1.0,
                max_scroll_attempts=0,
                scroll_amount=-120,
                max_click_attempts=1,
                post_click_settle_ms=250,
            )
            for slot in slots
            if slot.enabled and slot.template_path is not None
        ],
    )
```

Update `DesktopBotWorker` so it:
- validates `>= 1` enabled slot before opening Chrome
- validates every enabled slot has an image before opening Chrome
- builds the ephemeral internal sequence from enabled slots
- uses the existing `AutomationRuntime` / `SequenceRunner`
- updates the runtime/runner path so post-click confirmation polls the active capture for up to `2000 ms` after each click
- keeps sampling the clicked template match score and location during that confirmation window instead of relying only on `post_click_settle_ms`
- returns success only when the clicked template disappears or moves materially beyond the approved tolerance
- returns `ui_did_not_change` when the clicked template stays matched in essentially the same location for the full confirmation window
- closes the tab only on success
- leaves it open and pauses on failure

If needed:
- add a small helper to `AutomationRuntime` so the worker can run a generated sequence against the active handle without a user-visible sequence ID lookup
- move the confirmation polling loop into `raidbot/desktop/automation/runner.py` so the click-confirmation rule lives beside the existing step-execution logic

- [ ] **Step 4: Run the targeted worker tests to verify they pass**

Run:

```bash
python -m pytest -q tests/desktop/bot_actions/test_sequence.py tests/desktop/automation/test_runtime.py tests/desktop/automation/test_runner.py tests/desktop/test_worker.py -k "bot_action or captured_image or ui_did_not_change or queue"
```

Expected:
- PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/desktop/bot_actions/sequence.py raidbot/desktop/worker.py raidbot/desktop/automation/runtime.py raidbot/desktop/automation/runner.py tests/desktop/bot_actions/test_sequence.py tests/desktop/automation/test_runtime.py tests/desktop/automation/test_runner.py tests/desktop/test_worker.py
git commit -m "feat: run fixed bot action slots after telegram opens"
```

---

### Task 5: Propagate Simplified Status And Remove Old User-Facing Automation Controls

**Files:**
- Modify: `raidbot/desktop/controller.py`
- Modify: `raidbot/desktop/main_window.py`
- Modify: `tests/desktop/test_controller.py`
- Modify: `tests/desktop/test_main_window.py`
- Modify: `tests/desktop/test_app.py`

- [ ] **Step 1: Write the failing status/visibility tests**

```python
def test_bot_actions_page_shows_runtime_failure_in_status_area(qtbot):
    controller.errorRaised.emit("ui_did_not_change")
    assert "ui_did_not_change" in window.bot_actions_page.status_label.text()


def test_removed_generic_automation_controls_are_not_visible(qtbot):
    window = MainWindow(...)
    assert not hasattr(window.bot_actions_page, "sequence_list")
    assert not hasattr(window.bot_actions_page, "dry_run_button")
    assert not hasattr(window.bot_actions_page, "window_combo")


def test_bot_actions_settle_delay_wires_through_controller(qtbot):
    page.settle_delay_input.setValue(2200)
    assert controller.apply_calls[-1].bot_actions_settle_ms == 2200
```

- [ ] **Step 2: Run the targeted status/visibility tests to verify they fail**

Run:

```bash
python -m pytest -q tests/desktop/test_controller.py tests/desktop/test_main_window.py tests/desktop/test_app.py -k "bot_actions or removed_generic"
```

Expected:
- FAIL because old automation UI assumptions still exist in controller/main window tests

- [ ] **Step 3: Implement the minimal status propagation and visible cleanup**

```python
self.controller.errorRaised.connect(self.bot_actions_page.show_error)
self.bot_actions_page.set_runtime_state(...)
```

Keep:
- simple status text
- current slot text if available
- last error text

Remove from visible UI:
- generic sequence management widgets
- queue buttons
- manual-run buttons
- window-picker widgets

Do not spend scope deleting every old controller method if they are safely unused. Only remove or redirect code that still drives visible obsolete behavior.

- [ ] **Step 4: Run the targeted status/visibility tests to verify they pass**

Run:

```bash
python -m pytest -q tests/desktop/test_controller.py tests/desktop/test_main_window.py tests/desktop/test_app.py -k "bot_actions or removed_generic"
```

Expected:
- PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/desktop/controller.py raidbot/desktop/main_window.py tests/desktop/test_controller.py tests/desktop/test_main_window.py tests/desktop/test_app.py
git commit -m "refactor: simplify visible bot actions status and controls"
```

---

### Task 6: Full Regression Verification And Light Cleanup

**Files:**
- Modify: any touched files from Tasks 1-5 only as needed for green tests

- [ ] **Step 1: Run the focused desktop regression suite**

Run:

```bash
python -m pytest -q tests/desktop/test_models.py tests/desktop/test_storage.py tests/desktop/test_controller.py tests/desktop/test_main_window.py tests/desktop/test_worker.py tests/desktop/test_app.py tests/desktop/automation/test_runtime.py tests/desktop/automation/test_runner.py tests/desktop/bot_actions
```

Expected:
- PASS

- [ ] **Step 1.5: Run the queue-stop regression after failure**

Run:

```bash
python -m pytest -q tests/desktop/test_worker.py -k "pauses_remaining_queue_after_first_bot_action_failure"
```

Expected:
- PASS with a regression proving later queued links do not continue automatically after the first bot-actions failure

- [ ] **Step 2: Run the full suite**

Run:

```bash
python -m pytest -q
```

Expected:
- PASS with the full project suite green

- [ ] **Step 3: Manually smoke the desktop app**

Run:

```bash
python -m raidbot.desktop.app
```

Verify:
- tab shows `Bot Actions`
- four fixed boxes render
- capture click flow opens
- no generic sequence editor/runner UI is visible
- settings still load and save

- [ ] **Step 4: Clean only stray bot-actions test fixtures/artifacts**

Examples:

```bash
git clean -fd -- tests/desktop/bot_actions/__pycache__
```

Do not delete user data or unrelated working-tree files.

- [ ] **Step 5: Commit**

```bash
git add raidbot/desktop/bot_actions raidbot/desktop/*.py tests/desktop
git commit -m "test: verify bot actions panel simplification"
```

---

## Notes For The Implementer

- Reuse the existing image-matching/click runtime wherever possible. The simplification is primarily a product/UI refocus, not a mandate to rewrite the matching engine.
- Keep `DesktopAppConfig` backwards-compatible by defaulting older configs to four disabled slots with no templates.
- Do not reintroduce user-facing sequence or runner concepts during implementation.
- Follow `@superpowers:test-driven-development` strictly: every new behavior starts with a failing test.
- Keep commits frequent and scoped to the task boundaries above.
