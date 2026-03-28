# Chrome Window Template Automation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Windows-only desktop-app automation module that captures a selected Chrome window, matches user-provided template images in a fixed ordered sequence, and drives mouse move/click/scroll actions until the sequence completes or fails.

**Architecture:** Add a new `raidbot.desktop.automation` package with focused units for persisted sequence models, window targeting, frame capture, template matching, input driving, and sequence running. Extend the existing desktop controller and main window with a new automation tab so the subsystem runs beside the current bot UI without being mixed into Telegram-specific worker code.

**Tech Stack:** PySide6, pytest/pytest-qt, OpenCV (`opencv-python-headless`), NumPy, `mss`, `pywin32`

---

## File Structure

- Create: `raidbot/desktop/automation/__init__.py`
  - Package marker for the new desktop automation subsystem.
- Create: `raidbot/desktop/automation/models.py`
  - Dataclasses/enums for sequence definitions, steps, run state, match results, and run events.
- Create: `raidbot/desktop/automation/platform.py`
  - Windows-only dependency checks and lazy import helpers so desktop startup does not hard-require automation packages until the subsystem is used.
- Create: `raidbot/desktop/automation/storage.py`
  - JSON persistence for automation sequences in a dedicated `automation_sequences.json` file under the existing app data base directory.
- Create: `raidbot/desktop/automation/windowing.py`
  - Chrome window discovery, title-rule reacquisition, focus/restore helpers, and window metadata objects.
- Create: `raidbot/desktop/automation/capture.py`
  - Window-bounds frame capture using `mss`, returning DPI-aware pixel arrays.
- Create: `raidbot/desktop/automation/templates.py`
  - Template image loading from disk, grayscale conversion, and explicit missing/unreadable file errors.
- Create: `raidbot/desktop/automation/matching.py`
  - OpenCV `TM_CCOEFF_NORMED` template matching and best-match selection.
- Create: `raidbot/desktop/automation/input.py`
  - Mouse move, delayed click, and wheel scroll utilities against physical screen coordinates.
- Create: `raidbot/desktop/automation/runner.py`
  - Ordered step execution state machine with scan, scroll, click, verify, fail, and stop behavior.
- Create: `raidbot/desktop/automation/page.py`
  - PySide6 UI for sequence CRUD, step editing, dry-run, window selection, and activity display.
- Modify: `raidbot/desktop/models.py`
  - Add automation sequence summary/state models only if the UI/controller needs shared desktop-level dataclasses.
- Modify: `raidbot/desktop/storage.py`
  - Add convenience path helpers for the automation storage file, but keep sequence serialization in the dedicated automation storage module.
- Modify: `raidbot/desktop/controller.py`
  - Add automation-runner lifecycle, signals, config-independent storage wiring, and stop/start submissions for the new subsystem.
- Modify: `raidbot/desktop/main_window.py`
  - Add the automation tab and connect automation controller signals to the new page.
- Modify: `pyproject.toml`
  - Add runtime dependencies for capture, image matching, and Windows window/input integration.
- Test: `tests/desktop/automation/test_platform.py`
- Test: `tests/desktop/automation/test_models.py`
- Test: `tests/desktop/automation/test_storage.py`
- Test: `tests/desktop/automation/test_templates.py`
- Test: `tests/desktop/automation/test_matching.py`
- Test: `tests/desktop/automation/test_runner.py`
- Test: `tests/desktop/automation/test_windowing.py`
- Test: `tests/desktop/test_controller.py`
- Test: `tests/desktop/test_main_window.py`

### Task 1: Add Automation Dependencies And Platform Guards

**Files:**
- Modify: `pyproject.toml`
- Create: `raidbot/desktop/automation/platform.py`
- Test: `tests/desktop/automation/test_platform.py`

- [ ] **Step 1: Write failing tests for optional dependency probing and lazy platform guards**

```python
from raidbot.desktop.automation.platform import automation_runtime_available


def test_automation_runtime_available_reports_missing_optional_dependency(monkeypatch) -> None:
    monkeypatch.setattr("importlib.import_module", lambda _name: (_ for _ in ()).throw(ModuleNotFoundError("cv2")))

    available, reason = automation_runtime_available()

    assert available is False
    assert "cv2" in reason
```

- [ ] **Step 2: Run the new platform test to verify it fails**

Run: `python -m pytest -q tests/desktop/automation/test_platform.py`

Expected: import failure for `raidbot.desktop.automation.platform`.

- [ ] **Step 3: Add runtime dependencies and install them before matcher/windowing work begins**

```toml
dependencies = [
    "telethon",
    "python-dotenv",
    "PySide6",
    "numpy",
    "opencv-python-headless",
    "mss",
    "pywin32",
]
```

- [ ] **Step 4: Implement a lazy Windows-only platform probe**

```python
def automation_runtime_available() -> tuple[bool, str | None]:
    try:
        importlib.import_module("cv2")
        importlib.import_module("mss")
        importlib.import_module("win32gui")
    except ModuleNotFoundError as exc:
        return False, str(exc)
    if sys.platform != "win32":
        return False, "Windows only"
    return True, None
```

- [ ] **Step 5: Reinstall the editable package so the new dependencies exist for later TDD tasks**

Run: `python -m pip install -e .[dev]`

Expected: install succeeds with the new automation dependencies available.

- [ ] **Step 6: Run the platform test again and make it pass**

Run: `python -m pytest -q tests/desktop/automation/test_platform.py`

Expected: platform guard tests pass.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml raidbot/desktop/automation/platform.py tests/desktop/automation/test_platform.py
git commit -m "feat: add automation dependency and platform guards"
```

### Task 2: Add Automation Models And Persistence

**Files:**
- Create: `raidbot/desktop/automation/__init__.py`
- Create: `raidbot/desktop/automation/models.py`
- Create: `raidbot/desktop/automation/storage.py`
- Modify: `raidbot/desktop/storage.py`
- Test: `tests/desktop/automation/test_models.py`
- Test: `tests/desktop/automation/test_storage.py`

- [ ] **Step 1: Write the failing model and persistence tests**

```python
from pathlib import Path

from raidbot.desktop.automation.models import AutomationSequence, AutomationStep
from raidbot.desktop.automation.storage import AutomationStorage


def test_sequence_model_preserves_order_and_optional_window_rule() -> None:
    sequence = AutomationSequence(
        id="seq-1",
        name="Chrome Flow",
        target_window_rule="Twitter / X",
        steps=[
            AutomationStep(
                name="Open menu",
                template_path=Path("templates/menu.png"),
                match_threshold=0.92,
                max_search_seconds=2.0,
                max_scroll_attempts=3,
                scroll_amount=-4,
                max_click_attempts=1,
                post_click_settle_ms=500,
            )
        ],
    )

    assert sequence.steps[0].name == "Open menu"
    assert sequence.target_window_rule == "Twitter / X"


def test_automation_storage_round_trips_sequences(tmp_path) -> None:
    storage = AutomationStorage(tmp_path / "automation_sequences.json")
    sequence = AutomationSequence(...)

    storage.save_sequences([sequence])

    assert storage.load_sequences() == [sequence]


def test_automation_storage_handles_older_schema_and_missing_template_paths(tmp_path) -> None:
    ...
    loaded = storage.load_sequences()

    assert loaded[0].steps[0].template_missing is True
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `python -m pytest -q tests/desktop/automation/test_models.py tests/desktop/automation/test_storage.py`

Expected: `ModuleNotFoundError` and/or import failures for the new automation modules.

- [ ] **Step 3: Add the minimal sequence and storage implementation**

```python
@dataclass(eq=True)
class AutomationStep:
    name: str
    template_path: Path
    match_threshold: float
    max_search_seconds: float
    max_scroll_attempts: int
    scroll_amount: int
    max_click_attempts: int
    post_click_settle_ms: int
    click_offset_x: int = 0
    click_offset_y: int = 0


@dataclass(eq=True)
class AutomationSequence:
    id: str
    name: str
    target_window_rule: str | None
    steps: list[AutomationStep]
```

- [ ] **Step 4: Add dedicated automation JSON persistence and base-dir wiring**

```python
class AutomationStorage:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load_sequences(self) -> list[AutomationSequence]:
        if not self.path.exists():
            return []
        ...

    def save_sequences(self, sequences: list[AutomationSequence]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        ...
```

- [ ] **Step 5: Add schema versioning and missing-template marking**

```python
payload = {
    "schema_version": 1,
    "sequences": [...],
}
```

- [ ] **Step 6: Run the tests again and make them pass**

Run: `python -m pytest -q tests/desktop/automation/test_models.py tests/desktop/automation/test_storage.py`

Expected: `2 passed` or more, with the new automation tests green.

- [ ] **Step 7: Commit**

```bash
git add raidbot/desktop/automation/__init__.py raidbot/desktop/automation/models.py raidbot/desktop/automation/storage.py raidbot/desktop/storage.py tests/desktop/automation/test_models.py tests/desktop/automation/test_storage.py
git commit -m "feat: add automation sequence models and storage"
```

### Task 3: Add Template Matching Core

**Files:**
- Create: `raidbot/desktop/automation/templates.py`
- Create: `raidbot/desktop/automation/matching.py`
- Test: `tests/desktop/automation/test_templates.py`
- Test: `tests/desktop/automation/test_matching.py`

- [ ] **Step 1: Write failing template-matching tests against synthetic frames**

```python
import numpy as np

from raidbot.desktop.automation.matching import TemplateMatcher


def test_matcher_returns_best_match_above_threshold() -> None:
    frame = np.zeros((40, 40), dtype=np.uint8)
    template = np.array(
        [
            [0, 255, 0],
            [255, 64, 255],
            [0, 255, 0],
        ],
        dtype=np.uint8,
    )
    frame[10:13, 20:23] = template

    match = TemplateMatcher().find_best_match(frame, template, threshold=0.8)

    assert match is not None
    assert match.center_x == 21
    assert match.center_y == 11


def test_matcher_returns_none_when_score_below_threshold() -> None:
    frame = np.zeros((20, 20), dtype=np.uint8)
    template = np.array(
        [
            [0, 255, 0],
            [255, 64, 255],
            [0, 255, 0],
        ],
        dtype=np.uint8,
    )

    assert TemplateMatcher().find_best_match(frame, template, threshold=0.95) is None


def test_template_loader_raises_for_missing_file(tmp_path) -> None:
    from raidbot.desktop.automation.templates import load_template_image

    with pytest.raises(FileNotFoundError, match="missing"):
        load_template_image(tmp_path / "missing.png")


def test_template_loader_raises_for_unreadable_file(tmp_path) -> None:
    path = tmp_path / "broken.png"
    path.write_bytes(b"not-an-image")

    with pytest.raises(ValueError, match="unreadable"):
        load_template_image(path)
```

- [ ] **Step 2: Run the template and matcher tests to verify they fail**

Run: `python -m pytest -q tests/desktop/automation/test_templates.py tests/desktop/automation/test_matching.py`

Expected: import failure for `load_template_image` and `TemplateMatcher`.

- [ ] **Step 3: Implement template loading from disk with missing/unreadable-file failures**

```python
def load_template_image(path: Path) -> np.ndarray:
    if not path.exists():
        raise FileNotFoundError(f"Template file is missing: {path}")
    image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise ValueError(f"Template file is unreadable: {path}")
    return image
```

- [ ] **Step 4: Implement `TM_CCOEFF_NORMED` matching and result objects**

```python
class TemplateMatcher:
    def find_best_match(self, frame: np.ndarray, template: np.ndarray, threshold: float) -> MatchResult | None:
        result = cv2.matchTemplate(frame, template, cv2.TM_CCOEFF_NORMED)
        _, max_score, _, max_loc = cv2.minMaxLoc(result)
        if max_score < threshold:
            return None
        ...
```

- [ ] **Step 5: Add template-shape validation and out-of-range guardrails**

```python
if template.shape[0] > frame.shape[0] or template.shape[1] > frame.shape[1]:
    raise ValueError("Template dimensions exceed frame dimensions")
```

- [ ] **Step 6: Run the template and matcher tests and make them pass**

Run: `python -m pytest -q tests/desktop/automation/test_templates.py tests/desktop/automation/test_matching.py`

Expected: template-loader and matcher tests pass.

- [ ] **Step 7: Commit**

```bash
git add raidbot/desktop/automation/templates.py raidbot/desktop/automation/matching.py tests/desktop/automation/test_templates.py tests/desktop/automation/test_matching.py
git commit -m "feat: add template loading and matching core"
```

### Task 4: Add Window Discovery, Capture, And Input Seams

**Files:**
- Create: `raidbot/desktop/automation/windowing.py`
- Create: `raidbot/desktop/automation/capture.py`
- Create: `raidbot/desktop/automation/input.py`
- Test: `tests/desktop/automation/test_windowing.py`

- [ ] **Step 1: Write failing tests for window-rule resolution and click-target validation**

```python
from raidbot.desktop.automation.windowing import choose_window_for_rule, WindowInfo
from raidbot.desktop.automation.input import validate_click_target


def test_choose_window_for_rule_prefers_most_recent_focus() -> None:
    windows = [
        WindowInfo(handle=1, title="X - Chrome", bounds=(0, 0, 100, 100), last_focused_at=1.0),
        WindowInfo(handle=2, title="X - Chrome", bounds=(0, 0, 100, 100), last_focused_at=5.0),
    ]

    chosen = choose_window_for_rule(windows, "X - Chrome")

    assert chosen.handle == 2


def test_validate_click_target_rejects_points_outside_window() -> None:
    assert validate_click_target((10, 10, 110, 110), (200, 200)) is False


def test_window_manager_reports_focus_failure_for_minimized_window() -> None:
    ...
    assert outcome.reason == "window_not_focusable"
```

- [ ] **Step 2: Run the windowing/input tests to verify they fail**

Run: `python -m pytest -q tests/desktop/automation/test_windowing.py`

Expected: import failure for the new windowing/input helpers.

- [ ] **Step 3: Implement pure-Python window selection helpers and metadata objects**

```python
@dataclass(eq=True)
class WindowInfo:
    handle: int
    title: str
    bounds: tuple[int, int, int, int]
    last_focused_at: float


def choose_window_for_rule(windows: list[WindowInfo], rule: str) -> WindowInfo | None:
    matches = [window for window in windows if rule.lower() in window.title.lower()]
    return max(matches, key=lambda item: item.last_focused_at, default=None)
```

- [ ] **Step 4: Add Win32-backed adapters for enumeration/focus/restore and an `mss` capture seam**

```python
class WindowManager:
    def list_chrome_windows(self) -> list[WindowInfo]:
        ...

    def focus_window(self, handle: int) -> None:
        ...


class WindowCapture:
    def capture(self, bounds: tuple[int, int, int, int]) -> np.ndarray:
        ...
```

- [ ] **Step 5: Add restore/focus/handle-change/DPI-safety behavior before input-driving code**

```python
def ensure_interactable_window(window: WindowInfo) -> WindowInfo:
    if window.is_minimized:
        ...
    if window.handle != current_handle:
        raise WindowLostError("target window handle changed")
```

- [ ] **Step 6: Add input-driver helpers for move/click/scroll and window-bounds rejection**

```python
class InputDriver:
    def move_click(self, point: tuple[int, int], *, delay_seconds: float = 0.5) -> None:
        ...

    def scroll(self, amount: int) -> None:
        ...
```

- [ ] **Step 7: Run the tests again and make them pass**

Run: `python -m pytest -q tests/desktop/automation/test_windowing.py`

Expected: all windowing/input seam tests pass.

- [ ] **Step 8: Commit**

```bash
git add raidbot/desktop/automation/windowing.py raidbot/desktop/automation/capture.py raidbot/desktop/automation/input.py tests/desktop/automation/test_windowing.py
git commit -m "feat: add automation windowing and input seams"
```

### Task 5: Add The Sequence Runner State Machine

**Files:**
- Create: `raidbot/desktop/automation/runner.py`
- Test: `tests/desktop/automation/test_runner.py`

- [ ] **Step 1: Write failing runner tests using fake matcher, capture, and input drivers**

```python
from raidbot.desktop.automation.models import AutomationSequence, AutomationStep
from raidbot.desktop.automation.runner import SequenceRunner


def test_runner_clicks_match_and_advances_to_next_step() -> None:
    runner = SequenceRunner(
        window_manager=FakeWindowManager(),
        capture=FakeCapture([...]),
        matcher=FakeMatcher([...]),
        input_driver=FakeInputDriver(),
        now=lambda: 100.0,
    )

    result = runner.run_sequence(sequence, selected_window=window)

    assert result.status == "completed"
    assert runner.input_driver.clicks == [(50, 60)]


def test_runner_fails_when_template_never_appears_after_scroll_budget() -> None:
    ...
    assert result.failure_reason == "match_not_found"


def test_runner_retries_after_non_changing_click_then_fails() -> None:
    ...
    assert result.failure_reason == "no_ui_change_after_click"


def test_runner_rejects_click_offset_outside_window_bounds() -> None:
    ...
    assert result.failure_reason == "invalid_click_target"


def test_runner_dry_run_reports_match_without_clicking() -> None:
    ...
    assert result.status == "dry_run_match_found"
    assert runner.input_driver.clicks == []


def test_runner_prefers_selected_window_over_saved_rule() -> None:
    ...
    assert result.window_handle == selected_window.handle


def test_runner_reacquires_window_from_saved_rule_when_no_selection_is_provided() -> None:
    ...
    assert result.window_handle == reacquired_window.handle
```

- [ ] **Step 2: Run the runner tests to verify they fail**

Run: `python -m pytest -q tests/desktop/automation/test_runner.py`

Expected: import failure for `SequenceRunner`.

- [ ] **Step 3: Implement the ordered step loop with scan, scroll, click, and verify phases**

```python
class SequenceRunner:
    def run_sequence(self, sequence: AutomationSequence, *, selected_window: WindowInfo | None) -> RunResult:
        window = self._resolve_window(sequence, selected_window)
        for step in sequence.steps:
            self._run_step(window, step)
        return RunResult(status="completed")
```

- [ ] **Step 4: Implement `max_search_seconds`, `max_scroll_attempts`, and `max_click_attempts` exactly as specified**

```python
for scroll_attempt in range(step.max_scroll_attempts + 1):
    deadline = self.now() + step.max_search_seconds
    while self.now() < deadline:
        ...
    if scroll_attempt < step.max_scroll_attempts:
        self.input_driver.scroll(step.scroll_amount)
```

- [ ] **Step 5: Implement post-click settle-delay verification and offset validation exactly as specified**

```python
time.sleep(step.post_click_settle_ms / 1000)
next_match = self._scan_current_step(...)
if next_match is not None:
    ...
```

- [ ] **Step 6: Emit the full structured event contract and stop safely on command**

```python
self.emit({"type": "run_started", "sequence_id": sequence.id})
self.emit({"type": "target_window_acquired", "handle": window.handle})
self.emit({"type": "step_search_started", "step_id": step_id})
self.emit({"type": "step_found", "step_id": step_id, "score": match.score})
self.emit({"type": "step_scrolled", "step_id": step_id, "amount": step.scroll_amount})
self.emit({"type": "step_clicked", "step_id": step_id, "point": point})
self.emit({"type": "step_succeeded", "step_id": step_id})
```

- [ ] **Step 7: Add dry-run execution mode that finds and reports the current-step match without clicking**

```python
def dry_run_step(self, sequence: AutomationSequence, step_index: int, *, selected_window: WindowInfo | None) -> RunResult:
    ...
    return RunResult(status="dry_run_match_found", match=match)
```

- [ ] **Step 8: Run the runner tests and make them pass**

Run: `python -m pytest -q tests/desktop/automation/test_runner.py`

Expected: runner tests pass with fake seams only.

- [ ] **Step 9: Commit**

```bash
git add raidbot/desktop/automation/runner.py tests/desktop/automation/test_runner.py
git commit -m "feat: add sequence runner state machine"
```

### Task 6: Integrate Automation Into The Desktop Controller

**Files:**
- Modify: `raidbot/desktop/controller.py`
- Modify: `raidbot/desktop/models.py`
- Modify: `raidbot/desktop/storage.py`
- Create: `tests/desktop/automation/test_controller_integration.py`
- Modify: `tests/desktop/test_controller.py`

- [ ] **Step 1: Write failing controller tests for sequence loading, run lifecycle, and emitted events**

```python
def test_controller_loads_saved_sequences_on_startup(tmp_path) -> None:
    ...
    assert controller.list_automation_sequences()[0].name == "Chrome Flow"


def test_controller_lists_target_windows_for_ui_picker() -> None:
    ...
    assert controller.list_target_windows()[0].title.endswith("Chrome")


def test_controller_emits_automation_events_from_runner(qtbot) -> None:
    ...
    assert [event["type"] for event in received] == [
        "run_started",
        "target_window_acquired",
        "step_search_started",
        "step_found",
        "step_clicked",
        "step_succeeded",
        "run_completed",
    ]


def test_controller_emits_failure_and_stopped_events_for_unhappy_paths(qtbot) -> None:
    ...
    assert "step_failed" in event_types
    assert "target_window_lost" in event_types
    assert "run_stopped" in event_types


def test_controller_surfaces_dry_run_match_result_to_ui(qtbot) -> None:
    ...
    assert received[-1]["type"] == "dry_run_match_found"
```

- [ ] **Step 2: Run the controller-focused tests to verify they fail**

Run: `python -m pytest -q tests/desktop/test_controller.py tests/desktop/automation/test_controller_integration.py`

Expected: missing methods/signals on `DesktopController`.

- [ ] **Step 3: Add automation-specific signals and storage wiring to `DesktopController`**

```python
class DesktopController(QObject):
    automationSequencesChanged = Signal(object)
    automationRunEvent = Signal(object)
    automationRunStateChanged = Signal(str)
```

- [ ] **Step 4: Keep Windows-only imports lazy so desktop startup does not hard-require automation runtime**

```python
def _load_automation_runtime(self):
    from raidbot.desktop.automation.runner import SequenceRunner
    ...
```

- [ ] **Step 5: Add controller methods for sequence CRUD, window listing, dry-run, start, and stop**

```python
def save_automation_sequence(self, sequence: AutomationSequence) -> None:
    ...

def list_target_windows(self) -> list[WindowInfo]:
    ...

def dry_run_automation_step(self, sequence_id: str, step_index: int, selected_window_handle: int | None) -> None:
    ...

def start_automation_run(self, sequence_id: str, selected_window_handle: int | None) -> None:
    ...
```

- [ ] **Step 6: Reuse the existing async runner thread model for the automation subsystem**

```python
if self._automation_runner is None:
    self._automation_runner = self.runner_factory()
self._automation_runner.start(lambda: self._automation_worker.run(...))
```

- [ ] **Step 7: Run the controller tests and make them pass**

Run: `python -m pytest -q tests/desktop/test_controller.py tests/desktop/automation/test_controller_integration.py`

Expected: all controller automation tests pass.

- [ ] **Step 8: Commit**

```bash
git add raidbot/desktop/controller.py raidbot/desktop/models.py raidbot/desktop/storage.py tests/desktop/test_controller.py tests/desktop/automation/test_controller_integration.py
git commit -m "feat: integrate automation runner into desktop controller"
```

### Task 7: Add The Automation Desktop Page And Main Window Integration

**Files:**
- Create: `raidbot/desktop/automation/page.py`
- Modify: `raidbot/desktop/main_window.py`
- Modify: `raidbot/desktop/theme.py`
- Modify: `tests/desktop/test_main_window.py`

- [ ] **Step 1: Write failing Qt tests for the new automation tab and sequence editor actions**

```python
def test_main_window_adds_automation_tab(qtbot, controller, storage) -> None:
    window = MainWindow(controller=controller, storage=storage)

    assert window.tabs.tabText(2) == "Automation"


def test_automation_page_emits_start_and_save_requests(qtbot) -> None:
    page = AutomationPage(...)
    ...
    assert captured_sequence.name == "Chrome Flow"


def test_automation_page_emits_dry_run_request(qtbot) -> None:
    page = AutomationPage(...)
    ...
    assert captured["step_index"] == 0


def test_automation_page_displays_dry_run_match_without_clicking(qtbot) -> None:
    page = AutomationPage(...)
    ...
    assert "0.97" in page.status_label.text()
```

- [ ] **Step 2: Run the Qt tests to verify they fail**

Run: `python -m pytest -q tests/desktop/test_main_window.py`

Expected: failures because the automation tab/page does not exist.

- [ ] **Step 3: Implement the automation page UI with sequence list, editor, runner panel, and activity log**

```python
class AutomationPage(QWidget):
    sequenceSaveRequested = Signal(object)
    sequenceDeleteRequested = Signal(str)
    runRequested = Signal(str, object)
    dryRunRequested = Signal(str, int, object)
    stopRequested = Signal()
```

- [ ] **Step 4: Wire the automation page into `MainWindow` and connect controller signals**

```python
self.automation_page = AutomationPage(...)
self.tabs.addTab(self.automation_page, "Automation")
self.automation_page.runRequested.connect(self.controller.start_automation_run)
```

- [ ] **Step 5: Add dry-run and current-window selection plumbing without affecting the existing Dashboard/Settings tabs**

```python
self.automation_page.refresh_windows(self.controller.list_target_windows())
self.automation_page.dryRunRequested.connect(self.controller.dry_run_automation_step)
```

- [ ] **Step 6: Run the Qt tests and make them pass**

Run: `python -m pytest -q tests/desktop/test_main_window.py`

Expected: automation tab tests pass, existing main-window behavior still green.

- [ ] **Step 7: Commit**

```bash
git add raidbot/desktop/automation/page.py raidbot/desktop/main_window.py raidbot/desktop/theme.py tests/desktop/test_main_window.py
git commit -m "feat: add automation desktop UI"
```

### Task 8: Add Full Verification And Docs

**Files:**
- Modify: `README.md`
- Modify: `.env.example` only if any new optional app settings are introduced during implementation

- [ ] **Step 1: Write or update a minimal dependency/import smoke test if needed**

```python
def test_automation_modules_import() -> None:
    import raidbot.desktop.automation.runner  # noqa: F401
```

- [ ] **Step 2: Document the new automation tab, Windows-only support, dependency prerequisites, and template file workflow**

```markdown
## Automation

The desktop app includes a Chrome-window template automation tab for Windows.
Provide template images, choose a Chrome window, then run a fixed ordered sequence.
```

- [ ] **Step 3: Run the targeted automation test suite**

Run: `python -m pytest -q tests/desktop/automation tests/desktop/test_controller.py tests/desktop/test_main_window.py`

Expected: all new automation-focused tests pass.

- [ ] **Step 4: Run the full test suite**

Run: `python -m pytest -q`

Expected: full suite passes with the new automation subsystem integrated.

- [ ] **Step 5: Smoke-check desktop startup**

Run: `python -m raidbot.desktop.app`

Expected: app opens with the new `Automation` tab visible and no import/runtime errors before manual close.

- [ ] **Step 6: Commit**

```bash
git add README.md .env.example tests/desktop/automation tests/desktop/test_controller.py tests/desktop/test_main_window.py raidbot/desktop/automation raidbot/desktop/controller.py raidbot/desktop/main_window.py raidbot/desktop/storage.py raidbot/desktop/models.py
git commit -m "feat: add chrome window template automation"
```
