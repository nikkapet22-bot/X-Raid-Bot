# Dashboard And Bot Actions Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Simplify the redesigned dashboard to four whole-raid metrics, polish Recent Activity, remove visible Bot Actions timing, improve the enabled toggle, and add a clearer global Bot Actions status panel.

**Architecture:** Keep the existing redesign shell and runtime wiring, but tighten the dashboard data model and presentation. Add whole-link metrics at the worker/state layer, surface them in a smaller metric row, upgrade the activity feed rendering, and simplify the Bot Actions page without changing core automation behavior.

**Tech Stack:** PySide6, Python 3, pytest, pytest-qt

---

## File Map

- Modify: `raidbot/desktop/models.py`
  - Add whole-raid summary counters to the desktop app state.
- Modify: `raidbot/desktop/worker.py`
  - Maintain whole-link metrics and pause the bot when all profiles are red.
- Modify: `raidbot/desktop/main_window.py`
  - Replace noisy dashboard metrics with four summary cards and rebuild Recent Activity as cleaner event rows/cards.
- Modify: `raidbot/desktop/bot_actions/page.py`
  - Remove visible Timing, restyle enable control as a switch, and split the global status panel into latest status/current slot/last error fields.
- Modify: `raidbot/desktop/theme.py`
  - Add styling for smaller summary metrics, activity rows/cards, switch controls, and stronger status hierarchy.
- Test: `tests/desktop/test_worker.py`
  - Verify whole-link completed/failed logic and all-red pause behavior.
- Test: `tests/desktop/test_main_window.py`
  - Verify only the four desired metrics render and the activity feed still shows newest-first entries in the new presentation.
- Test: `tests/desktop/bot_actions/test_page.py`
  - Verify Timing is gone, slot toggles still emit, and the three-field status panel renders.

## Task 1: Add Whole-Raid Summary Counters

**Files:**
- Modify: `raidbot/desktop/models.py`
- Modify: `raidbot/desktop/worker.py`
- Test: `tests/desktop/test_worker.py`

- [ ] **Step 1: Write failing worker tests for whole-link counters and all-red pause**

Add tests that pin:

- detected/opened/completed/failed counters at the whole-link level
- mixed profile outcome counts as completed if one profile succeeds
- all profiles red causes a pause instead of pretending to process the raid

```python
def test_worker_counts_raid_completed_when_any_profile_succeeds() -> None:
    worker = build_worker(...)
    # one success, one failure for the same link
    assert worker.state.raids_completed == 1
    assert worker.state.raids_failed == 0
```

- [ ] **Step 2: Run the focused worker tests to verify they fail**

Run: `python -m pytest -q tests\desktop\test_worker.py -k "raids_completed or raids_failed or all_profiles_red"`

Expected: FAIL because the current state model does not expose the new counters or pause rule.

- [ ] **Step 3: Add the minimal state and worker logic**

Update `DesktopAppState` with the four summary counters:

```python
@dataclass
class DesktopAppState:
    raids_detected: int = 0
    raids_opened: int = 0
    raids_completed: int = 0
    raids_failed: int = 0
```

Update `DesktopBotWorker` so:

- detection increments `raids_detected`
- Chrome open increments `raids_opened`
- a raid link increments `raids_completed` if any eligible profile succeeds
- a raid link increments `raids_failed` only if no eligible profile succeeds
- if all profiles are red, the bot pauses

- [ ] **Step 4: Run the focused worker tests again**

Run: `python -m pytest -q tests\desktop\test_worker.py -k "raids_completed or raids_failed or all_profiles_red"`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/desktop/models.py raidbot/desktop/worker.py tests/desktop/test_worker.py
git commit -m "feat: add whole-raid dashboard counters"
```

## Task 2: Simplify Dashboard Metrics and Rebuild Recent Activity

**Files:**
- Modify: `raidbot/desktop/main_window.py`
- Test: `tests/desktop/test_main_window.py`

- [ ] **Step 1: Write failing dashboard tests for the new four-card summary**

Add tests that assert:

- only four summary metric cards render
- titles are exactly `Raids Detected`, `Raids Opened`, `Raids Completed`, `Raids Failed`
- old noisy metrics are no longer present

```python
def test_main_window_dashboard_shows_only_four_summary_metrics(qtbot) -> None:
    window = build_window(FakeController(), FakeStorage())
    qtbot.addWidget(window)

    titles = [card.findChild(QLabel, "metricTitle").text() for card in window.metric_cards]
    assert titles == [
        "Raids Detected",
        "Raids Opened",
        "Raids Completed",
        "Raids Failed",
    ]
```

- [ ] **Step 2: Run the focused dashboard tests**

Run: `python -m pytest -q tests\desktop\test_main_window.py -k "summary_metrics or activity"`

Expected: FAIL because the current dashboard still exposes the old metric set and raw activity list.

- [ ] **Step 3: Replace the old metric row and upgrade Recent Activity rendering**

In `raidbot/desktop/main_window.py`:

- remove the old 11-card metric set
- build four smaller cards bound to the new state labels
- replace plain text activity rows with cleaner per-item widgets or a more structured render path

Representative structure:

```python
self.metric_cards = [
    self._build_metric_card("Raids Detected", self.raids_detected_label),
    self._build_metric_card("Raids Opened", self.raids_opened_label),
    self._build_metric_card("Raids Completed", self.raids_completed_label),
    self._build_metric_card("Raids Failed", self.raids_failed_label),
]
```

- [ ] **Step 4: Run the full main-window suite**

Run: `python -m pytest -q tests\desktop\test_main_window.py`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/desktop/main_window.py tests/desktop/test_main_window.py
git commit -m "feat: simplify dashboard metrics and activity feed"
```

## Task 3: Clean Up Bot Actions

**Files:**
- Modify: `raidbot/desktop/bot_actions/page.py`
- Modify: `raidbot/desktop/theme.py`
- Test: `tests/desktop/bot_actions/test_page.py`

- [ ] **Step 1: Write failing Bot Actions page tests for the cleanup**

Add assertions for:

- no visible `Timing` group
- one big status panel with separate `Latest status`, `Current slot`, and `Last error` fields
- enabled control still exists and still emits slot toggle signals

```python
def test_bot_actions_page_uses_split_status_panel_without_timing(qtbot) -> None:
    page = BotActionsPage(config=build_config())
    qtbot.addWidget(page)

    assert not hasattr(page, "settle_delay_input") or page.findChild(QGroupBox, "timingGroup") is None
    assert page.latest_status_value_label is not None
    assert page.current_slot_value_label is not None
    assert page.last_error_value_label is not None
```

- [ ] **Step 2: Run the focused Bot Actions page suite**

Run: `python -m pytest -q tests\desktop\bot_actions\test_page.py`

Expected: FAIL because the current page still shows the Timing section and only one status label.

- [ ] **Step 3: Apply the Bot Actions cleanup**

In `raidbot/desktop/bot_actions/page.py`:

- remove the visible Timing section
- replace the single status label with three value fields
- keep the existing status APIs by routing them into those fields
- preserve capture/test/presets/toggle signal behavior

In `raidbot/desktop/theme.py`:

- restyle the checkbox indicator to look like a switch/toggle
- strengthen the status panel hierarchy

Representative status panel shape:

```python
status_layout.addRow("Latest status", self.latest_status_value_label)
status_layout.addRow("Current slot", self.current_slot_value_label)
status_layout.addRow("Last error", self.last_error_value_label)
```

- [ ] **Step 4: Re-run the Bot Actions page suite**

Run: `python -m pytest -q tests\desktop\bot_actions\test_page.py`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/desktop/bot_actions/page.py raidbot/desktop/theme.py tests/desktop/bot_actions/test_page.py
git commit -m "feat: clean up bot actions page status and controls"
```

## Task 4: Full Validation

**Files:**
- Verify: `raidbot/desktop/models.py`
- Verify: `raidbot/desktop/worker.py`
- Verify: `raidbot/desktop/main_window.py`
- Verify: `raidbot/desktop/bot_actions/page.py`
- Verify: `raidbot/desktop/theme.py`
- Test: `tests/desktop/test_worker.py`
- Test: `tests/desktop/test_main_window.py`
- Test: `tests/desktop/bot_actions/test_page.py`

- [ ] **Step 1: Run the focused cleanup suites**

Run:

```bash
python -m pytest -q ^
  tests\desktop\test_worker.py ^
  tests\desktop\test_main_window.py ^
  tests\desktop\bot_actions\test_page.py
```

Expected: PASS

- [ ] **Step 2: Run the full suite**

Run: `python -m pytest -q`

Expected: PASS

- [ ] **Step 3: Manual smoke check the redesign build**

Run:

```bash
python -m raidbot.desktop.app
```

Verify manually:

- dashboard shows only the four summary metrics
- activity feed looks cleaner and newest-first
- all-red profiles pause the bot
- Bot Actions has no visible Timing section
- Bot Actions status panel clearly shows latest status/current slot/last error
- enabled controls still feel obvious and usable

- [ ] **Step 4: Commit the integration pass**

```bash
git add raidbot/desktop/models.py raidbot/desktop/worker.py raidbot/desktop/main_window.py raidbot/desktop/bot_actions/page.py raidbot/desktop/theme.py tests/desktop/test_worker.py tests/desktop/test_main_window.py tests/desktop/bot_actions/test_page.py
git commit -m "feat: streamline dashboard and bot actions"
```
