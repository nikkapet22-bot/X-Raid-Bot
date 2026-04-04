# Settings Raid Profile Row Height Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce the row height of the Settings -> Routing -> `Raid profiles` list by about one-third without affecting other list widgets.

**Architecture:** Scope the change to one list by giving the Settings raid-profile list its own object name, then style only that list’s item padding in the shared stylesheet. Verify through a focused stylesheet assertion so the UI density change stays isolated and intentional.

**Tech Stack:** Python, PySide6, Qt stylesheets, pytest

---

### Task 1: Tighten Settings Raid Profile List Row Padding

**Files:**
- Modify: `raidbot/desktop/settings_page.py`
- Modify: `raidbot/desktop/theme.py`
- Test: `tests/desktop/test_app.py`

- [ ] **Step 1: Write the failing stylesheet assertion**

Add a focused assertion in `tests/desktop/test_app.py` for the dedicated raid-profile list selector:

```python
assert "QListWidget#settingsRaidProfilesList::item" in stylesheet
```

Optionally assert the reduced padding block directly if the file already follows that style.

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest -q tests\desktop\test_app.py -k "build_application_stylesheet_contains_dark_surface_and_accent"`

Expected: FAIL because the dedicated selector does not exist yet.

- [ ] **Step 3: Write the minimal implementation**

In `raidbot/desktop/settings_page.py`, assign an object name to the list:

```python
self.raid_profiles_list = QListWidget()
self.raid_profiles_list.setObjectName("settingsRaidProfilesList")
```

In `raidbot/desktop/theme.py`, add a targeted selector with smaller vertical padding than the default `QListWidget::item` rule:

```python
QListWidget#settingsRaidProfilesList::item {{
    padding: 4px 10px;
}}
```

Keep the rest of the list styling unchanged.

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest -q tests\desktop\test_app.py -k "build_application_stylesheet_contains_dark_surface_and_accent"`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/desktop/test_app.py raidbot/desktop/settings_page.py raidbot/desktop/theme.py
git commit -m "fix: reduce settings raid profile row height"
```
