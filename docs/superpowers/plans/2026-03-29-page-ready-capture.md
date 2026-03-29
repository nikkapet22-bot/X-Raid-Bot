# Page Ready Capture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one shared `Page Ready` capture to Bot Actions so the bot waits for a real page-ready image before it starts searching the action slots.

**Architecture:** Extend the existing desktop config with one shared page-ready template path, surface that capture in the Bot Actions page, and reuse the current automation matcher inside the worker to gate the per-profile bot-action run. The slot sequence logic stays unchanged; the worker adds one readiness wait before it calls the normal slot sequence.

**Tech Stack:** Python, PySide6, dataclasses, existing desktop storage/config model, existing automation runtime/matcher, pytest

---

### Task 1: Persist Shared Page Ready Template Path

**Files:**
- Modify: `raidbot/desktop/models.py`
- Modify: `raidbot/desktop/storage.py`
- Test: `tests/desktop/test_models.py`
- Test: `tests/desktop/test_storage.py`

- [ ] **Step 1: Write the failing model/storage tests**

Add tests that prove:
- `DesktopAppConfig` accepts and preserves `page_ready_template_path`
- config JSON round-trip keeps the shared page-ready path

```python
def test_desktop_app_config_preserves_page_ready_template_path() -> None:
    config = DesktopAppConfig(..., page_ready_template_path=Path("bot_actions/page_ready.png"))
    assert config.page_ready_template_path == Path("bot_actions/page_ready.png")
```

```python
def test_storage_round_trips_page_ready_template_path(tmp_path) -> None:
    storage = DesktopStorage(tmp_path)
    config = DesktopAppConfig(..., page_ready_template_path=Path("bot_actions/page_ready.png"))
    storage.save_config(config)
    assert storage.load_config().page_ready_template_path == Path("bot_actions/page_ready.png")
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest -q tests\desktop\test_models.py tests\desktop\test_storage.py -k page_ready
```

Expected:
- fail because `DesktopAppConfig` and storage do not know `page_ready_template_path`

- [ ] **Step 3: Write the minimal model/storage implementation**

Update:
- `DesktopAppConfig` to accept and normalize `page_ready_template_path: Path | None`
- storage save/load payloads to persist the field

- [ ] **Step 4: Run tests to verify they pass**

Run:

```powershell
python -m pytest -q tests\desktop\test_models.py tests\desktop\test_storage.py -k page_ready
```

Expected:
- PASS

- [ ] **Step 5: Commit**

```powershell
git add raidbot/desktop/models.py raidbot/desktop/storage.py tests/desktop/test_models.py tests/desktop/test_storage.py
git commit -m "feat: persist page ready template path"
```

### Task 2: Add Page Ready Capture UI And Controller Wiring

**Files:**
- Modify: `raidbot/desktop/bot_actions/page.py`
- Modify: `raidbot/desktop/controller.py`
- Modify: `raidbot/desktop/main_window.py`
- Test: `tests/desktop/bot_actions/test_page.py`
- Test: `tests/desktop/test_controller.py`
- Test: `tests/desktop/test_main_window.py`

- [ ] **Step 1: Write the failing UI/controller tests**

Add tests that prove:
- Bot Actions page renders a shared page-ready capture section above the slot grid
- clicking `Capture` emits a dedicated page-ready signal and status text
- controller persists the captured page-ready path
- main window routes the capture result back into controller config sync

```python
def test_bot_actions_page_emits_page_ready_capture_request(qtbot) -> None:
    page = BotActionsPage(config=build_config())
    captured = []
    page.pageReadyCaptureRequested.connect(lambda: captured.append("capture"))
    qtbot.mouseClick(page.page_ready_capture_button, Qt.MouseButton.LeftButton)
    assert captured == ["capture"]
    assert page.status_label.text() == "Page Ready: capturing"
```

```python
def test_controller_updates_page_ready_template_and_saves(qtbot) -> None:
    controller = DesktopController(...)
    captured_path = Path("bot_actions/page_ready.png")
    controller.set_page_ready_template_path(captured_path)
    assert controller.config.page_ready_template_path == captured_path
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest -q tests\desktop\bot_actions\test_page.py tests\desktop\test_controller.py tests\desktop\test_main_window.py -k page_ready
```

Expected:
- fail because the page-ready UI and controller methods do not exist yet

- [ ] **Step 3: Write the minimal UI/controller implementation**

Update:
- `BotActionsPage` with shared page-ready preview + capture button + status/path
- `DesktopController` with `set_page_ready_template_path(...)`
- `MainWindow` capture flow to reuse the existing capture service and save the shared path

- [ ] **Step 4: Run tests to verify they pass**

Run:

```powershell
python -m pytest -q tests\desktop\bot_actions\test_page.py tests\desktop\test_controller.py tests\desktop\test_main_window.py -k page_ready
```

Expected:
- PASS

- [ ] **Step 5: Commit**

```powershell
git add raidbot/desktop/bot_actions/page.py raidbot/desktop/controller.py raidbot/desktop/main_window.py tests/desktop/bot_actions/test_page.py tests/desktop/test_controller.py tests/desktop/test_main_window.py
git commit -m "feat: add page ready capture controls"
```

### Task 3: Gate Bot Action Runs On Page Ready Detection

**Files:**
- Modify: `raidbot/desktop/worker.py`
- Test: `tests/desktop/test_worker.py`

- [ ] **Step 1: Write the failing worker tests**

Add tests that prove:
- if `page_ready_template_path` is configured and found, the worker waits for it before running the slot sequence
- if `page_ready_template_path` is configured and not found, that profile fails with `page_ready_not_found`
- if no page-ready template is configured, worker keeps current behavior

```python
def test_worker_waits_for_page_ready_before_running_sequence(tmp_path) -> None:
    runtime = FakeAutomationRuntime(...)
    worker = build_worker(..., config=build_config(page_ready_template_path=Path("page_ready.png")))
    worker._handle_message(build_message(...))
    assert runtime.run_calls == [("bot-actions", 17)]
    assert runtime.page_ready_checks == [(17, Path("page_ready.png"))]
```

```python
def test_worker_marks_profile_failed_when_page_ready_never_appears(tmp_path) -> None:
    runtime = FakeAutomationRuntime(page_ready_found=False)
    worker = build_worker(..., config=build_config(page_ready_template_path=Path("page_ready.png")))
    worker._handle_message(build_message(...))
    assert worker.state.raid_profile_states[0].last_error == "page_ready_not_found"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest -q tests\desktop\test_worker.py -k page_ready
```

Expected:
- fail because worker does not yet have a page-ready gate

- [ ] **Step 3: Write the minimal worker implementation**

Add a small worker helper that:
- checks whether `page_ready_template_path` is configured
- uses the existing automation matcher/runtime against the opened profile window
- returns success/failure before `runtime.run_sequence(...)`

Keep the failure mapping narrow:
- `page_ready_not_found` for timeout/no match

- [ ] **Step 4: Run tests to verify they pass**

Run:

```powershell
python -m pytest -q tests\desktop\test_worker.py -k page_ready
```

Expected:
- PASS

- [ ] **Step 5: Commit**

```powershell
git add raidbot/desktop/worker.py tests/desktop/test_worker.py
git commit -m "feat: wait for page ready before slot search"
```

### Task 4: Run Full Regression Suite

**Files:**
- No new files
- Verify touched code across:
  - `raidbot/desktop/models.py`
  - `raidbot/desktop/storage.py`
  - `raidbot/desktop/bot_actions/page.py`
  - `raidbot/desktop/controller.py`
  - `raidbot/desktop/main_window.py`
  - `raidbot/desktop/worker.py`

- [ ] **Step 1: Run focused regression suites**

Run:

```powershell
python -m pytest -q tests\desktop\bot_actions\test_page.py tests\desktop\test_controller.py tests\desktop\test_main_window.py tests\desktop\test_models.py tests\desktop\test_storage.py tests\desktop\test_worker.py
```

Expected:
- PASS

- [ ] **Step 2: Run full test suite**

Run:

```powershell
python -m pytest -q
```

Expected:
- PASS

- [ ] **Step 3: Commit final integration state**

```powershell
git add raidbot/desktop/models.py raidbot/desktop/storage.py raidbot/desktop/bot_actions/page.py raidbot/desktop/controller.py raidbot/desktop/main_window.py raidbot/desktop/worker.py tests/desktop/bot_actions/test_page.py tests/desktop/test_controller.py tests/desktop/test_main_window.py tests/desktop/test_models.py tests/desktop/test_storage.py tests/desktop/test_worker.py
git commit -m "test: cover page ready capture flow"
```

## Notes For The Implementer

- Follow @superpowers:test-driven-development for each task. Do not implement production code before the failing test is in place.
- Reuse the current capture service and page-preview pattern from the existing slot UI. Do not create a second capture subsystem.
- Reuse the existing automation matcher/runtime path inside the worker; do not add a separate browser automation stack just for page-ready.
- Keep the feature optional. If the user never captures a page-ready image, current bot behavior should remain intact.
