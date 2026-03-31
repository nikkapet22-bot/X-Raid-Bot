# Rally Guard Scan And Runtime Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Rally Guard posts open reliably by letting the parser accept scheme-less X/Twitter links and making sender scan save the same numeric sender ID that runtime actually receives.

**Architecture:** Keep the current detection pipeline intact, but fix the two mismatched boundaries. The parser will broaden accepted URL input while still normalizing to canonical `https://x.com/...` output. Telegram scan will switch from resolved entity IDs to runtime `message.sender_id` for matching, while keeping the resolved sender label for UI display.

**Tech Stack:** Python, PySide6 desktop app, Telethon, pytest

---

## File Map

- Modify: `raidbot/parser.py`
  - Relax X/Twitter URL matching to allow optional scheme while preserving canonical normalization.
- Modify: `tests/test_parser.py`
  - Add parser coverage for scheme-less X/Twitter raid links.
- Modify: `raidbot/desktop/telegram_setup.py`
  - Align scanned sender candidates with runtime sender IDs by using `message.sender_id` for candidate identity and resolved sender entity only for labels.
- Modify: `tests/desktop/test_telegram_setup.py`
  - Add coverage for scan returning runtime sender ID with a readable label when runtime and resolved entity IDs differ.

### Task 1: Accept Scheme-Less Raid Links

**Files:**
- Modify: `raidbot/parser.py`
- Test: `tests/test_parser.py`

- [ ] **Step 1: Write the failing parser tests**

Add focused cases in `tests/test_parser.py` proving these messages parse successfully:

```python
SCHEMELESS_X_MESSAGE = """
Like + Repost

x.com/i/status/1234567890123456789
"""

SCHEMELESS_TWITTER_MESSAGE = """
Reply + Bookmark

twitter.com/some_user/status/1234567890123456789
"""
```

Expected assertions:

```python
match = parse_raid_message(SCHEMELESS_X_MESSAGE)
assert match is not None
assert match.raw_url == "x.com/i/status/1234567890123456789"
assert match.normalized_url == "https://x.com/i/status/1234567890123456789"
```

- [ ] **Step 2: Run parser tests to verify failure**

Run:

```bash
python -m pytest -q tests\test_parser.py -k "schemeless or parse_raid_message"
```

Expected: the new scheme-less tests fail with `missing_status_url`.

- [ ] **Step 3: Implement the minimal parser change**

In `raidbot/parser.py`:

- update the status URL regex so `http://` / `https://` is optional
- keep path extraction identical
- keep normalization output as:

```python
normalized_url = f"https://x.com/{url_match.group('path')}"
```

Do not loosen action-marker requirements or any other filtering.

- [ ] **Step 4: Run parser tests to verify pass**

Run:

```bash
python -m pytest -q tests\test_parser.py
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/parser.py tests/test_parser.py
git commit -m "fix: accept scheme-less raid links"
```

### Task 2: Align Sender Scan With Runtime Sender IDs

**Files:**
- Modify: `raidbot/desktop/telegram_setup.py`
- Test: `tests/desktop/test_telegram_setup.py`

- [ ] **Step 1: Write the failing scan-alignment test**

Add a focused test in `tests/desktop/test_telegram_setup.py` with a fake message where:

- `message.sender_id == 5349287105`
- `await message.get_sender()` returns an entity with:
  - `id == 7022354529`
  - `username == "RallyGuard_Raid_Bot"`

Expected candidate result:

```python
assert candidates == [
    RaidarCandidate(entity_id=5349287105, label="@RallyGuard_Raid_Bot")
]
```

This pins the intended separation:

- runtime identity comes from `message.sender_id`
- label comes from the resolved sender entity

- [ ] **Step 2: Run Telegram setup tests to verify failure**

Run:

```bash
python -m pytest -q tests\desktop\test_telegram_setup.py -k "infer_recent_sender_candidates"
```

Expected: the new mismatch test fails because the implementation currently uses the resolved sender entity ID instead of the runtime sender ID.

- [ ] **Step 3: Implement the minimal scan fix**

In `raidbot/desktop/telegram_setup.py`, update `infer_recent_sender_candidates(...)` so that:

- it still resolves the sender entity with `_message_sender(message)` for label text
- but it uses `message.sender_id` as the candidate `entity_id`
- it falls back safely if `message.sender_id` is missing
- sender counting and dedupe are keyed by runtime sender ID, not resolved entity ID

Keep `detect_raidar_candidates(...)` support logic only for labels and supported-bot recognition. Do not change runtime listener behavior.

- [ ] **Step 4: Run Telegram setup tests to verify pass**

Run:

```bash
python -m pytest -q tests\desktop\test_telegram_setup.py
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add raidbot/desktop/telegram_setup.py tests/desktop/test_telegram_setup.py
git commit -m "fix: align scanned sender ids with runtime"
```

### Task 3: Run The Focused Regression Slice

**Files:**
- Uses: `tests/test_parser.py`
- Uses: `tests/desktop/test_telegram_setup.py`
- Uses: `tests/test_service.py`

- [ ] **Step 1: Run focused regression tests**

Run:

```bash
python -m pytest -q tests\test_parser.py tests\desktop\test_telegram_setup.py tests\test_service.py -k "raid or sender or status_url"
```

Expected: PASS

- [ ] **Step 2: Sanity-check no service regression from parser broadening**

Run:

```bash
python -m pytest -q tests\test_service.py
```

Expected: PASS

- [ ] **Step 3: Commit verification-only checkpoint**

```bash
git add raidbot/parser.py raidbot/desktop/telegram_setup.py tests/test_parser.py tests/desktop/test_telegram_setup.py tests/test_service.py
git commit -m "test: verify rally guard scan and parser fixes"
```

