# Wizard And Sender Beta Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the beta-reported wizard auth UX problems and the sender-resolution/save bug without changing raid runtime behavior.

**Architecture:** Keep the current wizard structure, but split Telegram auth into an explicit `Get Code` step followed by final sign-in. Add the missing sender resolver to the Telegram setup service and keep allowed sender labels visible in Settings by preserving and rendering `allowed_sender_entries`.

**Tech Stack:** Python, PySide6, Telethon, pytest, pytest-qt

---

### Task 1: Add Telegram Setup Service Coverage

**Files:**
- Modify: `raidbot/desktop/telegram_setup.py`
- Test: `tests/desktop/test_telegram_setup.py`

- [ ] **Step 1: Write the failing tests**

Add tests for:
- sending a Telegram code request without final sign-in yet
- resolving a sender entry like `@raidar` into a numeric sender ID

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest -q tests\desktop\test_telegram_setup.py -k "send_code or resolve_sender_entry"`

Expected: FAIL because the service does not yet expose those behaviors.

- [ ] **Step 3: Write minimal implementation**

Add service methods that:
- send the Telegram code request after phone validation
- resolve a sender entry to a numeric Telegram entity ID

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest -q tests\desktop\test_telegram_setup.py -k "send_code or resolve_sender_entry"`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/desktop/telegram_setup.py tests/desktop/test_telegram_setup.py
git commit -m "feat: add telegram setup code request and sender resolution"
```

### Task 2: Fix Wizard Telegram Access UX

**Files:**
- Modify: `raidbot/desktop/wizard.py`
- Test: `tests/desktop/test_wizard.py`

- [ ] **Step 1: Write the failing tests**

Add tests that pin:
- `Telegram Code` label text
- `2FA Password (optional)` guidance
- `Get Code` button presence
- wizard only attempts full sign-in after code has been requested

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest -q tests\desktop\test_wizard.py -k "get_code or telegram access or 2fa"`

Expected: FAIL because the current wizard still uses the old auth wording and direct sign-in flow.

- [ ] **Step 3: Write minimal implementation**

Update the wizard page to:
- relabel the code field to `Telegram Code`
- relabel/help the password field as optional 2FA
- add a `Get Code` button
- send the code first, then perform final sign-in on continue

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest -q tests\desktop\test_wizard.py -k "get_code or telegram access or 2fa"`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/desktop/wizard.py tests/desktop/test_wizard.py
git commit -m "feat: clarify wizard telegram code flow"
```

### Task 3: Keep Sender Labels Visible In Settings And Fix Save

**Files:**
- Modify: `raidbot/desktop/controller.py`
- Modify: `raidbot/desktop/settings_page.py`
- Test: `tests/desktop/test_controller.py`
- Test: `tests/desktop/test_settings_page.py`

- [ ] **Step 1: Write the failing tests**

Add tests that pin:
- saving Settings with sender usernames resolves without crashing
- Settings continues to render sender labels/usernames when entries already exist

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest -q tests\desktop\test_controller.py -k sender`

Run: `python -m pytest -q tests\desktop\test_settings_page.py -k sender`

Expected: FAIL or reproduce the current crash path.

- [ ] **Step 3: Write minimal implementation**

Update controller/settings behavior so:
- sender labels are preserved via `allowed_sender_entries`
- non-numeric entries resolve through the new service method
- saving no longer crashes on `resolve_sender_entry`

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest -q tests\desktop\test_controller.py -k sender`

Run: `python -m pytest -q tests\desktop\test_settings_page.py -k sender`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/desktop/controller.py raidbot/desktop/settings_page.py tests/desktop/test_controller.py tests/desktop/test_settings_page.py
git commit -m "fix: preserve sender labels and resolve settings save"
```

### Task 4: Run Focused Beta Smoke Slice

**Files:**
- Verify: `tests/desktop/test_telegram_setup.py`
- Verify: `tests/desktop/test_wizard.py`
- Verify: `tests/desktop/test_controller.py`
- Verify: `tests/desktop/test_settings_page.py`

- [ ] **Step 1: Run focused beta-fix verification**

Run:

`python -m pytest -q tests\desktop\test_telegram_setup.py tests\desktop\test_wizard.py tests\desktop\test_controller.py -k "sender or telegram or get_code or 2fa" tests\desktop\test_settings_page.py -k sender`

Expected: PASS

- [ ] **Step 2: Check the wizard manually if needed**

Verify that:
- `Get Code` is visible
- password guidance is optional/clear
- sender labels remain human-readable in Settings

- [ ] **Step 3: Commit final polish if needed**

```bash
git add raidbot/desktop/telegram_setup.py raidbot/desktop/wizard.py raidbot/desktop/controller.py raidbot/desktop/settings_page.py tests/desktop/test_telegram_setup.py tests/desktop/test_wizard.py tests/desktop/test_controller.py tests/desktop/test_settings_page.py
git commit -m "test: verify wizard and sender beta fixes"
```
