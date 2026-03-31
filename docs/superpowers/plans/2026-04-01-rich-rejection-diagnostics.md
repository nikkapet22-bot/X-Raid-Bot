# Rich Rejection Diagnostics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `sender_rejected` and `not_a_raid` failures explain their exact cause so Rally Guard and other sender/detection issues can be diagnosed from normal app activity.

**Architecture:** Keep the public detection kinds unchanged, but enrich the reason text at the parser/service boundary. The parser should expose whether the message failed because it lacked action markers or lacked a status URL, and the service should combine that with the existing sender and video checks to emit precise reasons.

**Tech Stack:** Python, existing parser/service pipeline, pytest

---

## File Map

- Modify: `raidbot/parser.py`
  - Return enough parsing detail to distinguish missing action markers from missing status URL
- Modify: `raidbot/service.py`
  - Keep the same detection kinds, but enrich rejection reasons
- Test: `tests/test_service.py`
  - Add focused assertions for sender and non-raid reason text

### Task 1: Add Failing Service Tests For Rich Rejection Reasons

**Files:**
- Modify: `tests/test_service.py`

- [ ] **Step 1: Write the failing tests**

Add focused tests for:
- `sender_rejected` includes the incoming `sender_id`
- a parsed post without video returns `not_a_raid` with reason `missing_video`
- a message with action markers but no status URL returns `not_a_raid` with reason `missing_status_url`
- a message with a status URL but no action markers returns `not_a_raid` with reason `missing_action_markers`

- [ ] **Step 2: Run the focused service tests to verify they fail**

Run:

```bash
python -m pytest -q tests\test_service.py -k "sender_rejected or missing_video or missing_status_url or missing_action_markers"
```

Expected: FAIL because the service currently returns only bare rejection kinds

- [ ] **Step 3: Commit test scaffolding if useful**

```bash
git add tests/test_service.py
git commit -m "test: cover rich rejection diagnostics"
```

### Task 2: Add Parser Detail And Service Reasons

**Files:**
- Modify: `raidbot/parser.py`
- Modify: `raidbot/service.py`
- Test: `tests/test_service.py`

- [ ] **Step 1: Implement the minimal parser/service change**

In `raidbot/parser.py`:
- expose parsing detail so callers can tell:
  - no action markers
  - no status URL
  - valid raid parse

In `raidbot/service.py`:
- keep returning the same `kind` values
- set specific reasons:
  - `sender_rejected`: include incoming `sender_id`
  - `not_a_raid`: one of:
    - `missing_video`
    - `missing_status_url`
    - `missing_action_markers`

Do not change allowlist semantics or broaden media detection in this task.

- [ ] **Step 2: Run the focused service tests to verify they pass**

Run:

```bash
python -m pytest -q tests\test_service.py -k "sender_rejected or missing_video or missing_status_url or missing_action_markers"
```

Expected: PASS

- [ ] **Step 3: Run the broader service/parser slice**

Run:

```bash
python -m pytest -q tests\test_service.py tests\test_parser.py
```

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add raidbot/parser.py raidbot/service.py tests/test_service.py
git commit -m "feat: add rich rejection diagnostics"
```

### Task 3: Final Verification

**Files:**
- Verify: `tests/test_service.py`
- Verify: `tests/test_parser.py`

- [ ] **Step 1: Run the focused verification slice**

Run:

```bash
python -m pytest -q tests\test_service.py tests\test_parser.py -k "sender_rejected or not_a_raid or parse_raid_message"
```

Expected: PASS

- [ ] **Step 2: Commit final polish if needed**

```bash
git add raidbot/parser.py raidbot/service.py tests/test_service.py tests/test_parser.py
git commit -m "feat: expose exact rejection reasons"
```
