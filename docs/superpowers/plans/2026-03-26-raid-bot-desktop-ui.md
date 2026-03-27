# Raid Bot Desktop UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a PySide6 desktop application that wraps the existing raid bot with a first-run setup wizard, persistent settings and app state, live bot statistics, and minimize-to-tray behavior.

**Architecture:** Keep the current bot logic reusable and UI-agnostic, then add a `raidbot.desktop` package that owns desktop models, storage, setup services, a Qt worker/controller boundary, and the actual windows/widgets. The UI talks to a worker thread through explicit state and event signals, while the bot runtime continues to use the existing parser, dedupe, Chrome opener, and Telegram listener modules.

**Tech Stack:** Python 3.10+, PySide6, Telethon, python-dotenv, pytest, pytest-qt, pytest-asyncio, stdlib `json`, `logging`, `pathlib`, `enum`, `asyncio`

---

## Prerequisites

This workspace is not currently a git repository, so the commit checkpoints below are informational until `git init` exists.

The brainstorming workflow expected a dedicated git worktree, but that is not possible until the repo is initialized. Execute this plan in-place unless the repo is converted to git first.

## File Map

- Modify: `pyproject.toml`
  - Add PySide6 and pytest-qt, switch setuptools packaging to include `raidbot.desktop`
- Modify: `README.md`
  - Document the desktop app install, first-run wizard, and launch flow
- Modify: `raidbot/telegram_client.py`
  - Add clean stop support and optional connection callbacks for desktop control
- Modify: `tests/test_telegram_client.py`
  - Cover the new stop and connection-callback behavior
- Create: `raidbot/desktop/__init__.py`
  - Desktop package marker and exports
- Create: `raidbot/desktop/models.py`
  - Desktop config, app-state, stats, activity, and runtime-state models
- Create: `raidbot/desktop/storage.py`
  - JSON persistence for config and app state, plus first-run detection
- Create: `raidbot/desktop/chrome_profiles.py`
  - Detect Chrome installation/user-data paths and enumerate profiles
- Create: `raidbot/desktop/telegram_setup.py`
  - One-time authorization, chat discovery, and `Raidar` discovery helpers
- Create: `raidbot/desktop/worker.py`
  - Worker-side bot runtime glue, persistent app-state updates, and event emission for UI consumption
- Create: `raidbot/desktop/controller.py`
  - Qt-facing controller that owns the worker thread, state-driven actions, and clean shutdown/apply behavior
- Create: `raidbot/desktop/wizard.py`
  - First-run setup wizard and its page classes
- Create: `raidbot/desktop/main_window.py`
  - Main desktop window, stats/activity display, and navigation shell
- Create: `raidbot/desktop/settings_page.py`
  - Dedicated post-setup settings page with session status, reauthorization, and editable bot settings
- Create: `raidbot/desktop/tray.py`
  - System tray icon and menu integration
- Create: `raidbot/desktop/app.py`
  - Desktop bootstrap that routes first-run to the wizard and later launches to the main window
- Create: `tests/desktop/test_models.py`
  - Desktop model tests
- Create: `tests/desktop/test_storage.py`
  - Config/state persistence and first-run tests
- Create: `tests/desktop/test_chrome_profiles.py`
  - Chrome detection and profile enumeration tests
- Create: `tests/desktop/test_telegram_setup.py`
  - Authorization and discovery tests with fake Telethon clients
- Create: `tests/desktop/test_worker.py`
  - Worker stats/activity/state tests
- Create: `tests/desktop/test_controller.py`
  - Controller thread orchestration and live-apply tests
- Create: `tests/desktop/test_wizard.py`
  - Wizard progression and step validation tests
- Create: `tests/desktop/test_main_window.py`
  - Main window and tray/minimize behavior tests
- Create: `tests/desktop/test_settings_page.py`
  - Dedicated settings-page tests
- Create: `tests/desktop/test_app.py`
  - App bootstrap tests for first-run vs configured launch behavior

## Implementation Notes

- Keep the existing CLI daemon entrypoint `raidbot.main` working. The desktop app is an additional entrypoint, not a replacement.
- Store desktop config and app state under `%APPDATA%\RaidBot\` in v1:
  - `config.json`
  - `state.json`
- Persist the most recent 200 activity entries in `state.json`.
- Persist counters across bot restarts and full app restarts until state is cleared.
- Persist `last_successful_raid_open_at` across bot restarts and full app restarts.
- Auto-detect Chrome from standard Windows locations only in v1:
  - `%PROGRAMFILES%\Google\Chrome\Application\chrome.exe`
  - `%PROGRAMFILES(X86)%\Google\Chrome\Application\chrome.exe`
  - `%LOCALAPPDATA%\Google\Chrome\User Data`
- Do not add manual Chrome executable selection in v1.
- `Raidar` detection rule in setup:
  - exact username `raidar`
  - else exact display name `Raidar`
  - else infer candidates from recent senders and require explicit confirmation
- Later settings edits should apply live when safe:
  - whitelist / `Raidar` sender / Chrome profile update future message handling immediately
  - Telegram credential/session changes trigger controlled reconnect or reauthorization
- Close behavior:
  - during setup: close exits normally
  - after setup, minimize goes to tray
  - when bot stopped: close exits
  - when bot running: close asks for confirmation, then stops and exits if confirmed

### Task 1: Package Desktop Dependencies And Models

**Files:**
- Modify: `pyproject.toml`
- Create: `raidbot/desktop/__init__.py`
- Create: `raidbot/desktop/models.py`
- Test: `tests/desktop/test_models.py`

- [ ] **Step 1: Write the failing desktop model tests**

```python
from pathlib import Path

from raidbot.desktop.models import (
    ActivityEntry,
    BotRuntimeState,
    DesktopAppConfig,
    DesktopAppState,
    TelegramConnectionState,
)


def test_desktop_app_config_holds_required_values():
    config = DesktopAppConfig(
        telegram_api_id=123456,
        telegram_api_hash="hash-value",
        telegram_session_path=Path("raidbot.session"),
        telegram_phone_number="+40123456789",
        whitelisted_chat_ids=[-1001],
        raidar_sender_id=42,
        chrome_profile_directory="Profile 3",
    )

    assert config.telegram_api_id == 123456
    assert config.chrome_profile_directory == "Profile 3"


def test_desktop_app_state_defaults_to_stopped_and_empty_history():
    state = DesktopAppState()

    assert state.bot_state is BotRuntimeState.STOPPED
    assert state.connection_state is TelegramConnectionState.DISCONNECTED
    assert state.activity == []
    assert state.last_successful_raid_open_at is None


def test_activity_entry_can_serialize_timestamp_and_reason():
    entry = ActivityEntry(
        timestamp="2026-03-26T10:00:00Z",
        action="duplicate",
        url="https://x.com/i/status/123",
        reason="duplicate",
    )

    assert entry.reason == "duplicate"
```

- [ ] **Step 2: Run the desktop model tests to verify they fail**

Run: `python -m pytest tests/desktop/test_models.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'raidbot.desktop'`

- [ ] **Step 3: Write the minimal package and models**

```python
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class BotRuntimeState(str, Enum):
    SETUP_REQUIRED = "setup_required"
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"


class TelegramConnectionState(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    AUTH_REQUIRED = "auth_required"


@dataclass(frozen=True)
class DesktopAppConfig:
    telegram_api_id: int
    telegram_api_hash: str
    telegram_session_path: Path
    telegram_phone_number: str | None
    whitelisted_chat_ids: list[int]
    raidar_sender_id: int | None
    chrome_profile_directory: str


@dataclass(frozen=True)
class ActivityEntry:
    timestamp: str
    action: str
    url: str | None = None
    reason: str | None = None


@dataclass
class DesktopAppState:
    bot_state: BotRuntimeState = BotRuntimeState.STOPPED
    connection_state: TelegramConnectionState = TelegramConnectionState.DISCONNECTED
    raids_opened: int = 0
    duplicates_skipped: int = 0
    non_matching_skipped: int = 0
    open_failures: int = 0
    last_successful_raid_open_at: str | None = None
    activity: list[ActivityEntry] = field(default_factory=list)
    last_error: str | None = None
```

Also update `pyproject.toml`:

- add runtime dependency `PySide6`
- add dev dependency `pytest-qt`
- replace `packages = ["raidbot"]` with setuptools package discovery that includes `raidbot.*`

- [ ] **Step 4: Run the desktop model tests to verify they pass**

Run: `python -m pytest tests/desktop/test_models.py -q`
Expected: `3 passed`

- [ ] **Step 5: Commit the desktop foundation**

```bash
git add pyproject.toml raidbot/desktop/__init__.py raidbot/desktop/models.py tests/desktop/test_models.py
git commit -m "feat: add desktop app models and package deps"
```

Expected: one commit containing the desktop package foundation

### Task 2: Persist Desktop Config And App State

**Files:**
- Create: `raidbot/desktop/storage.py`
- Test: `tests/desktop/test_storage.py`

- [ ] **Step 1: Write the failing storage tests**

```python
from pathlib import Path

from raidbot.desktop.models import DesktopAppConfig, DesktopAppState
from raidbot.desktop.storage import DesktopStorage


def test_storage_round_trips_config_and_state(tmp_path):
    storage = DesktopStorage(base_dir=tmp_path)
    config = DesktopAppConfig(
        telegram_api_id=123456,
        telegram_api_hash="hash-value",
        telegram_session_path=Path("raidbot.session"),
        telegram_phone_number="+40123456789",
        whitelisted_chat_ids=[-1001],
        raidar_sender_id=42,
        chrome_profile_directory="Profile 3",
    )
    state = DesktopAppState(
        raids_opened=5,
        duplicates_skipped=2,
        open_failures=1,
        last_successful_raid_open_at="2026-03-26T10:00:00Z",
        activity=[
            ActivityEntry(
                timestamp="2026-03-26T10:00:00Z",
                action="opened",
                url="https://x.com/i/status/123",
            )
        ],
    )

    storage.save_config(config)
    storage.save_state(state)

    assert storage.load_config() == config
    loaded_state = storage.load_state()
    assert loaded_state.raids_opened == 5
    assert loaded_state.duplicates_skipped == 2
    assert loaded_state.last_successful_raid_open_at == "2026-03-26T10:00:00Z"
    assert loaded_state.activity[0].action == "opened"


def test_storage_reports_first_run_when_config_is_missing(tmp_path):
    storage = DesktopStorage(base_dir=tmp_path)

    assert storage.is_first_run() is True


def test_storage_caps_activity_history_to_200_entries(tmp_path):
    storage = DesktopStorage(base_dir=tmp_path)
    state = DesktopAppState(
        activity=[
            ActivityEntry(timestamp=f"2026-03-26T10:00:{i:02d}Z", action="opened")
            for i in range(205)
        ]
    )

    storage.save_state(state)

    assert len(storage.load_state().activity) == 200
```

- [ ] **Step 2: Run the storage tests to verify they fail**

Run: `python -m pytest tests/desktop/test_storage.py -q`
Expected: FAIL because `raidbot.desktop.storage` does not exist

- [ ] **Step 3: Write the minimal storage layer**

```python
import json
from dataclasses import asdict
from pathlib import Path

from raidbot.desktop.models import ActivityEntry, DesktopAppConfig, DesktopAppState


class DesktopStorage:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.config_path = base_dir / "config.json"
        self.state_path = base_dir / "state.json"

    def is_first_run(self) -> bool:
        return not self.config_path.exists()

    def save_config(self, config: DesktopAppConfig) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        payload = asdict(config)
        payload["telegram_session_path"] = str(config.telegram_session_path)
        self.config_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def load_config(self) -> DesktopAppConfig:
        payload = json.loads(self.config_path.read_text(encoding="utf-8"))
        payload["telegram_session_path"] = Path(payload["telegram_session_path"])
        return DesktopAppConfig(**payload)

    def save_state(self, state: DesktopAppState) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        payload = asdict(state)
        payload["activity"] = payload["activity"][-200:]
        self.state_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def load_state(self) -> DesktopAppState:
        if not self.state_path.exists():
            return DesktopAppState()
        payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        payload["activity"] = [ActivityEntry(**item) for item in payload.get("activity", [])]
        return DesktopAppState(**payload)
```

Refine before moving on:

- add `default_base_dir()` returning `%APPDATA%\RaidBot`
- serialize enum values cleanly
- cap activity history at 200 on save and load
- keep `last_successful_raid_open_at` round-tripped through storage

- [ ] **Step 4: Run the storage tests to verify they pass**

Run: `python -m pytest tests/desktop/test_storage.py -q`
Expected: `3 passed`

- [ ] **Step 5: Commit the storage layer**

```bash
git add raidbot/desktop/storage.py tests/desktop/test_storage.py
git commit -m "feat: add desktop config and state storage"
```

Expected: one commit containing desktop persistence

### Task 3: Detect Chrome Profiles From Standard Windows Locations

**Files:**
- Create: `raidbot/desktop/chrome_profiles.py`
- Test: `tests/desktop/test_chrome_profiles.py`

- [ ] **Step 1: Write the failing Chrome detection tests**

```python
from pathlib import Path

from raidbot.desktop.chrome_profiles import detect_chrome_environment


def test_detect_chrome_environment_reads_profiles_from_local_state(tmp_path, monkeypatch):
    local_appdata = tmp_path / "Local"
    user_data_dir = local_appdata / "Google" / "Chrome" / "User Data"
    user_data_dir.mkdir(parents=True)
    (user_data_dir / "Local State").write_text(
        '{"profile":{"info_cache":{"Default":{"name":"Main"},"Profile 3":{"name":"Raid"}}}}',
        encoding="utf-8",
    )
    (user_data_dir / "Default").mkdir()
    (user_data_dir / "Profile 3").mkdir()

    chrome_exe = tmp_path / "Program Files" / "Google" / "Chrome" / "Application" / "chrome.exe"
    chrome_exe.parent.mkdir(parents=True)
    chrome_exe.write_text("", encoding="utf-8")

    monkeypatch.setenv("LOCALAPPDATA", str(local_appdata))
    monkeypatch.setenv("PROGRAMFILES", str(tmp_path / "Program Files"))
    monkeypatch.delenv("PROGRAMFILES(X86)", raising=False)

    env = detect_chrome_environment()

    assert env.chrome_path == chrome_exe
    assert [profile.directory_name for profile in env.profiles] == ["Default", "Profile 3"]
    assert env.profiles[1].label == "Raid"
```

- [ ] **Step 2: Run the Chrome detection tests to verify they fail**

Run: `python -m pytest tests/desktop/test_chrome_profiles.py -q`
Expected: FAIL because `raidbot.desktop.chrome_profiles` does not exist

- [ ] **Step 3: Write the minimal Chrome detection code**

```python
from dataclasses import dataclass
import json
import os
from pathlib import Path


@dataclass(frozen=True)
class ChromeProfile:
    directory_name: str
    label: str


@dataclass(frozen=True)
class ChromeEnvironment:
    chrome_path: Path
    user_data_dir: Path
    profiles: list[ChromeProfile]


def detect_chrome_environment() -> ChromeEnvironment:
    chrome_path = _find_chrome_path()
    user_data_dir = Path(os.environ["LOCALAPPDATA"]) / "Google" / "Chrome" / "User Data"
    local_state = json.loads((user_data_dir / "Local State").read_text(encoding="utf-8"))
    info_cache = local_state.get("profile", {}).get("info_cache", {})
    profiles = [
        ChromeProfile(directory_name=name, label=data.get("name", name))
        for name, data in info_cache.items()
        if (user_data_dir / name).exists()
    ]
    return ChromeEnvironment(chrome_path=chrome_path, user_data_dir=user_data_dir, profiles=profiles)
```

Refine before finalizing:

- fail with a clear `RuntimeError` if Chrome or `Local State` is missing
- preserve stable ordering: `Default` first, then `Profile N`

- [ ] **Step 4: Run the Chrome detection tests to verify they pass**

Run: `python -m pytest tests/desktop/test_chrome_profiles.py -q`
Expected: `1 passed`

- [ ] **Step 5: Commit Chrome detection**

```bash
git add raidbot/desktop/chrome_profiles.py tests/desktop/test_chrome_profiles.py
git commit -m "feat: add chrome profile detection"
```

Expected: one commit containing Chrome environment detection

### Task 4: Add Telegram Authorization And Discovery Services

**Files:**
- Create: `raidbot/desktop/telegram_setup.py`
- Test: `tests/desktop/test_telegram_setup.py`

- [ ] **Step 1: Write the failing Telegram setup tests**

```python
import asyncio

from raidbot.desktop.telegram_setup import detect_raidar_candidates


class FakeEntity:
    def __init__(self, entity_id, username=None, first_name=None, title=None):
        self.id = entity_id
        self.username = username
        self.first_name = first_name
        self.title = title


def test_detect_raidar_candidates_prefers_exact_username():
    candidates = detect_raidar_candidates(
        [
            FakeEntity(10, username="raidar"),
            FakeEntity(20, username="not-raidar", first_name="Raidar"),
        ]
    )

    assert [candidate.entity_id for candidate in candidates] == [10]


def test_detect_raidar_candidates_falls_back_to_display_name():
    candidates = detect_raidar_candidates([FakeEntity(20, first_name="Raidar")])

    assert candidates[0].entity_id == 20
```

- [ ] **Step 2: Run the Telegram setup tests to verify they fail**

Run: `python -m pytest tests/desktop/test_telegram_setup.py -q`
Expected: FAIL because `raidbot.desktop.telegram_setup` does not exist

- [ ] **Step 3: Write the minimal Telegram setup helpers**

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class RaidarCandidate:
    entity_id: int
    label: str


def detect_raidar_candidates(entities) -> list[RaidarCandidate]:
    exact_username = [
        RaidarCandidate(entity_id=item.id, label=_label_for_entity(item))
        for item in entities
        if (item.username or "").lower() == "raidar"
    ]
    if exact_username:
        return exact_username

    exact_name = [
        RaidarCandidate(entity_id=item.id, label=_label_for_entity(item))
        for item in entities
        if _display_name(item) == "Raidar"
    ]
    return exact_name


def _display_name(item) -> str:
    return item.title or item.first_name or ""


def _label_for_entity(item) -> str:
    username = f"@{item.username}" if getattr(item, "username", None) else _display_name(item)
    return username or str(item.id)
```

Extend the module before moving on:

- add `TelegramSetupService` with async methods:
  - `authorize(...)`
  - `list_accessible_chats()`
  - `infer_recent_sender_candidates(chat_ids)`
- make `authorize(...)` explicitly cover:
  - reuse of an existing valid session file before prompting
  - one-time phone/code/password collection through callback functions
  - interrupted-auth cleanup by replacing incomplete session files
  - no persistence of login codes or 2FA passwords
- add a `reauthorize(...)` path or equivalent explicit replacement flow used by the settings page
- expose session status that can drive the settings-page `Reauthorize` action
- test those methods with fake Telethon clients, not a real Telegram session

- [ ] **Step 4: Run the Telegram setup tests to verify they pass**

Run: `python -m pytest tests/desktop/test_telegram_setup.py -q`
Expected: PASS with the initial helper tests and the added service tests

- [ ] **Step 5: Commit Telegram setup services**

```bash
git add raidbot/desktop/telegram_setup.py tests/desktop/test_telegram_setup.py
git commit -m "feat: add desktop telegram setup services"
```

Expected: one commit containing setup-side Telegram integration

### Task 5: Add A Controllable Bot Worker And Extend Telegram Listener Stop Support

**Files:**
- Modify: `raidbot/telegram_client.py`
- Modify: `tests/test_telegram_client.py`
- Create: `raidbot/desktop/worker.py`
- Create: `tests/desktop/test_worker.py`

- [ ] **Step 1: Write the failing worker and stop-support tests**

```python
from raidbot.desktop.models import BotRuntimeState, DesktopAppConfig
from raidbot.desktop.worker import DesktopBotWorker


def test_worker_records_opened_raid_and_updates_stats():
    events = []

    class FakeListener:
        async def run_forever(self):
            return None

        async def stop(self):
            return None

    worker = DesktopBotWorker(
        config=DesktopAppConfig(
            telegram_api_id=123456,
            telegram_api_hash="hash-value",
            telegram_session_path=Path("raidbot.session"),
            telegram_phone_number="+40123456789",
            whitelisted_chat_ids=[-1001],
            raidar_sender_id=42,
            chrome_profile_directory="Profile 3",
        ),
        listener_factory=lambda *_args, **_kwargs: FakeListener(),
        emit_event=events.append,
    )

    worker._record_service_outcome("opened", "raid_opened", "https://x.com/i/status/123")

    assert worker.state.raids_opened == 1
    assert worker.state.activity[-1].action == "opened"
```

Also add a test in `tests/test_telegram_client.py`:

```python
def test_listener_stop_disconnects_client():
    ...
```

Add another worker test:

```python
def test_worker_loads_persisted_state_and_saves_updates():
    ...
```

- [ ] **Step 2: Run the worker tests to verify they fail**

Run: `python -m pytest tests/desktop/test_worker.py tests/test_telegram_client.py -q`
Expected: FAIL because `raidbot.desktop.worker` does not exist and listener stop support is missing

- [ ] **Step 3: Write the minimal worker and listener changes**

```python
# raidbot/telegram_client.py
class TelegramRaidListener:
    ...
    async def stop(self) -> None:
        await self.client.disconnect()
```

```python
# raidbot/desktop/worker.py
class DesktopBotWorker:
    def __init__(self, config, listener_factory, emit_event, storage, initial_state=None) -> None:
        self.config = config
        self.listener_factory = listener_factory
        self.emit_event = emit_event
        self.storage = storage
        self.state = initial_state or storage.load_state()

    def _record_service_outcome(self, action: str, reason: str, url: str | None) -> None:
        if action == "opened":
            self.state.raids_opened += 1
            self.state.last_successful_raid_open_at = _utc_now()
        elif reason == "duplicate":
            self.state.duplicates_skipped += 1
        elif reason == "not_a_raid":
            self.state.non_matching_skipped += 1
        elif reason == "open_failed":
            self.state.open_failures += 1
        self.state.activity.append(ActivityEntry(...))
        self.state.activity = self.state.activity[-200:]
        self.storage.save_state(self.state)
```

Refine before finalizing:

- add optional connection-state callbacks to `TelegramRaidListener`
- have worker emit `bot_state_changed`, `connection_state_changed`, `stats_changed`, `activity_added`, and `error` events
- keep Chrome-open failures as recoverable `running` events
- save app state on every meaningful stats/activity update and on clean shutdown
- support live application of whitelist / `Raidar` sender / Chrome profile changes to future messages
- support controlled reconnect for Telegram credential/session changes

- [ ] **Step 4: Run the worker tests to verify they pass**

Run: `python -m pytest tests/desktop/test_worker.py tests/test_telegram_client.py -q`
Expected: PASS for the new worker and listener tests

- [ ] **Step 5: Commit the worker boundary**

```bash
git add raidbot/telegram_client.py tests/test_telegram_client.py raidbot/desktop/worker.py tests/desktop/test_worker.py
git commit -m "feat: add controllable desktop worker runtime"
```

Expected: one commit containing stop-capable listener support and desktop worker logic

### Task 6: Add The Qt Controller And First-Run Wizard

**Files:**
- Create: `raidbot/desktop/controller.py`
- Create: `raidbot/desktop/wizard.py`
- Test: `tests/desktop/test_controller.py`
- Test: `tests/desktop/test_wizard.py`

- [ ] **Step 1: Write the failing controller and wizard tests**

```python
from PySide6.QtWidgets import QApplication

from raidbot.desktop.models import DesktopAppConfig
from raidbot.desktop.wizard import SetupWizard


def test_wizard_cannot_finish_without_required_choices(qtbot):
    wizard = SetupWizard()
    qtbot.addWidget(wizard)

    assert wizard.button(wizard.FinishButton).isEnabled() is False
```

Add a controller test:

```python
def test_controller_applies_whitelist_changes_live(qtbot):
    ...
```

Add wizard tests for:

```python
def test_chat_selection_page_filters_search_results(qtbot):
    ...


def test_raidar_page_requires_confirmation_when_candidates_are_ambiguous(qtbot):
    ...


def test_review_page_saves_config_and_can_request_start_now(qtbot):
    ...
```

- [ ] **Step 2: Run the controller and wizard tests to verify they fail**

Run: `python -m pytest tests/desktop/test_controller.py tests/desktop/test_wizard.py -q`
Expected: FAIL because controller and wizard modules do not exist

- [ ] **Step 3: Write the minimal controller and wizard**

```python
from PySide6.QtCore import QObject, Signal


class DesktopController(QObject):
    botStateChanged = Signal(str)
    connectionStateChanged = Signal(str)
    statsChanged = Signal(object)
    activityAdded = Signal(object)
    errorRaised = Signal(str)

    def start_bot(self) -> None:
        ...

    def stop_bot(self) -> None:
        ...

    def apply_config(self, config) -> None:
        ...
```

```python
from PySide6.QtWidgets import QWizard, QWizardPage


class SetupWizard(QWizard):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.addPage(WelcomePage())
        self.addPage(TelegramAuthorizationPage())
        self.addPage(ChatDiscoveryPage())
        self.addPage(RaidarSelectionPage())
        self.addPage(ChromeProfilePage())
        self.addPage(ReviewPage())
```

Refine before finalizing:

- wire the wizard pages to `TelegramSetupService` and `ChromeEnvironment`
- keep the wizard responsible for collecting validated config data only
- keep controller logic out of page widgets
- make the review page save through `DesktopStorage`
- expose a `start_now_requested` result that the bootstrap layer can honor immediately after save
- include a searchable chat list on the chat-discovery page
- preselect `Raidar` automatically when exactly one exact-match candidate is found, then require explicit confirmation on that page
- include explicit ambiguous-`Raidar` confirmation and advanced manual sender-ID fallback on the sender page

- [ ] **Step 4: Run the controller and wizard tests to verify they pass**

Run: `python -m pytest tests/desktop/test_controller.py tests/desktop/test_wizard.py -q`
Expected: PASS for the new controller and wizard tests

- [ ] **Step 5: Commit the controller and wizard**

```bash
git add raidbot/desktop/controller.py raidbot/desktop/wizard.py tests/desktop/test_controller.py tests/desktop/test_wizard.py
git commit -m "feat: add desktop controller and setup wizard"
```

Expected: one commit containing the first-run UI flow

### Task 7: Add The Main Window, Settings UI, And Tray Integration

**Files:**
- Create: `raidbot/desktop/main_window.py`
- Create: `raidbot/desktop/settings_page.py`
- Create: `raidbot/desktop/tray.py`
- Test: `tests/desktop/test_main_window.py`
- Test: `tests/desktop/test_settings_page.py`

- [ ] **Step 1: Write the failing main-window and tray tests**

```python
from raidbot.desktop.main_window import MainWindow


def test_running_window_minimizes_to_tray_on_minimize(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    window.handle_minimize_requested()

    assert window.isHidden() is True
```

Add another test covering settings edits:

```python
def test_settings_save_emits_apply_request(qtbot):
    ...
```

Add close/tray behavior tests:

```python
def test_setup_window_minimize_behaves_like_normal_window_minimize(qtbot):
    ...


def test_close_during_setup_exits_normally(qtbot):
    ...


def test_close_while_stopped_exits_normally(qtbot):
    ...


def test_close_while_running_requests_confirmation_before_exit(qtbot):
    ...


def test_tray_toggle_action_label_tracks_runtime_state(qtbot):
    ...


def test_tray_click_restores_main_window(qtbot):
    ...
```

Add a settings-page test:

```python
def test_settings_page_exposes_session_status_and_reauthorize(qtbot):
    ...
```

- [ ] **Step 2: Run the main-window tests to verify they fail**

Run: `python -m pytest tests/desktop/test_main_window.py -q`
Expected: FAIL because main window and tray modules do not exist

- [ ] **Step 3: Write the minimal main window and tray integration**

```python
from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QLabel, QPushButton


class MainWindow(QMainWindow):
    def __init__(self, controller, storage, parent=None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.storage = storage
        ...

    def handle_minimize_requested(self) -> None:
        self.hide()
```

```python
from PySide6.QtWidgets import QWidget, QFormLayout, QPushButton


class SettingsPage(QWidget):
    def __init__(self, controller, parent=None) -> None:
        super().__init__(parent)
        self.controller = controller
        ...
```

```python
from PySide6.QtWidgets import QSystemTrayIcon, QMenu


class TrayController:
    def __init__(self, window, controller, icon, parent=None) -> None:
        self.window = window
        self.tray = QSystemTrayIcon(icon, parent)
        menu = QMenu()
        menu.addAction("Show", window.showNormal)
        self.toggle_action = menu.addAction(controller.current_toggle_label())
        self.toggle_action.triggered.connect(controller.toggle_bot)
        menu.addAction("Quit", controller.shutdown_app)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._handle_activated)

    def _handle_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.Trigger:
            self.window.showNormal()
```

Refine before finalizing:

- render stats counters and recent activity from controller events
- render the current Telegram connection state in the main window status area
- render a dedicated last-error panel in the main window
- add settings controls for whitelist, `Raidar` sender, Chrome profile, and advanced Telegram credentials
- add session status and a `Reauthorize` action in settings
- implement close-event rules from the spec
- keep setup-window minimize behavior as normal window minimize instead of tray-hide
- derive tray labels and enabled actions from the shared runtime state model
- restore the main window on both tray click and `Show`
- ensure `Quit` always routes through clean worker shutdown before exiting
- keep settings responsibilities in `settings_page.py` rather than folding them into `main_window.py`

- [ ] **Step 4: Run the main-window tests to verify they pass**

Run: `python -m pytest tests/desktop/test_main_window.py tests/desktop/test_settings_page.py -q`
Expected: PASS for window behavior, settings-page, and tray-state tests

- [ ] **Step 5: Commit the desktop shell**

```bash
git add raidbot/desktop/main_window.py raidbot/desktop/settings_page.py raidbot/desktop/tray.py tests/desktop/test_main_window.py tests/desktop/test_settings_page.py
git commit -m "feat: add desktop main window settings and tray integration"
```

Expected: one commit containing the normal post-setup desktop shell and dedicated settings page

### Task 8: Add Desktop Bootstrap, Update Docs, And Verify End To End

**Files:**
- Create: `raidbot/desktop/app.py`
- Modify: `README.md`
- Test: `tests/desktop/test_app.py`

- [ ] **Step 1: Write the failing app bootstrap tests**

```python
from raidbot.desktop.app import choose_startup_view


def test_choose_startup_view_returns_wizard_for_first_run():
    assert choose_startup_view(is_first_run=True) == "wizard"


def test_choose_startup_view_returns_main_window_for_configured_app():
    assert choose_startup_view(is_first_run=False) == "main_window"
```

Add a bootstrap test:

```python
def test_main_uses_storage_first_run_check_to_choose_window(monkeypatch):
    ...
```

- [ ] **Step 2: Run the app bootstrap tests to verify they fail**

Run: `python -m pytest tests/desktop/test_app.py -q`
Expected: FAIL because `raidbot.desktop.app` does not exist

- [ ] **Step 3: Write the minimal desktop bootstrap and docs**

```python
from PySide6.QtWidgets import QApplication


def choose_startup_view(*, is_first_run: bool) -> str:
    return "wizard" if is_first_run else "main_window"


def main() -> int:
    app = QApplication([])
    storage = DesktopStorage(default_base_dir())
    startup_view = choose_startup_view(is_first_run=storage.is_first_run())
    if startup_view == "wizard":
        window = SetupWizard(...)
    else:
        window = MainWindow(...)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
```

Also update `README.md` to include:

- install command with desktop deps
- launch command `python -m raidbot.desktop.app`
- first-run wizard behavior
- note that the app performs one-time Telethon authorization inside the desktop app
- note that later Telegram session changes are handled through the desktop app `Reauthorize` flow
- note that only new incoming messages after bot start are handled
- note that the Chrome profile must already be logged into X

- [ ] **Step 4: Run the full suite and a real startup smoke path**

Run: `python -m pytest -q`
Expected: all core and desktop tests pass

Run: `python -m raidbot.desktop.app`
Expected: desktop app launches; if first run, wizard opens

If GUI launch is not verifiable in the current environment, record the real blocker instead of claiming success.

- [ ] **Step 5: Commit the desktop app entrypoint**

```bash
git add raidbot/desktop/app.py README.md tests/desktop/test_app.py
git commit -m "feat: add desktop app bootstrap"
```

Expected: one commit containing the desktop entrypoint and operator docs

## Final Verification Checklist

- [ ] `python -m pytest -q`
- [ ] `python -m raidbot.desktop.app` launches to the wizard on first run
- [ ] completing the wizard saves `%APPDATA%\RaidBot\config.json`
- [ ] relaunching after setup opens the main window instead of the wizard
- [ ] minimizing after setup hides the running app to tray
- [ ] closing during setup exits normally
- [ ] closing while stopped exits normally
- [ ] changing whitelist, `Raidar` sender, or Chrome profile in settings applies to future messages without full app restart
- [ ] Telegram reauthorization flow reconnects cleanly when credentials/session change
- [ ] Chrome-open failures show up in recent activity and increment `open_failures` without crashing the app
- [ ] stats and recent activity persist across app restarts

## Execution Notes

- Keep the UI layer thin. Telegram logic, Chrome detection, persistence, and runtime control should stay outside widget classes.
- Reuse the existing bot modules instead of forking behavior into separate desktop-only copies.
- Use `pytest-qt` for UI behavior boundaries, not pixel-perfect assertions.
- Preserve the current headless CLI path while introducing the desktop app as the primary operator experience.
