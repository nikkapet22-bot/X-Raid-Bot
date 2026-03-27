# Raid Bot Premium Dark UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the existing PySide6 desktop app into a premium dark Windows UI with a coherent electric-blue theme across the setup wizard, dashboard, and settings pages.

**Architecture:** Keep runtime behavior unchanged and confine this work to the presentation layer. Add a shared desktop theme module, then refactor the wizard, main window, and settings page to use reusable visual sections, stronger hierarchy, and deliberate composition while preserving the existing controller, storage, and worker boundaries.

**Tech Stack:** Python 3.10+, PySide6, pytest, pytest-qt, existing `raidbot.desktop` modules

---

## Prerequisites

This workspace is not currently a git repository, so the commit checkpoints below are informational until `git init` exists.

This plan is intentionally UI-only. Do not change the bot runtime, Telegram authorization logic, tray behavior rules, or Chrome-opening logic unless a failing test proves the current presentation code is incorrectly coupled to that behavior.

## File Map

- Create: `raidbot/desktop/theme.py`
  - Shared theme tokens, global application stylesheet builder, and small reusable style helpers
- Modify: `raidbot/desktop/app.py`
  - Apply the shared desktop theme at startup
- Modify: `raidbot/desktop/wizard.py`
  - Redesign the wizard layout, page composition, welcome content, helper text, and navigation styling hooks
- Modify: `raidbot/desktop/main_window.py`
  - Recompose the dashboard into premium sections with status, metric cards, activity, and error surfaces
- Modify: `raidbot/desktop/settings_page.py`
  - Redesign the settings page into grouped premium sections while preserving emitted signals and config-building behavior
- Modify: `README.md`
  - Update usage screenshots/description copy if needed to describe the new desktop UI and setup flow
- Modify: `tests/desktop/test_app.py`
  - Add coverage proving the desktop theme is applied from startup
- Modify: `tests/desktop/test_wizard.py`
  - Add coverage for the structured welcome page and redesigned wizard content surfaces
- Modify: `tests/desktop/test_main_window.py`
  - Add coverage for the new dashboard sections and preserved minimize/tray behavior
- Modify: `tests/desktop/test_settings_page.py`
  - Add coverage for grouped sections and preserved apply/reauthorize wiring

## Implementation Notes

- Use a dark charcoal palette rather than pure black.
- Use electric blue only for primary actions, focus states, and key metrics.
- Keep the native Windows title bar; do not make the window frameless.
- Prefer object names or dynamic properties for styling over large one-off inline stylesheet strings in individual widgets.
- Reuse the current widget classes where possible instead of replacing them with custom painted widgets.
- Preserve current test coverage for:
  - first-run wizard behavior
  - settings apply behavior
  - tray minimize/restore behavior
  - startup routing

### Task 1: Add Shared Theme Infrastructure

**Files:**
- Create: `raidbot/desktop/theme.py`
- Modify: `raidbot/desktop/app.py`
- Modify: `tests/desktop/test_app.py`

- [ ] **Step 1: Write the failing theme-startup tests**

Add tests in `tests/desktop/test_app.py` that prove:

```python
from raidbot.desktop import app as app_module
from raidbot.desktop.theme import build_application_stylesheet


def test_build_application_stylesheet_contains_dark_surface_and_accent():
    stylesheet = build_application_stylesheet()

    assert "#0f1724" in stylesheet
    assert "#2f7ef7" in stylesheet
    assert "QPushButton" in stylesheet


def test_main_applies_application_stylesheet(monkeypatch):
    applied = {}

    class FakeApplication:
        def __init__(self, _argv):
            self.stylesheet = ""

        def setStyleSheet(self, stylesheet):
            applied["stylesheet"] = stylesheet

        def exec(self):
            return 0

    monkeypatch.setattr(app_module, "QApplication", FakeApplication)
    monkeypatch.setattr(app_module, "DesktopStorage", lambda _path: FakeStorage())
    monkeypatch.setattr(app_module, "default_base_dir", lambda: "ignored")
    monkeypatch.setattr(app_module, "create_startup_window", lambda **_kwargs: FakeWindow())

    assert app_module.main([]) == 0
    assert "#0f1724" in applied["stylesheet"]
```

- [ ] **Step 2: Run the app tests to verify they fail**

Run: `python -m pytest tests/desktop/test_app.py -q`

Expected: FAIL because `raidbot.desktop.theme` does not exist and startup does not apply a stylesheet

- [ ] **Step 3: Write the minimal shared theme module and startup wiring**

Create `raidbot/desktop/theme.py` with:

```python
WINDOW_BG = "#0b1220"
SURFACE_BG = "#0f1724"
ELEVATED_BG = "#131d2d"
ACCENT = "#2f7ef7"
TEXT = "#edf3ff"
MUTED = "#90a0bd"
BORDER = "#22314a"
ERROR = "#ff6b81"


def build_application_stylesheet() -> str:
    return f"""
    QWidget {{
        background-color: {WINDOW_BG};
        color: {TEXT};
    }}
    QPushButton {{
        min-height: 36px;
        border-radius: 10px;
    }}
    QPushButton[variant="primary"] {{
        background-color: {ACCENT};
        color: #ffffff;
    }}
    """
```

Update `raidbot/desktop/app.py` so `main()` calls:

```python
app.setStyleSheet(build_application_stylesheet())
```

Refine before moving on:

- keep all color and spacing tokens in `theme.py`
- add helpers for section/card object names or dynamic properties
- include styles for:
  - labels
  - line edits
  - combo boxes
  - text edits
  - list widgets
  - group boxes
  - tabs
  - wizard nav buttons

- [ ] **Step 4: Run the app tests to verify they pass**

Run: `python -m pytest tests/desktop/test_app.py -q`

Expected: PASS with the new theme assertions

- [ ] **Step 5: Commit the theme foundation**

```bash
git add raidbot/desktop/theme.py raidbot/desktop/app.py tests/desktop/test_app.py
git commit -m "feat: add premium dark desktop theme"
```

Expected: one commit containing the shared theme system and startup application

### Task 2: Redesign The Wizard Composition

**Files:**
- Modify: `raidbot/desktop/wizard.py`
- Modify: `tests/desktop/test_wizard.py`

- [ ] **Step 1: Write the failing wizard-structure tests**

Add tests in `tests/desktop/test_wizard.py` that prove the wizard now renders deliberate onboarding structure:

```python
def test_welcome_page_contains_structured_intro_content(qtbot):
    from raidbot.desktop.wizard import SetupWizard

    wizard = SetupWizard(storage=FakeStorage(), telegram_service_factory=lambda *_args: None)
    qtbot.addWidget(wizard)

    assert "Telegram access" in wizard.welcome_page.description_label.text()
    assert "Chrome profile" in wizard.welcome_page.description_label.text()
    assert "already be logged into X" in wizard.welcome_page.note_label.text()
    assert wizard.welcome_page.checklist_label.text()


def test_wizard_buttons_have_visual_variants(qtbot):
    from raidbot.desktop.wizard import SetupWizard

    wizard = SetupWizard(storage=FakeStorage(), telegram_service_factory=lambda *_args: None)
    qtbot.addWidget(wizard)
    wizard.show()

    assert wizard.button(wizard.NextButton).property("variant") == "primary"
    assert wizard.button(wizard.CancelButton).property("variant") == "quiet"
```

Add another test that the page wrappers expose styled section surfaces:

```python
def test_telegram_page_uses_named_surface_container(qtbot):
    from raidbot.desktop.wizard import SetupWizard

    wizard = SetupWizard(storage=FakeStorage(), telegram_service_factory=lambda *_args: None)
    qtbot.addWidget(wizard)

    assert wizard.telegram_page.surface.objectName() == "wizardSurface"
```

Add coverage for operator-facing page copy on data-heavy steps:

```python
def test_chat_and_review_pages_expose_guidance_copy(qtbot):
    from raidbot.desktop.wizard import SetupWizard

    wizard = SetupWizard(storage=FakeStorage(), telegram_service_factory=lambda *_args: None)
    qtbot.addWidget(wizard)

    assert "Select the chats" in wizard.chat_page.helper_label.text()
    wizard.review_page.initializePage = lambda: None
    wizard.review_page.helper_label.setText("Review your setup before saving.")
    assert "Review your setup" in wizard.review_page.helper_label.text()
```

- [ ] **Step 2: Run the wizard tests to verify they fail**

Run: `python -m pytest tests/desktop/test_wizard.py -q`

Expected: FAIL because the current wizard pages do not expose structured content or themed button properties

- [ ] **Step 3: Implement the wizard redesign**

Refactor `raidbot/desktop/wizard.py` to add:

- a small shared page-shell builder inside the module or via helper functions
- a branded wizard header inside the content region
- object names / properties used by the global theme
- structured welcome content:

```python
self.headline_label = QLabel("Set Up Raid Bot")
self.description_label = QLabel(
    "Configure Telegram access, Raidar matching, and the Chrome profile used for raids."
)
self.note_label = QLabel("Chrome should already be logged into X in the profile you select.")
self.checklist_label = QLabel(
    "What you'll configure:\n• Telegram session\n• Whitelisted chats\n• Raidar sender\n• Chrome profile"
)
```

- helper text labels for the Telegram, Raidar, and Chrome pages
- an explicit welcome-page note that the selected Chrome profile must already be logged into X
- clearer status/error labels for discovery failures
- explicit helper/empty/loading copy on the chat-discovery and review pages
- styled review summary surface
- navigation button variants:

```python
self.button(self.NextButton).setProperty("variant", "primary")
self.button(self.FinishButton).setProperty("variant", "primary")
self.button(self.BackButton).setProperty("variant", "secondary")
self.button(self.CancelButton).setProperty("variant", "quiet")
```

Refine before moving on:

- keep all current validation and authorization behavior intact
- ensure first-run minimize behavior remains unchanged
- do not move Telegram logic into visual helper widgets
- keep existing test helpers compatible where possible

- [ ] **Step 4: Run the wizard tests to verify they pass**

Run: `python -m pytest tests/desktop/test_wizard.py -q`

Expected: PASS with the new structure tests and the pre-existing functional wizard tests

- [ ] **Step 5: Commit the wizard redesign**

```bash
git add raidbot/desktop/wizard.py tests/desktop/test_wizard.py
git commit -m "feat: redesign setup wizard with premium dark layout"
```

Expected: one commit containing the premium onboarding UI changes

### Task 3: Recompose The Dashboard Into Premium Sections

**Files:**
- Modify: `raidbot/desktop/main_window.py`
- Modify: `tests/desktop/test_main_window.py`

- [ ] **Step 1: Write the failing dashboard-structure tests**

Add tests in `tests/desktop/test_main_window.py` that prove the dashboard uses deliberate sections:

```python
def test_main_window_dashboard_exposes_metric_cards_and_panels(qtbot):
    from raidbot.desktop.main_window import MainWindow

    window = MainWindow(controller=FakeController(), storage=FakeStorage())
    qtbot.addWidget(window)

    assert window.status_panel.objectName() == "statusPanel"
    assert len(window.metric_cards) == 4
    assert window.activity_panel.objectName() == "activityPanel"
    assert window.error_panel.objectName() == "errorPanel"
```

Add another test that the primary start button is themed without breaking existing signal wiring:

```python
def test_main_window_start_button_uses_primary_variant(qtbot):
    from raidbot.desktop.main_window import MainWindow

    window = MainWindow(controller=FakeController(), storage=FakeStorage())
    qtbot.addWidget(window)

    assert window.start_button.property("variant") == "primary"
```

- [ ] **Step 2: Run the main-window tests to verify they fail**

Run: `python -m pytest tests/desktop/test_main_window.py -q`

Expected: FAIL because the current dashboard is a basic form/list layout without named premium sections

- [ ] **Step 3: Implement the dashboard redesign**

Refactor `raidbot/desktop/main_window.py` so the dashboard is composed from distinct surfaces:

- top command/status row
- status panel
- metric cards row
- recent activity panel
- last-error panel

Minimal structure target:

```python
self.status_panel = self._build_status_panel()
self.metric_cards = [
    self._build_metric_card("Raids Opened", self.raids_opened_label),
    self._build_metric_card("Duplicates", self.duplicates_label),
    self._build_metric_card("Non-matching", self.non_matching_label),
    self._build_metric_card("Open Failures", self.open_failures_label),
]
self.activity_panel = self._build_activity_panel()
self.error_panel = self._build_error_panel()
```

Refine before moving on:

- keep the same labels wired to controller signals
- preserve tray/minimize/close behavior tests exactly
- keep settings tab integration intact
- use object names or dynamic properties for themed cards/panels
- add muted helper copy where empty sections would otherwise look dead

- [ ] **Step 4: Run the main-window tests to verify they pass**

Run: `python -m pytest tests/desktop/test_main_window.py -q`

Expected: PASS with both the new structure tests and the existing window/tray behavior tests

- [ ] **Step 5: Commit the dashboard redesign**

```bash
git add raidbot/desktop/main_window.py tests/desktop/test_main_window.py
git commit -m "feat: redesign desktop dashboard surfaces"
```

Expected: one commit containing the premium dashboard composition

### Task 4: Redesign The Settings Page Into Premium Groups

**Files:**
- Modify: `raidbot/desktop/settings_page.py`
- Modify: `tests/desktop/test_settings_page.py`

- [ ] **Step 1: Write the failing settings-layout tests**

Add tests in `tests/desktop/test_settings_page.py` that prove the settings page uses stronger grouping without losing behavior:

```python
def test_settings_page_uses_grouped_sections_and_primary_save(qtbot):
    from raidbot.desktop.settings_page import SettingsPage

    page = SettingsPage(
        config=build_config(),
        available_profiles=["Default", "Profile 3"],
        session_status="authorized",
    )
    qtbot.addWidget(page)

    assert page.session_section.objectName() == "settingsSection"
    assert page.telegram_section.objectName() == "settingsSection"
    assert page.routing_section.objectName() == "settingsSection"
    assert page.save_button.property("variant") == "primary"
```

Add another test for helper copy and preserved signals:

```python
def test_settings_page_preserves_apply_and_reauthorize_signals(qtbot):
    from raidbot.desktop.settings_page import SettingsPage

    apply_events = []
    reauthorize_events = []
    page = SettingsPage(
        config=build_config(),
        available_profiles=["Default", "Profile 3"],
        session_status="authorized",
    )
    qtbot.addWidget(page)
    page.applyRequested.connect(apply_events.append)
    page.reauthorizeRequested.connect(lambda: reauthorize_events.append(True))

    page.save_button.click()
    page.reauthorize_button.click()

    assert len(apply_events) == 1
    assert reauthorize_events == [True]
```

- [ ] **Step 2: Run the settings-page tests to verify they fail**

Run: `python -m pytest tests/desktop/test_settings_page.py -q`

Expected: FAIL because the current page does not expose styled sections or button variants

- [ ] **Step 3: Implement the settings-page redesign**

Refactor `raidbot/desktop/settings_page.py` to:

- keep the same fields and signal behavior
- convert the page into deliberate sections with section headings and helper labels
- make the save button primary and the reauthorize action secondary
- use object names/properties for themed sections and field hints

Minimal structure target:

```python
self.session_section = self._build_section(
    title="Session",
    description="Review current Telegram session state and reauthorize if needed.",
    content_layout=session_layout,
)
self.telegram_section = self._build_section(
    title="Telegram",
    description="Advanced API credentials used by the desktop app session.",
    content_layout=telegram_layout,
)
self.routing_section = self._build_section(
    title="Routing",
    description="Configure the chat whitelist, Raidar sender, and Chrome profile.",
    content_layout=routing_layout,
)
self.save_button.setProperty("variant", "primary")
self.reauthorize_button.setProperty("variant", "secondary")
```

Refine before moving on:

- do not break `_build_config()`
- keep profile refresh and session-status refresh methods working
- keep the page readable at typical desktop widths without needing a huge window

- [ ] **Step 4: Run the settings-page tests to verify they pass**

Run: `python -m pytest tests/desktop/test_settings_page.py -q`

Expected: PASS with the new section tests and the existing signal/config tests

- [ ] **Step 5: Commit the settings redesign**

```bash
git add raidbot/desktop/settings_page.py tests/desktop/test_settings_page.py
git commit -m "feat: redesign settings page presentation"
```

Expected: one commit containing the premium settings layout

### Task 5: Refresh Docs And Run Full Verification

**Files:**
- Modify: `README.md`
- Modify: `tests/desktop/test_app.py`
- Modify: `tests/desktop/test_wizard.py`
- Modify: `tests/desktop/test_main_window.py`
- Modify: `tests/desktop/test_settings_page.py`

- [ ] **Step 1: Write any final failing documentation/test assertions**

Add a small assertion in `tests/desktop/test_app.py` or `tests/desktop/test_launcher.py` that the README still mentions the setup wizard / desktop flow in stable wording.

Example:

```python
def test_readme_mentions_desktop_setup_wizard():
    content = Path("README.md").read_text(encoding="utf-8")
    assert "setup wizard" in content
```

- [ ] **Step 2: Run the focused desktop tests**

Run: `python -m pytest tests/desktop/test_app.py tests/desktop/test_wizard.py tests/desktop/test_main_window.py tests/desktop/test_settings_page.py -q`

Expected: PASS for the full UI redesign coverage

- [ ] **Step 3: Update docs and finalize any visual copy**

Update `README.md`:

- keep launch instructions intact
- keep the double-click launcher note intact
- mention the desktop app now provides a setup wizard, live stats, and settings in one interface

Do not add marketing copy. Keep it factual.

- [ ] **Step 4: Run the full suite and a real desktop smoke launch**

Run: `python -m pytest -q`

Expected: all tests pass

Run: `python -m raidbot.desktop.app`

Expected: the desktop app launches successfully; on first run, the wizard opens with the new dark theme

If GUI launch cannot be observed in the current environment, record the concrete blocker instead of claiming success.

- [ ] **Step 5: Commit the verified UI refresh**

```bash
git add README.md tests/desktop/test_app.py tests/desktop/test_wizard.py tests/desktop/test_main_window.py tests/desktop/test_settings_page.py
git commit -m "docs: update desktop UI documentation"
```

Expected: one commit containing any final README adjustments and test updates after full verification

## Final Verification Checklist

- [ ] `python -m pytest tests/desktop/test_app.py tests/desktop/test_wizard.py tests/desktop/test_main_window.py tests/desktop/test_settings_page.py -q`
- [ ] `python -m pytest -q`
- [ ] `python -m raidbot.desktop.app` launches successfully
- [ ] first-run wizard uses the new dark theme
- [ ] welcome page shows structured onboarding content instead of a single line
- [ ] wizard navigation buttons are visibly differentiated by role
- [ ] dashboard shows separate status, metric, activity, and error surfaces
- [ ] settings page keeps apply/reauthorize behavior after the layout redesign
- [ ] existing minimize-to-tray and close behavior still passes tests

## Execution Notes

- Keep the work visual and structural. Resist the temptation to “improve” runtime logic while touching these files.
- Prefer small reusable builders and theme hooks over large monolithic widget methods.
- If a test breaks because a widget no longer exists under the same attribute name, restore a stable public attribute unless the rename meaningfully improves the design and the plan step explicitly accounts for the test updates.
