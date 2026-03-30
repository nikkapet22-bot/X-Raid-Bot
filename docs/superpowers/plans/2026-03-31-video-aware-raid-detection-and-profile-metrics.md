# Video-Aware Raid Detection And Profile Metrics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Require video media for real raid detection and fix dashboard metrics so they count successful per-profile raids instead of collapsing everything by URL.

**Architecture:** Extend the Telegram message model with explicit media information, enforce the video gate in the raid service, then enrich desktop activity rows with `profile_directory` so dashboard metrics can pair per-profile automation runs accurately. Keep storage backward-compatible and avoid changing the automation runtime semantics.

**Tech Stack:** Python, Telethon, PySide6, pytest

---

## File Map

- `raidbot/models.py`
  - Shared `IncomingMessage` model for the runtime path.
- `raidbot/telegram_client.py`
  - Converts Telethon events into `IncomingMessage`.
- `raidbot/service.py`
  - Decides whether a Telegram message becomes a raid job.
- `tests/test_telegram_client.py`
  - Verifies Telethon event mapping.
- `tests/test_service.py`
  - Verifies raid detection behavior.
- `raidbot/desktop/models.py`
  - Desktop `ActivityEntry` shape.
- `raidbot/desktop/storage.py`
  - State persistence / backward-compatible activity load.
- `raidbot/desktop/worker.py`
  - Records automation activity rows with per-profile identity.
- `raidbot/desktop/main_window.py`
  - Derives dashboard metrics and raid activity chart data.
- `tests/desktop/test_storage.py`
  - Verifies state persistence compatibility.
- `tests/desktop/test_worker.py`
  - Verifies worker activity recording.
- `tests/desktop/test_main_window.py`
  - Verifies dashboard metric math and chart behavior.

### Task 1: Carry Video Presence Through Telegram Intake

**Files:**
- Modify: `raidbot/models.py`
- Modify: `raidbot/telegram_client.py`
- Test: `tests/test_telegram_client.py`

- [ ] **Step 1: Write the failing tests for message media mapping**

Add coverage for:

```python
def test_event_to_incoming_message_marks_video_posts(monkeypatch):
    ...
    event = SimpleNamespace(
        chat_id=-1001,
        sender_id=42,
        raw_text="raid text",
        video=True,
        media=object(),
    )
    message = telegram_client.event_to_incoming_message(event)
    assert message.has_video is True


def test_event_to_incoming_message_marks_non_video_posts_false(monkeypatch):
    ...
    event = SimpleNamespace(
        chat_id=-1001,
        sender_id=42,
        raw_text="raid text",
        video=False,
        media=None,
    )
    message = telegram_client.event_to_incoming_message(event)
    assert message.has_video is False
```

- [ ] **Step 2: Run the telegram client tests to verify they fail for the new field**

Run: `python -m pytest -q tests\test_telegram_client.py`

Expected: FAIL because `IncomingMessage` has no `has_video` field and/or the mapper does not populate it.

- [ ] **Step 3: Implement the minimal message-model and mapper change**

Update the shared model and mapper:

```python
@dataclass(frozen=True)
class IncomingMessage:
    chat_id: int
    sender_id: int
    text: str
    has_video: bool = False
```

In `event_to_incoming_message()`:

```python
return IncomingMessage(
    chat_id=event.chat_id,
    sender_id=event.sender_id,
    text=event.raw_text or "",
    has_video=bool(getattr(event, "video", None)),
)
```

Prefer a simple explicit video check first. Only broaden media inspection if the test fixtures or real Telethon behavior require it.

- [ ] **Step 4: Run the telegram client tests to verify they pass**

Run: `python -m pytest -q tests\test_telegram_client.py`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/models.py raidbot/telegram_client.py tests/test_telegram_client.py
git commit -m "feat: carry video flag through telegram messages"
```

### Task 2: Require Video For Real Raid Detection

**Files:**
- Modify: `raidbot/service.py`
- Test: `tests/test_service.py`

- [ ] **Step 1: Write the failing service tests for the video gate**

Add coverage for:

```python
def test_handle_message_rejects_parsed_link_without_video():
    service, dedupe_store = build_service()
    result = service.handle_message(
        IncomingMessage(
            chat_id=-1001,
            sender_id=42,
            text="Like + Repost now\n\nhttps://x.com/i/status/123",
            has_video=False,
        )
    )
    assert result.kind == "not_a_raid"
    assert dedupe_store.contains_calls == []


def test_handle_message_detects_job_when_video_is_present():
    service, _ = build_service()
    result = service.handle_message(
        IncomingMessage(
            chat_id=-1001,
            sender_id=42,
            text="Like + Repost now\n\nhttps://x.com/i/status/123",
            has_video=True,
        )
    )
    assert result.kind == "job_detected"
```

- [ ] **Step 2: Run the service tests to verify they fail**

Run: `python -m pytest -q tests\test_service.py`

Expected: FAIL because the service currently ignores `has_video`.

- [ ] **Step 3: Implement the minimal service rule**

Update `handle_message()`:

```python
raid_match = parse_raid_message(message.text)
if raid_match is None or not message.has_video:
    return RaidDetectionResult(kind="not_a_raid")
```

Keep the sender/chat checks and dedupe order unchanged.

- [ ] **Step 4: Run the service tests to verify they pass**

Run: `python -m pytest -q tests\test_service.py`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/service.py tests/test_service.py
git commit -m "feat: require video for raid detection"
```

### Task 3: Add Per-Profile Identity To Activity Entries

**Files:**
- Modify: `raidbot/desktop/models.py`
- Modify: `raidbot/desktop/storage.py`
- Test: `tests/desktop/test_storage.py`

- [ ] **Step 1: Write the failing storage tests for `profile_directory`**

Add coverage for:

```python
def test_storage_round_trips_activity_profile_directory(tmp_path):
    ...
    state = DesktopAppState(
        activity=[
            ActivityEntry(
                timestamp=datetime(2026, 3, 31, 12, 0, 0),
                action="automation_started",
                url="https://x.com/i/status/1",
                reason="automation_started",
                profile_directory="Profile 3",
            )
        ]
    )
    ...
    assert loaded.activity[0].profile_directory == "Profile 3"


def test_storage_loads_legacy_activity_without_profile_directory(tmp_path):
    ...
    assert loaded.activity[0].profile_directory is None
```

- [ ] **Step 2: Run the storage tests to verify they fail**

Run: `python -m pytest -q tests\desktop\test_storage.py`

Expected: FAIL because `ActivityEntry` does not accept or persist `profile_directory`.

- [ ] **Step 3: Implement the minimal backward-compatible model/storage changes**

Update the desktop activity model:

```python
@dataclass
class ActivityEntry:
    timestamp: datetime
    action: str
    url: str | None = None
    reason: str | None = None
    profile_directory: str | None = None
```

Update storage serialization:

```python
def _activity_to_data(self, entry: ActivityEntry) -> dict[str, Any]:
    return {
        "timestamp": entry.timestamp.isoformat(),
        "action": entry.action,
        "url": entry.url,
        "reason": entry.reason,
        "profile_directory": entry.profile_directory,
    }
```

And loading:

```python
def _activity_from_data(self, data: dict[str, Any]) -> ActivityEntry:
    return ActivityEntry(
        timestamp=datetime.fromisoformat(str(data["timestamp"])),
        action=str(data["action"]),
        url=data.get("url"),
        reason=data.get("reason"),
        profile_directory=data.get("profile_directory"),
    )
```

- [ ] **Step 4: Run the storage tests to verify they pass**

Run: `python -m pytest -q tests\desktop\test_storage.py`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/desktop/models.py raidbot/desktop/storage.py tests/desktop/test_storage.py
git commit -m "feat: persist profile identity in activity entries"
```

### Task 4: Record Per-Profile Activity In The Worker

**Files:**
- Modify: `raidbot/desktop/worker.py`
- Test: `tests/desktop/test_worker.py`

- [ ] **Step 1: Write the failing worker tests for per-profile activity**

Add coverage for successful and failed automation activity rows:

```python
def test_worker_records_profile_directory_on_automation_activity(...):
    ...
    actions = [entry for entry in worker.state.activity if entry.action in {
        "automation_started",
        "automation_succeeded",
        "automation_failed",
        "session_closed",
    }]
    assert {entry.profile_directory for entry in actions} == {"Profile 3"}
```

Include one success-path assertion and one failure-path assertion.

- [ ] **Step 2: Run the worker tests to verify they fail**

Run: `python -m pytest -q tests\desktop\test_worker.py -k "profile_directory or automation_started"`

Expected: FAIL because activity rows do not include the profile directory.

- [ ] **Step 3: Implement the minimal worker recording change**

Pass `profile.profile_directory` into `_record_activity()` for:

- `automation_started`
- `automation_succeeded`
- `automation_failed`
- `session_closed`

Do not broaden this to unrelated actions like `raid_detected`.

- [ ] **Step 4: Run the worker tests to verify they pass**

Run: `python -m pytest -q tests\desktop\test_worker.py -k "profile_directory or automation_started"`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/desktop/worker.py tests/desktop/test_worker.py
git commit -m "feat: tag automation activity with profile directory"
```

### Task 5: Rewrite Dashboard Metrics To Use Successful Profile Runs

**Files:**
- Modify: `raidbot/desktop/main_window.py`
- Test: `tests/desktop/test_main_window.py`

- [ ] **Step 1: Write the failing dashboard tests for multi-profile metric math**

Add/replace coverage for:

```python
def test_main_window_counts_multi_profile_successes_in_raids_per_hour(qtbot):
    base_time = datetime.now().replace(second=0, microsecond=0)
    state = DesktopAppState(
        activity=[
            ActivityEntry(
                timestamp=base_time - timedelta(minutes=10),
                action="automation_started",
                url="https://x.com/i/status/500",
                reason="automation_started",
                profile_directory="George",
            ),
            ActivityEntry(
                timestamp=base_time - timedelta(minutes=10) + timedelta(seconds=3),
                action="automation_succeeded",
                url="https://x.com/i/status/500",
                reason="automation_succeeded",
                profile_directory="George",
            ),
            ...
        ]
    )
    ...
    assert window.average_raids_per_hour_label.text() == "4.0/hr"
    assert window.avg_raid_completion_time_label.text() == "3s"
```

Also add a chart test that verifies multiple successful profiles on one URL contribute multiple hourly bucket units.

- [ ] **Step 2: Run the main window tests to verify they fail**

Run: `python -m pytest -q tests\desktop\test_main_window.py -k "automation_activity_for_dashboard_metrics or raids_per_hour or raid_activity_series"`

Expected: FAIL because the dashboard still collapses by URL.

- [ ] **Step 3: Implement minimal per-profile run aggregation**

Refactor the metric helpers in `main_window.py` to:

- gather successful runs by `(url, profile_directory)`
- pair each `automation_started` with the matching `automation_succeeded`
- ignore incomplete pairs
- compute:
  - completion durations from per-profile pairs
  - successful profile completions per hour from success timestamps
  - average raids per hour from successful profile completion count over 24h

Preferred helper shape:

```python
def _collect_recent_profile_runs(entries: list[ActivityEntry]) -> list[tuple[datetime, datetime]]:
    ...

def _count_recent_successful_profile_runs(entries: list[ActivityEntry]) -> int:
    ...
```

Keep success-rate formatting untouched unless a test proves a direct dependency.

- [ ] **Step 4: Run the main window tests to verify they pass**

Run: `python -m pytest -q tests\desktop\test_main_window.py -k "automation_activity_for_dashboard_metrics or raids_per_hour or raid_activity_series"`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/desktop/main_window.py tests/desktop/test_main_window.py
git commit -m "feat: derive dashboard metrics from profile raid runs"
```

### Task 6: Final Regression Pass

**Files:**
- Modify: none
- Test: `tests/test_telegram_client.py`
- Test: `tests/test_service.py`
- Test: `tests/desktop/test_storage.py`
- Test: `tests/desktop/test_worker.py`
- Test: `tests/desktop/test_main_window.py`

- [ ] **Step 1: Run the focused regression suite**

Run:

```bash
python -m pytest -q tests\test_telegram_client.py tests\test_service.py tests\desktop\test_storage.py tests\desktop\test_worker.py tests\desktop\test_main_window.py
```

Expected: PASS

- [ ] **Step 2: Run the full suite**

Run:

```bash
python -m pytest -q
```

Expected: PASS

- [ ] **Step 3: Commit the final integrated change**

```bash
git add raidbot/models.py raidbot/telegram_client.py raidbot/service.py raidbot/desktop/models.py raidbot/desktop/storage.py raidbot/desktop/worker.py raidbot/desktop/main_window.py tests/test_telegram_client.py tests/test_service.py tests/desktop/test_storage.py tests/desktop/test_worker.py tests/desktop/test_main_window.py
git commit -m "feat: add video-aware raid detection and profile metrics"
```
