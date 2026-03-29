# UI IDEAS Hybrid Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port the `UI_IDEAS` visual shell into the live desktop app while preserving all current bot behavior, signals, and saved configuration semantics.

**Architecture:** Keep the existing controller/runtime/model wiring intact and redesign only the UI shell and page composition. Apply the new sidebar/card visual language in `theme.py`, then port each live page to the new layout while keeping the current state rendering and signal contracts unchanged.

**Tech Stack:** PySide6, Python 3, pytest, pytest-qt

---

## File Map

- Modify: `raidbot/desktop/theme.py`
  - Port the `UI_IDEAS` palette, selectors, nav styling, card styling, status variants, and shared geometry/spacing tokens.
- Modify: `raidbot/desktop/main_window.py`
  - Replace the current shell with the sidebar + stacked-page layout and rebuild the dashboard framing around cards.
- Modify: `raidbot/desktop/settings_page.py`
  - Reframe Settings into section cards while preserving existing signals and routing/profile controls.
- Modify: `raidbot/desktop/bot_actions/page.py`
  - Rebuild Bot Actions into the new card/tile layout while preserving page-ready, slot capture/test, presets, and settle-delay wiring.
- Modify: `raidbot/desktop/bot_actions/presets_dialog.py`
  - Port the split preset-list/editor layout and preserve the current save/build semantics.
- Test: `tests/desktop/test_main_window.py`
  - Cover the sidebar shell, page switching, dashboard profile cards, and preserved status surfaces.
- Test: `tests/desktop/test_settings_page.py`
  - Verify section-card structure plus existing apply/profile-management behavior.
- Test: `tests/desktop/bot_actions/test_page.py`
  - Verify page-ready controls, slot tiles, and signal emission still work.
- Test: `tests/desktop/bot_actions/test_presets_dialog.py`
  - Verify the redesigned dialog still saves presets and finish-image state correctly.

## Task 1: Port the Shared Visual System

**Files:**
- Modify: `raidbot/desktop/theme.py`
- Test: `tests/desktop/test_main_window.py`

- [ ] **Step 1: Write the failing UI-structure assertions for the new shell selectors**

Add/adjust a focused test in `tests/desktop/test_main_window.py` that expects the redesigned shell primitives to exist after the main window is built:

```python
def test_main_window_uses_sidebar_shell(qtbot) -> None:
    window = MainWindow(
        controller=FakeController(),
        storage=FakeStorage(),
        tray_controller_factory=lambda *args, **kwargs: None,
    )
    qtbot.addWidget(window)

    assert window.findChild(QWidget, "sidebar") is not None
    assert window.stack is not None
```

- [ ] **Step 2: Run the focused test to verify it fails or is incomplete**

Run: `python -m pytest -q tests\desktop\test_main_window.py -k sidebar_shell`

Expected: FAIL because the live theme/layout does not yet expose the new shell structure.

- [ ] **Step 3: Port the `UI_IDEAS` theme primitives into `raidbot/desktop/theme.py`**

Carry over the new tokens and selectors while keeping any live selectors that current widgets still rely on:

```python
WINDOW_BG = "#060c18"
SURFACE_BG = "#0a1628"
SIDEBAR_BG = "#070e1d"
ACCENT = "#4f8ef7"
SUCCESS = "#2dd4bf"
ERROR = "#f87171"

def build_application_stylesheet() -> str:
    return f"""
    QWidget#sidebar {{ background-color: {SIDEBAR_BG}; }}
    QPushButton#navButton[active="true"] {{ border-left: 3px solid {ACCENT}; }}
    QFrame#card[profileStatus="green"] {{ background-color: #0d3d37; }}
    QFrame#card[profileStatus="red"] {{ background-color: #3d0f0f; }}
    """
```

- [ ] **Step 4: Run the focused UI test again**

Run: `python -m pytest -q tests\desktop\test_main_window.py -k sidebar_shell`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/desktop/theme.py tests/desktop/test_main_window.py
git commit -m "feat: port shared UI IDEAS theme shell"
```

## Task 2: Rebuild the Main Window Shell and Dashboard

**Files:**
- Modify: `raidbot/desktop/main_window.py`
- Test: `tests/desktop/test_main_window.py`

- [ ] **Step 1: Write failing tests for sidebar navigation and dashboard card rendering**

Add focused assertions for:

- sidebar page buttons
- stacked pages for dashboard/settings/bot actions
- profile cards still rendering status and restart affordances

```python
def test_main_window_renders_sidebar_navigation(qtbot) -> None:
    window = MainWindow(
        controller=FakeController(),
        storage=FakeStorage(),
        tray_controller_factory=lambda *args, **kwargs: None,
    )
    qtbot.addWidget(window)

    assert window.sidebar is not None
    assert window.stack.count() == 3
```

- [ ] **Step 2: Run the focused test selection**

Run: `python -m pytest -q tests\desktop\test_main_window.py -k "sidebar or profile_card or dashboard"`

Expected: FAIL on shell/layout expectations before the port.

- [ ] **Step 3: Port the `UI_IDEAS` shell into `raidbot/desktop/main_window.py` while preserving live wiring**

Implement:

- `SidebarNav`
- card-based `RaidProfileCard`
- `QStackedWidget` shell
- wrapped pages in the new padded layout
- card-style dashboard builders

Keep intact:

- controller signal hookups
- tray controller creation
- config/state sync methods
- restore-from-tray behavior already fixed on local `main`
- slot-1 presets dialog wiring

Representative structure:

```python
self.sidebar = SidebarNav()
self.stack = QStackedWidget()
self.stack.addWidget(self._wrap_page(self._build_dashboard_tab()))
self.stack.addWidget(self._wrap_page(self.settings_page))
self.stack.addWidget(self._wrap_page(self.bot_actions_page))
self.sidebar.pageRequested.connect(self.stack.setCurrentIndex)
```

- [ ] **Step 4: Run the full main-window suite**

Run: `python -m pytest -q tests\desktop\test_main_window.py`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/desktop/main_window.py tests/desktop/test_main_window.py
git commit -m "feat: redesign desktop shell and dashboard"
```

## Task 3: Redesign the Settings Page Without Changing Behavior

**Files:**
- Modify: `raidbot/desktop/settings_page.py`
- Test: `tests/desktop/test_settings_page.py`

- [ ] **Step 1: Write failing tests for the section-card presentation while preserving behavior**

Add tests that still exercise:

- session section
- Telegram section
- routing section
- apply/profile-management signals

```python
def test_settings_page_renders_section_cards(qtbot) -> None:
    page = SettingsPage(
        config=build_config(),
        available_profiles=[],
        session_status="connected",
    )
    qtbot.addWidget(page)

    assert page.session_section is not None
    assert page.telegram_section is not None
    assert page.routing_section is not None
```

- [ ] **Step 2: Run the focused settings tests**

Run: `python -m pytest -q tests\desktop\test_settings_page.py -k "section or apply or raid_profile"`

Expected: FAIL or incomplete for the new section-card expectations.

- [ ] **Step 3: Port the `UI_IDEAS` settings layout into `raidbot/desktop/settings_page.py`**

Implement:

- section-card builders
- cleaner profile management row/list
- cleaner sender row presentation

Do not change:

- `applyRequested`
- `raidProfileAddRequested`
- `raidProfileRemoveRequested`
- `raidProfileMoveRequested`
- current parsing/validation semantics

Representative pattern:

```python
self.session_section, self.session_surface = self._build_section(
    title="Session",
    description="Review current Telegram session state and reauthorize if needed.",
    content_layout=session_layout,
)
```

- [ ] **Step 4: Run the full settings-page suite**

Run: `python -m pytest -q tests\desktop\test_settings_page.py`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/desktop/settings_page.py tests/desktop/test_settings_page.py
git commit -m "feat: redesign settings page cards"
```

## Task 4: Redesign the Bot Actions Page

**Files:**
- Modify: `raidbot/desktop/bot_actions/page.py`
- Test: `tests/desktop/bot_actions/test_page.py`

- [ ] **Step 1: Write failing tests for the card/tile layout while preserving signals**

Add focused checks for:

- page title/helper text
- page-ready block
- four slot tiles
- settle delay control
- existing capture/test/presets/toggle signals

```python
def test_bot_actions_page_renders_page_ready_and_four_slots(qtbot) -> None:
    page = BotActionsPage(config=build_config())
    qtbot.addWidget(page)

    assert page.page_ready_capture_button is not None
    assert len(page.slot_boxes) == 4
```

- [ ] **Step 2: Run the focused Bot Actions page tests**

Run: `python -m pytest -q tests\desktop\bot_actions\test_page.py`

Expected: FAIL on the new layout expectations before the port.

- [ ] **Step 3: Port the `UI_IDEAS` Bot Actions composition into `raidbot/desktop/bot_actions/page.py`**

Implement:

- stronger page framing
- page-ready card
- 2x2 slot tile grid
- tile headers, previews, button rows, and status framing

Preserve:

- `pageReadyCaptureRequested`
- `slotCaptureRequested`
- `slotTestRequested`
- `slotPresetsRequested`
- `slotEnabledChanged`
- `settleDelayChanged`

Representative structure:

```python
slots_group = QGroupBox("Action Slots")
slots_layout = QGridLayout(slots_group)
for index in range(4):
    box = SlotBox(index=index, slot=...)
    self.slot_boxes.append(box)
    slots_layout.addWidget(box, index // 2, index % 2)
```

- [ ] **Step 4: Run the Bot Actions page suite**

Run: `python -m pytest -q tests\desktop\bot_actions\test_page.py`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/desktop/bot_actions/page.py tests/desktop/bot_actions/test_page.py
git commit -m "feat: redesign bot actions page"
```

## Task 5: Redesign the Slot 1 Presets Dialog

**Files:**
- Modify: `raidbot/desktop/bot_actions/presets_dialog.py`
- Test: `tests/desktop/bot_actions/test_presets_dialog.py`

- [ ] **Step 1: Write failing tests for the split dialog layout while preserving save behavior**

Add checks that the dialog still:

- renders the preset list/editor split
- supports add/remove
- stores text/image changes
- returns updated slot data through `build_updated_slot()`

```python
def test_presets_dialog_builds_updated_slot_with_split_layout(qtbot) -> None:
    dialog = Slot1PresetsDialog(slot=build_slot_1())
    qtbot.addWidget(dialog)

    assert dialog.preset_list is not None
    assert dialog.preset_text_input is not None
    assert dialog.capture_finish_button is not None
```

- [ ] **Step 2: Run the presets-dialog suite**

Run: `python -m pytest -q tests\desktop\bot_actions\test_presets_dialog.py`

Expected: FAIL on the new layout expectations before the port.

- [ ] **Step 3: Port the `UI_IDEAS` split dialog into `raidbot/desktop/bot_actions/presets_dialog.py`**

Implement:

- left list + add/remove controls
- right editor column
- cleaner preset image controls
- cleaner finish image controls

Do not change:

- how preset data is stored
- `build_updated_slot()`
- image selection semantics

Representative structure:

```python
top_row = QHBoxLayout()
top_row.addLayout(list_column, 1)
top_row.addWidget(editor_widget, 2)
root_layout.addLayout(top_row)
```

- [ ] **Step 4: Re-run the presets-dialog suite**

Run: `python -m pytest -q tests\desktop\bot_actions\test_presets_dialog.py`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/desktop/bot_actions/presets_dialog.py tests/desktop/bot_actions/test_presets_dialog.py
git commit -m "feat: redesign slot 1 presets dialog"
```

## Task 6: Full Regression and Visual Smoke Check

**Files:**
- Verify: `raidbot/desktop/theme.py`
- Verify: `raidbot/desktop/main_window.py`
- Verify: `raidbot/desktop/settings_page.py`
- Verify: `raidbot/desktop/bot_actions/page.py`
- Verify: `raidbot/desktop/bot_actions/presets_dialog.py`
- Test: `tests/desktop/test_main_window.py`
- Test: `tests/desktop/test_settings_page.py`
- Test: `tests/desktop/bot_actions/test_page.py`
- Test: `tests/desktop/bot_actions/test_presets_dialog.py`

- [ ] **Step 1: Run the focused desktop UI suite**

Run:

```bash
python -m pytest -q ^
  tests\desktop\test_main_window.py ^
  tests\desktop\test_settings_page.py ^
  tests\desktop\bot_actions\test_page.py ^
  tests\desktop\bot_actions\test_presets_dialog.py
```

Expected: PASS

- [ ] **Step 2: Run the full suite**

Run: `python -m pytest -q`

Expected: PASS

- [ ] **Step 3: Manual smoke check the redesigned shell**

Run:

```bash
python -m raidbot.desktop.app
```

Verify manually:

- sidebar navigation works
- dashboard profile cards and activity feed render correctly
- settings page still saves and manages raid profiles
- bot actions page still captures/tests slots and page-ready
- slot 1 presets dialog still saves preset data

- [ ] **Step 4: Commit the integration pass**

```bash
git add raidbot/desktop/theme.py raidbot/desktop/main_window.py raidbot/desktop/settings_page.py raidbot/desktop/bot_actions/page.py raidbot/desktop/bot_actions/presets_dialog.py tests/desktop/test_main_window.py tests/desktop/test_settings_page.py tests/desktop/bot_actions/test_page.py tests/desktop/bot_actions/test_presets_dialog.py
git commit -m "feat: apply UI IDEAS hybrid redesign"
```
