# Raid Bot Automation Groundwork Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the bot so it supports both `Raidar` and `D.RaidBot`, introduces a pluggable browser execution pipeline with a shipped no-op executor, and leaves only one narrow executor module for a future AI to finish.

**Architecture:** Split the current open-on-detect flow into `detect -> build job -> hand off to browser backend -> invoke executor -> record structured results`. Keep current behavior available through a `launch-only` backend, but move CLI and desktop runtime code onto shared browser/result contracts and migrate config/state to sender allowlists plus dedicated raid browser settings.

**Tech Stack:** Python 3.10, PySide6, Telethon, pytest

---

## File Map

### New files

- `raidbot/browser/__init__.py`
  - Browser package exports for pipeline types.
- `raidbot/browser/models.py`
  - `RaidActionRequirements`, `RaidActionJob`, `RaidDetectionResult`, `RaidExecutionResult`, browser/backend enums, preset reply model.
- `raidbot/browser/pipeline.py`
  - Shared browser execution orchestration and handoff logic.
- `raidbot/browser/backends.py`
  - `LaunchOnlyBrowserBackend`, `ControlledSessionBrowserBackend`, `BrowserSession` protocol, session result helpers.
- `raidbot/browser/executors/__init__.py`
  - Executor package exports.
- `raidbot/browser/executors/base.py`
  - Executor protocol / abstract base.
- `raidbot/browser/executors/noop.py`
  - Shipped no-op executor that returns `executor_not_configured`.
- `tests/test_browser_pipeline.py`
  - Browser pipeline and executor-contract unit tests.

### Modified files

- `raidbot/models.py`
  - Keep `IncomingMessage`; re-home or re-export detection-facing result types only if still needed.
- `raidbot/parser.py`
  - Parse active-raid markers into normalized action requirements and support synonym matching.
- `raidbot/service.py`
  - Convert from opener-driven service to detection/job construction with sender allowlists.
- `raidbot/config.py`
  - Replace single sender setting with allowlist and add browser/executor/preset-reply/default-action config.
- `raidbot/chrome.py`
  - Reduce to low-level launch helper or compatibility wrapper used by `LaunchOnlyBrowserBackend`.
- `raidbot/runtime.py`
  - Build shared detection service plus browser pipeline for CLI mode.
- `raidbot/main.py`
  - Keep CLI entrypoint aligned with new runtime config.
- `raidbot/desktop/models.py`
  - Add sender allowlist, preset replies, browser/executor settings, and new state counters.
- `raidbot/desktop/storage.py`
  - Config/state migration for allowlists and new counters.
- `raidbot/desktop/settings_page.py`
  - Sender allowlist editor, preset-reply pool editor, action toggles, browser/backend settings.
- `raidbot/desktop/telegram_setup.py`
  - Multi-bot candidate inference for `raidar` and `delugeraidbot`.
- `raidbot/desktop/wizard.py`
  - Multi-select allowed senders, dedicated raid browser profile wording, updated review summary.
- `raidbot/desktop/worker.py`
  - Orchestrate detection results, browser pipeline, second cancellation gate, and new stats/activity mapping.
- `raidbot/desktop/controller.py`
  - Keep event handling aligned with expanded worker events if needed.
- `raidbot/desktop/main_window.py`
  - Show updated counters and activity semantics.
- `README.md`
  - Document new config fields, dedicated raid browser profile, and no-op executor groundwork.
- `.env.example`
  - Document CLI-side allowlist and browser/executor settings if present in repo.

### Modified tests

- `tests/test_parser.py`
- `tests/test_service.py`
- `tests/test_config.py`
- `tests/test_runtime.py`
- `tests/test_chrome.py`
- `tests/desktop/test_models.py`
- `tests/desktop/test_storage.py`
- `tests/desktop/test_settings_page.py`
- `tests/desktop/test_telegram_setup.py`
- `tests/desktop/test_wizard.py`
- `tests/desktop/test_worker.py`
- `tests/desktop/test_main_window.py`
- `tests/desktop/test_controller.py`

---

### Task 1: Add Core Browser And Result Models

**Files:**
- Create: `raidbot/browser/__init__.py`
- Create: `raidbot/browser/models.py`
- Modify: `raidbot/models.py`
- Test: `tests/test_browser_pipeline.py`

- [ ] **Step 1: Write the failing model tests**

```python
from raidbot.browser.models import (
    RaidActionJob,
    RaidActionRequirements,
    RaidDetectionResult,
    RaidExecutionResult,
)


def test_detection_result_carries_job_for_detected_message():
    job = RaidActionJob(
        normalized_url="https://x.com/i/status/123",
        raw_url="https://x.com/i/status/123",
        chat_id=-1001,
        sender_id=42,
        requirements=RaidActionRequirements(
            like=True,
            repost=True,
            bookmark=False,
            reply=True,
        ),
        preset_replies=("gm",),
        trace_id="raid-1",
    )

    result = RaidDetectionResult.job_detected(job)

    assert result.kind == "job_detected"
    assert result.job == job


def test_execution_result_exposes_structured_failure_kind():
    result = RaidExecutionResult(kind="page_ready_timeout", handed_off=False)
    assert result.kind == "page_ready_timeout"
    assert result.handed_off is False
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `python -m pytest -q tests\test_browser_pipeline.py`

Expected: FAIL with import errors for `raidbot.browser.models`

- [ ] **Step 3: Implement the minimal models**

```python
@dataclass(frozen=True)
class RaidActionRequirements:
    like: bool
    repost: bool
    bookmark: bool
    reply: bool


@dataclass(frozen=True)
class RaidActionJob:
    normalized_url: str
    raw_url: str
    chat_id: int
    sender_id: int
    requirements: RaidActionRequirements
    preset_replies: tuple[str, ...]
    trace_id: str


@dataclass(frozen=True)
class RaidDetectionResult:
    kind: str
    normalized_url: str | None = None
    job: RaidActionJob | None = None
```

- [ ] **Step 4: Re-export or trim old shared models carefully**

Keep `IncomingMessage` in `raidbot/models.py`. Either move legacy `MessageOutcome` behind compatibility helpers for intermediate call sites, or remove it once the service/runtime tests are updated in later tasks.

- [ ] **Step 5: Run the focused test to verify it passes**

Run: `python -m pytest -q tests\test_browser_pipeline.py`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add raidbot/browser/__init__.py raidbot/browser/models.py raidbot/models.py tests/test_browser_pipeline.py
git commit -m "feat: add raid browser model contracts"
```

### Task 2: Normalize Parser Output And Add Two-Bot Samples

**Files:**
- Modify: `raidbot/parser.py`
- Test: `tests/test_parser.py`

- [ ] **Step 1: Extend parser tests with synonym and source samples**

```python
D_RAIDBOT_MESSAGE = """
Reposts 8 | 8 [%]
Bookmarks 4 | 4 [%]
Replies 2 | 2 [%]

https://x.com/i/status/999
"""


def test_parse_raid_message_extracts_required_actions():
    match = parse_raid_message(D_RAIDBOT_MESSAGE)
    assert match is not None
    assert match.requirements.repost is True
    assert match.requirements.bookmark is True
    assert match.requirements.reply is True
    assert match.requirements.like is False
```

- [ ] **Step 2: Run the parser tests to verify they fail**

Run: `python -m pytest -q tests\test_parser.py`

Expected: FAIL because `requirements` and synonym parsing do not exist yet

- [ ] **Step 3: Implement parser normalization**

```python
MARKER_GROUPS = {
    "like": ("like", "likes"),
    "repost": ("retweet", "retweets", "repost", "reposts"),
    "reply": ("reply", "replies"),
    "bookmark": ("bookmark", "bookmarks"),
}


def _has_any_marker(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers)
```

Return a richer parse result that includes `raw_url`, `normalized_url`, and `RaidActionRequirements`.

- [ ] **Step 4: Keep queue-message rejection intact**

Preserve the current `Next up...` rejection behavior while expanding marker support. Do not broaden parsing so far that queue posts start matching.

- [ ] **Step 5: Re-run parser tests**

Run: `python -m pytest -q tests\test_parser.py`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add raidbot/parser.py tests/test_parser.py
git commit -m "feat: normalize raid markers across supported bots"
```

### Task 3: Convert The Service To Sender Allowlists And Detection Results

**Files:**
- Modify: `raidbot/service.py`
- Modify: `raidbot/config.py`
- Test: `tests/test_service.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Rewrite service tests around detection instead of browser opening**

```python
def test_handle_message_detects_job_for_allowed_sender():
    service = RaidService(
        allowed_chat_ids={-1001},
        allowed_sender_ids={42, 77},
        dedupe_store=InMemoryOpenedUrlStore(),
        preset_replies=("gm",),
        default_requirements=RaidActionRequirements(True, True, False, True),
    )

    result = service.handle_message(
        IncomingMessage(
            chat_id=-1001,
            sender_id=77,
            text="Likes 10 | 8 [%]\\n\\nhttps://x.com/i/status/123",
        )
    )

    assert result.kind == "job_detected"
    assert result.job is not None
    assert result.job.sender_id == 77


def test_handle_message_returns_duplicate_before_job_creation():
    dedupe_store = FakeDedupeStore(existing={"https://x.com/i/status/123"})
    service = RaidService(...)

    result = service.handle_message(
        IncomingMessage(
            chat_id=-1001,
            sender_id=42,
            text="Likes 10 | 8 [%]\\n\\nhttps://x.com/i/status/123",
        )
    )

    assert result.kind == "duplicate"
    assert result.job is None
```

- [ ] **Step 2: Add config tests for sender allowlists and compatibility fallback**

```python
def test_settings_from_env_reads_allowed_sender_ids(monkeypatch):
    monkeypatch.setenv("ALLOWED_SENDER_IDS", "42,77")
    settings = Settings.from_env()
    assert settings.allowed_sender_ids == {42, 77}
```

Also add one compatibility test where `RAIDAR_SENDER_ID` still loads as a one-element set when `ALLOWED_SENDER_IDS` is missing.

- [ ] **Step 3: Run the focused tests to verify they fail**

Run: `python -m pytest -q tests\test_service.py tests\test_config.py`

Expected: FAIL because the service still expects one sender ID and still opens the browser directly

- [ ] **Step 4: Implement detection-only service behavior**

```python
if message.chat_id not in self.allowed_chat_ids:
    return RaidDetectionResult.chat_rejected()

if message.sender_id not in self.allowed_sender_ids:
    return RaidDetectionResult.sender_rejected()

match = parse_raid_message(message.text)
if match is None:
    return RaidDetectionResult.not_a_raid()

if self.dedupe_store.contains(match.normalized_url):
    return RaidDetectionResult.duplicate(match.normalized_url)
```

Build `RaidActionJob` only after the duplicate check passes, but do not call `mark_if_new()` yet. Dedupe timing is completed by the execution pipeline in a later task.

- [ ] **Step 5: Implement config parsing**

Add fields for:

- `allowed_sender_ids`
- `browser_mode`
- `executor_name`
- `preset_replies`
- default action toggles

Keep env parsing simple and explicit. Prefer small helper functions such as `_parse_bool` and `_parse_str_list`.

- [ ] **Step 6: Re-run the focused tests**

Run: `python -m pytest -q tests\test_service.py tests\test_config.py`

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add raidbot/service.py raidbot/config.py tests/test_service.py tests/test_config.py
git commit -m "feat: switch raid detection to sender allowlists"
```

### Task 4: Build The Browser Pipeline And Both Browser Backends

**Files:**
- Create: `raidbot/browser/backends.py`
- Create: `raidbot/browser/pipeline.py`
- Create: `raidbot/browser/executors/__init__.py`
- Create: `raidbot/browser/executors/base.py`
- Create: `raidbot/browser/executors/noop.py`
- Modify: `raidbot/chrome.py`
- Test: `tests/test_browser_pipeline.py`
- Test: `tests/test_chrome.py`

- [ ] **Step 1: Add pipeline tests for handoff, no-op executor, and dedupe timing**

```python
def test_launch_only_backend_marks_handoff_when_launch_succeeds():
    backend = FakeBackend(result=RaidExecutionResult(kind="executor_not_configured", handed_off=True))
    pipeline = BrowserPipeline(backend=backend, executor=NoOpRaidExecutor())

    result = pipeline.execute(job)

    assert result.kind == "executor_not_configured"
    assert result.handed_off is True


def test_controlled_session_backend_reports_page_ready_timeout():
    session = FakeBrowserSession(page_ready=False)
    backend = ControlledSessionBrowserBackend(session_factory=lambda: session)

    result = backend.execute(job, NoOpRaidExecutor())

    assert result.kind == "page_ready_timeout"
    assert result.handed_off is False
```

Add explicit tests for:

- browser startup failure
- navigation failure
- page-ready timeout
- cancelled before executor
- executor success/failure passthrough
- session-close failure after executor handoff

- [ ] **Step 2: Run browser-focused tests to verify they fail**

Run: `python -m pytest -q tests\test_browser_pipeline.py tests\test_chrome.py`

Expected: FAIL because the pipeline and executor modules do not exist yet

- [ ] **Step 3: Implement the browser backend interfaces**

```python
class BrowserBackend(Protocol):
    def execute(self, job: RaidActionJob, executor: RaidExecutor) -> RaidExecutionResult:
        ...


class LaunchOnlyBrowserBackend:
    def execute(self, job: RaidActionJob, executor: RaidExecutor) -> RaidExecutionResult:
        self._launcher.open(job.normalized_url)
        return RaidExecutionResult(kind="executor_not_configured", handed_off=True)


class BrowserSession(Protocol):
    def navigate(self, url: str) -> None:
        ...

    def wait_until_ready(self) -> bool:
        ...

    def close(self) -> None:
        ...


class ControlledSessionBrowserBackend:
    def execute(self, job: RaidActionJob, executor: RaidExecutor) -> RaidExecutionResult:
        session = self._session_factory()
        ...
```

Use `raidbot/chrome.py` only as the low-level Chrome launch helper. Keep `ControlledSessionBrowserBackend` real at the contract level: it must perform navigate/page-ready/close sequencing and surface distinct failure kinds even if the production session factory remains simple.

- [ ] **Step 4: Implement the no-op executor**

```python
class NoOpRaidExecutor(RaidExecutor):
    def execute(self, job: RaidActionJob, session) -> RaidExecutionResult:
        return RaidExecutionResult(kind="executor_not_configured", handed_off=True)
```

For `launch-only`, the backend can skip session objects entirely. For `controlled-session`, implement the full navigate/page-ready/close flow against the `BrowserSession` protocol and return the distinct failure kinds exercised by the tests.

- [ ] **Step 5: Re-run browser-focused tests**

Run: `python -m pytest -q tests\test_browser_pipeline.py tests\test_chrome.py`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add raidbot/browser/backends.py raidbot/browser/pipeline.py raidbot/browser/executors/__init__.py raidbot/browser/executors/base.py raidbot/browser/executors/noop.py raidbot/chrome.py tests/test_browser_pipeline.py tests/test_chrome.py
git commit -m "feat: add browser pipeline and noop executor"
```

### Task 5: Wire The CLI Runtime To Detection Plus Browser Execution

**Files:**
- Modify: `raidbot/runtime.py`
- Modify: `raidbot/main.py`
- Test: `tests/test_runtime.py`

- [ ] **Step 1: Rewrite runtime tests around the new pipeline**

```python
def test_build_runtime_wires_allowlist_backend_and_noop_executor(monkeypatch):
    settings = build_settings(allowed_sender_ids={42, 77}, browser_mode="launch-only")
    runtime = build_runtime(settings)
    assert runtime.service.allowed_sender_ids == {42, 77}
    assert runtime.pipeline.executor_name == "noop"
```

Add a test that a detected job becomes deduped only after a handed-off execution result.

- [ ] **Step 2: Run runtime tests to verify they fail**

Run: `python -m pytest -q tests\test_runtime.py`

Expected: FAIL because `build_runtime()` still instantiates `ChromeOpener` directly

- [ ] **Step 3: Implement shared runtime orchestration**

```python
result = service.handle_message(message)
if result.kind != "job_detected":
    return result

execution = pipeline.execute(result.job)
if execution.handed_off:
    dedupe_store.mark_if_new(result.job.normalized_url)
return execution
```

Keep the listener wiring unchanged: `main.py` should still just load env, build the runtime, and run the listener.

- [ ] **Step 4: Re-run runtime tests**

Run: `python -m pytest -q tests\test_runtime.py`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/runtime.py raidbot/main.py tests/test_runtime.py
git commit -m "feat: wire cli runtime to browser execution pipeline"
```

### Task 6: Migrate Desktop Config, State, Settings, And Dashboard

**Files:**
- Modify: `raidbot/desktop/models.py`
- Modify: `raidbot/desktop/storage.py`
- Modify: `raidbot/desktop/settings_page.py`
- Modify: `raidbot/desktop/main_window.py`
- Test: `tests/desktop/test_models.py`
- Test: `tests/desktop/test_storage.py`
- Test: `tests/desktop/test_settings_page.py`
- Test: `tests/desktop/test_main_window.py`

- [ ] **Step 1: Add failing desktop-model and storage migration tests**

```python
def test_storage_loads_legacy_single_sender_as_allowlist(tmp_path):
    storage = DesktopStorage(tmp_path)
    storage.config_path.write_text(json.dumps({"raidar_sender_id": 42, ...}), encoding="utf-8")
    config = storage.load_config()
    assert config.allowed_sender_ids == [42]
```

Add state tests verifying old counters still load and new counters default to zero.

- [ ] **Step 2: Add failing settings-page tests for the new fields**

```python
def test_settings_save_emits_allowlist_and_preset_replies(qtbot):
    page.allowed_senders_input.setText("42,77")
    page.reply_pool_input.setPlainText("gm\\nlfggg")
    page.like_toggle.setChecked(True)
    ...
```

- [ ] **Step 3: Run the focused desktop config tests**

Run: `python -m pytest -q tests\desktop\test_models.py tests\desktop\test_storage.py tests\desktop\test_settings_page.py tests\desktop\test_main_window.py`

Expected: FAIL because the desktop config model still only supports one sender and old counters

- [ ] **Step 4: Implement config/state migration**

Update `DesktopAppConfig` to include:

- `allowed_sender_ids`
- `browser_mode`
- `executor_name`
- `preset_replies`
- default action toggles

Update `DesktopAppState` with new pipeline counters while preserving legacy meanings for:

- `raids_opened`
- `duplicates_skipped`
- `non_matching_skipped`
- `open_failures`

- [ ] **Step 5: Implement settings page and dashboard updates**

Add:

- sender allowlist text field
- shared preset-reply pool editor
- action toggles
- backend/mode display or selector
- dashboard labels and counters for:
  - `sender_rejected`
  - `browser_session_failed`
  - `page_ready`
  - `executor_not_configured`
  - `executor_succeeded`
  - `executor_failed`
  - `session_closed`

Keep the page layouts aligned with the current premium dark UI.

- [ ] **Step 6: Re-run the focused desktop config tests**

Run: `python -m pytest -q tests\desktop\test_models.py tests\desktop\test_storage.py tests\desktop\test_settings_page.py tests\desktop\test_main_window.py`

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add raidbot/desktop/models.py raidbot/desktop/storage.py raidbot/desktop/settings_page.py raidbot/desktop/main_window.py tests/desktop/test_models.py tests/desktop/test_storage.py tests/desktop/test_settings_page.py tests/desktop/test_main_window.py
git commit -m "feat: migrate desktop config and state for browser pipeline"
```

### Task 7: Update Telegram Setup And Wizard For Multi-Bot Sender Discovery

**Files:**
- Modify: `raidbot/desktop/telegram_setup.py`
- Modify: `raidbot/desktop/wizard.py`
- Test: `tests/desktop/test_telegram_setup.py`
- Test: `tests/desktop/test_wizard.py`

- [ ] **Step 1: Add failing Telegram setup tests for `raidar` and `delugeraidbot`**

```python
def test_detect_raid_candidates_prefers_exact_supported_usernames():
    entities = [
        FakeEntity(entity_id=1, username="raidar"),
        FakeEntity(entity_id=2, username="delugeraidbot"),
    ]
    candidates = detect_raid_candidates(entities)
    assert [candidate.entity_id for candidate in candidates] == [1, 2]
```

Add wizard tests proving more than one sender can be confirmed and serialized into config.

- [ ] **Step 2: Run the focused wizard/setup tests**

Run: `python -m pytest -q tests\desktop\test_telegram_setup.py tests\desktop\test_wizard.py`

Expected: FAIL because sender discovery and wizard serialization still assume one sender

- [ ] **Step 3: Implement multi-candidate discovery**

Extend candidate matching to recognize:

- `raidar`
- `delugeraidbot`
- `d.raidbot`

Rank exact username/name hits ahead of fallback frequency sorting.

- [ ] **Step 4: Implement wizard multi-select sender confirmation**

Replace the single combo/manual-ID flow with a UI that can confirm multiple detected senders, while keeping a manual fallback path for edge cases.

The review page should summarize all selected sender IDs and the dedicated raid browser profile wording.

- [ ] **Step 5: Re-run the focused wizard/setup tests**

Run: `python -m pytest -q tests\desktop\test_telegram_setup.py tests\desktop\test_wizard.py`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add raidbot/desktop/telegram_setup.py raidbot/desktop/wizard.py tests/desktop/test_telegram_setup.py tests/desktop/test_wizard.py
git commit -m "feat: support multi-bot sender discovery in setup"
```

### Task 8: Wire Desktop Worker Events To The New Pipeline

**Files:**
- Modify: `raidbot/desktop/worker.py`
- Modify: `raidbot/desktop/controller.py`
- Test: `tests/desktop/test_worker.py`
- Test: `tests/desktop/test_controller.py`

- [ ] **Step 1: Add failing worker tests for the second cancellation gate and handoff-driven dedupe**

```python
def test_worker_skips_executor_when_stop_requested_after_page_ready():
    worker = build_worker(...)
    worker._stop_requested = True
    result = worker._execute_job(job)
    assert result.kind == "cancelled_before_executor"
```

Add one test verifying dedupe is marked only after a handed-off execution result.

Also add worker/controller tests that explicitly cover:

- `sender_rejected`
- `browser_session_failed`
- `executor_succeeded`
- `session_closed`

- [ ] **Step 2: Run the focused worker/controller tests**

Run: `python -m pytest -q tests\desktop\test_worker.py tests\desktop\test_controller.py`

Expected: FAIL because the worker still maps straight from service result to `ChromeOpener.open()`

- [ ] **Step 3: Implement worker orchestration and event mapping**

```python
detection = self._service.handle_message(message)
if detection.kind != "job_detected":
    self._record_detection_result(detection)
    return detection

execution = self._pipeline.execute(detection.job, should_continue=self._can_start_executor)
if execution.handed_off:
    self._dedupe_store.mark_if_new(detection.job.normalized_url)
self._record_execution_result(execution)
```

Emit activity entries for:

- `raid_detected`
- `sender_rejected`
- `browser_session_opened`
- `browser_session_failed`
- `page_ready`
- `executor_not_configured`
- `executor_succeeded`
- `cancelled_before_executor`
- `executor_failed`
- `session_closed`

- [ ] **Step 4: Re-run the focused worker/controller tests**

Run: `python -m pytest -q tests\desktop\test_worker.py tests\desktop\test_controller.py`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/desktop/worker.py raidbot/desktop/controller.py tests/desktop/test_worker.py tests/desktop/test_controller.py
git commit -m "feat: connect desktop worker to browser execution pipeline"
```

### Task 9: Update Docs And Run Full Verification

**Files:**
- Modify: `README.md`
- Modify: `.env.example`

- [ ] **Step 1: Update README**

Document:

- multi-sender support for `Raidar` and `D.RaidBot`
- dedicated raid browser profile guidance
- shared preset-reply storage
- shipped no-op executor boundary
- new CLI config keys

- [ ] **Step 2: Update `.env.example`**

Add explicit examples for:

- `ALLOWED_SENDER_IDS`
- `BROWSER_MODE`
- `EXECUTOR_NAME`
- `PRESET_REPLIES`
- default action toggles

- [ ] **Step 3: Run the full test suite**

Run: `python -m pytest -q`

Expected: PASS

- [ ] **Step 4: Smoke-check the desktop app startup path**

Run:

```powershell
$env:APPDATA = Join-Path $PWD ".tmp_appdata_smoke"
$p = Start-Process pythonw -ArgumentList "-m raidbot.desktop.app" -PassThru
Start-Sleep -Seconds 5
if ($p.HasExited) { throw "desktop app exited during smoke check" }
Stop-Process -Id $p.Id
```

Expected: the app process stays alive for 5 seconds and can be terminated cleanly

- [ ] **Step 5: Commit**

```bash
git add README.md .env.example
git commit -m "docs: document automation groundwork configuration"
```

- [ ] **Step 6: Verify the branch is clean**

Run: `git status --short`

Expected: no output
