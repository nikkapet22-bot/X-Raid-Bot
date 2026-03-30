# Top Tab Shell Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the left sidebar shell with a Chrome-style top tab strip and move `Success Rate` / `Uptime` into the dashboard metric cards without changing bot behavior.

**Architecture:** Keep the existing `QStackedWidget` page model, but remove `SidebarNav` and introduce a top navigation strip that drives the same page indexes. Reuse the existing metric-calculation labels and rehost them in the dashboard metric section so only layout changes, not underlying state logic.

**Tech Stack:** PySide6, existing desktop theme system, pytest/pytest-qt

---

### Task 1: Lock the New Shell Contract in Tests

**Files:**
- Modify: `tests/desktop/test_main_window.py`
- Test: `tests/desktop/test_main_window.py`

- [ ] **Step 1: Write the failing tests for the new shell**

Add focused tests that assert:
- there is no `SidebarNav` widget in the main window
- a top tab strip exists and exposes `Dashboard`, `Settings`, `Bot Actions`
- dashboard metric titles now include `Success Rate` and `Uptime`

- [ ] **Step 2: Run the focused tests to verify they fail**

Run:

```powershell
python -m pytest -q tests\desktop\test_main_window.py -k "top_tab or sidebar or metric_cards"
```

Expected: FAIL because the current shell still uses `SidebarNav` and the metric row has only four cards.

- [ ] **Step 3: Commit the failing-test checkpoint**

```powershell
git add tests/desktop/test_main_window.py
git commit -m "test: define top tab shell contract"
```

### Task 2: Replace Sidebar Navigation With a Top Tab Strip

**Files:**
- Modify: `raidbot/desktop/main_window.py`
- Modify: `raidbot/desktop/theme.py`
- Test: `tests/desktop/test_main_window.py`

- [ ] **Step 1: Add the minimal shell implementation**

Implement a compact top navigation strip in `MainWindow` that:
- removes `SidebarNav` from the root layout
- keeps `QStackedWidget` as the page host
- adds three tab-like buttons at the top:
  - `Dashboard`
  - `Settings`
  - `Bot Actions`
- switches the same page indexes the sidebar previously controlled

- [ ] **Step 2: Style the top strip as simplified Chrome tabs**

Update `theme.py` so:
- tabs are content-sized
- the active tab reads as attached to the content surface
- inactive tabs sit darker behind it
- no icons or extra branding are shown in the tab strip

- [ ] **Step 3: Run focused shell tests**

Run:

```powershell
python -m pytest -q tests\desktop\test_main_window.py -k "top_tab or sidebar"
```

Expected: PASS

- [ ] **Step 4: Commit the shell replacement**

```powershell
git add raidbot/desktop/main_window.py raidbot/desktop/theme.py tests/desktop/test_main_window.py
git commit -m "feat: replace sidebar with top tab shell"
```

### Task 3: Move Success Rate And Uptime Into Dashboard Metrics

**Files:**
- Modify: `raidbot/desktop/main_window.py`
- Modify: `raidbot/desktop/theme.py`
- Test: `tests/desktop/test_main_window.py`

- [ ] **Step 1: Write/extend tests for six dashboard metric cards**

Make the dashboard test assert the metric titles are exactly:
- `AVG RAID COMPLETION TIME`
- `AVG RAIDS PER HOUR`
- `Raids Completed`
- `Raids Failed`
- `Success Rate`
- `Uptime`

- [ ] **Step 2: Run the focused metric test to verify the old layout fails**

Run:

```powershell
python -m pytest -q tests\desktop\test_main_window.py -k "metric_cards"
```

Expected: FAIL while the dashboard still renders only four cards and the labels live in the sidebar/footer.

- [ ] **Step 3: Rehost the existing metric labels in the dashboard row**

Update `MainWindow` so:
- the old sidebar footer metrics are removed
- `self.sidebar_success_rate_label` / `self.sidebar_uptime_label` are replaced by dashboard metric labels or renamed to neutral metric labels
- the dashboard metric row wraps cleanly on narrower widths if needed

- [ ] **Step 4: Run the focused dashboard metrics tests**

Run:

```powershell
python -m pytest -q tests\desktop\test_main_window.py -k "metric_cards or success_rate or uptime"
```

Expected: PASS

- [ ] **Step 5: Commit the metric migration**

```powershell
git add raidbot/desktop/main_window.py raidbot/desktop/theme.py tests/desktop/test_main_window.py
git commit -m "feat: move success rate and uptime into dashboard metrics"
```

### Task 4: Remove Sidebar-Only Assumptions From Remaining UI

**Files:**
- Modify: `raidbot/desktop/main_window.py`
- Modify: `tests/desktop/test_main_window.py`
- Test: `tests/desktop/test_settings_page.py`
- Test: `tests/desktop/bot_actions/test_page.py`

- [ ] **Step 1: Remove leftover sidebar-only spacing assumptions**

Clean up the page shell so:
- no empty sidebar gutter remains
- dashboard, settings, and bot actions sit under the top tabs consistently
- page titles and page padding still read correctly

- [ ] **Step 2: Verify Settings and Bot Actions still mount cleanly**

Run:

```powershell
python -m pytest -q tests\desktop\test_settings_page.py tests\desktop\bot_actions\test_page.py
```

Expected: PASS

- [ ] **Step 3: Commit the page-shell cleanup**

```powershell
git add raidbot/desktop/main_window.py tests/desktop/test_main_window.py
git commit -m "refactor: remove sidebar layout assumptions from desktop shell"
```

### Task 5: Full Verification

**Files:**
- Verify: `tests/desktop/test_main_window.py`
- Verify: `tests/desktop/test_settings_page.py`
- Verify: `tests/desktop/bot_actions/test_page.py`
- Verify: `tests/desktop/test_app.py`

- [ ] **Step 1: Run the focused desktop UI suite**

```powershell
python -m pytest -q tests\desktop\test_main_window.py tests\desktop\test_settings_page.py tests\desktop\bot_actions\test_page.py tests\desktop\test_app.py
```

Expected: PASS

- [ ] **Step 2: Run the full suite**

```powershell
python -m pytest -q
```

Expected: PASS

- [ ] **Step 3: Commit the verified final state**

```powershell
git add raidbot/desktop/main_window.py raidbot/desktop/theme.py tests/desktop/test_main_window.py tests/desktop/test_settings_page.py tests/desktop/bot_actions/test_page.py tests/desktop/test_app.py
git commit -m "feat: convert desktop app shell to top tabs"
```
