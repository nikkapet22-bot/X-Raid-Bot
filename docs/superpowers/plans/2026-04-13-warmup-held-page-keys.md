# Warmup Held Page Keys Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace warmup wheel scrolling with held `PageDown` / `PageUp` key navigation, with `1s` post-page-ready settle and pause-safe resume from remaining hold duration.

**Architecture:** Keep the warmup flow in the worker, but swap the movement primitive from wheel-scroll amounts to key-hold segments. The input layer gets explicit key down/up support, and the worker pause snapshot stores remaining warmup hold segments instead of wheel-scroll amounts.

**Tech Stack:** Python 3.10, PySide6 desktop app, Windows win32 input, pytest.

---

## File Map

- Modify: `raidbot/desktop/automation/input.py`
  - Add `PageDown` / `PageUp` key down/up support and a safe hold helper that can release immediately on pause.
- Modify: `raidbot/desktop/worker.py`
  - Replace warmup scroll blocks with timed key-hold segments.
  - Update warmup pause snapshots from `remaining_scroll_amounts` to remaining hold segments.
- Modify: `tests/desktop/automation/test_input.py`
  - Add coverage for held key plumbing and stop-safe key release.
- Modify: `tests/desktop/test_worker.py`
  - Replace warmup wheel-scroll expectations with held-key expectations.
  - Add warmup pause/resume coverage for interrupted key holds.
- Modify: `pyproject.toml`
  - Bump version after implementation.
- Modify: `raidbot/__init__.py`
  - Keep package version aligned.
- Modify: `tests/desktop/test_packaging.py`
  - Update versioned packaging assertions.

### Task 1: Add Held Page Key Support To The Input Layer

**Files:**
- Modify: `raidbot/desktop/automation/input.py`
- Test: `tests/desktop/automation/test_input.py`

- [ ] **Step 1: Write the failing input tests**

Add focused tests proving:
- `InputDriver` can press and release `pagedown`
- `InputDriver` can press and release `pageup`
- a held key is released if stop is requested during the hold

Example test shape:

```python
def test_input_driver_holds_pagedown_and_releases() -> None:
    events: list[tuple[str, str]] = []
    waits: list[float] = []
    driver = InputDriver(
        key_down=lambda key: events.append(("down", key)),
        key_up=lambda key: events.append(("up", key)),
        wait=waits.append,
    )

    driver.hold_key("pagedown", 5.0)

    assert events == [("down", "pagedown"), ("up", "pagedown")]
```

- [ ] **Step 2: Run the input tests to verify they fail**

Run:

```bash
python -m pytest -q tests\desktop\automation\test_input.py -k "hold_key or pagedown or pageup"
```

Expected: FAIL because held key support does not exist yet.

- [ ] **Step 3: Write the minimal input implementation**

Implement:
- `key_down` / `key_up` plumbing in `InputDriver.__init__`
- Windows keycode support for `pagedown` and `pageup`
- a `hold_key(name, seconds)` helper that:
  - raises on stop before pressing
  - presses the key
  - waits with stop checks
  - releases the key in `finally`

- [ ] **Step 4: Run the input tests to verify they pass**

Run:

```bash
python -m pytest -q tests\desktop\automation\test_input.py -k "hold_key or pagedown or pageup"
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/desktop/automation/test_input.py raidbot/desktop/automation/input.py
git commit -m "feat: add held page key warmup input support"
```

### Task 2: Replace Warmup Wheel Scroll Blocks With Held Key Segments

**Files:**
- Modify: `raidbot/desktop/worker.py`
- Test: `tests/desktop/test_worker.py`

- [ ] **Step 1: Write the failing warmup behavior tests**

Update the warmup browse test to expect:
- after each `Page Ready`, wait `1.0`
- no wheel scroll calls
- held key segments:
  - home: `pagedown 5.0`, `pageup 2.0`, `pagedown 3.0`
  - feed: `pagedown 4.0`

Add a focused pause/resume test for an interrupted warmup hold:

```python
def test_worker_resumes_warmup_from_remaining_key_hold_duration(tmp_path) -> None:
    ...
    assert paused_snapshot.profile_snapshot.remaining_hold_segments == (
        ("pagedown", 2.5),
        ("pageup", 2.0),
        ("pagedown", 3.0),
    )
```

- [ ] **Step 2: Run the warmup worker tests to verify they fail**

Run:

```bash
python -m pytest -q tests\desktop\test_worker.py -k "warmup_mode_browses_and_scrolls_instead_of_running_actions or resumes_warmup_from_remaining_key_hold_duration"
```

Expected: FAIL because worker still uses wheel-scroll amounts and the old snapshot shape.

- [ ] **Step 3: Write the minimal worker implementation**

In `raidbot/desktop/worker.py`:
- replace `remaining_scroll_amounts` in `PausedProfileRunSnapshot` with a hold-segment field such as:

```python
remaining_hold_segments: tuple[tuple[str, float], ...] = ()
```

- replace `_run_warmup_scroll_block(...)` with a hold-segment helper that:
  - waits for page ready
  - moves cursor to the page-ready anchor
  - waits `1.0`
  - executes hold segments in order
  - stores remaining segments on pause
- use exact warmup segments:

```python
home_segments = (
    ("pagedown", 5.0),
    ("pageup", 2.0),
    ("pagedown", 3.0),
)
feed_segments = (("pagedown", 4.0),)
```

- keep all existing warmup failure and graduation logic unchanged.

- [ ] **Step 4: Run the warmup worker tests to verify they pass**

Run:

```bash
python -m pytest -q tests\desktop\test_worker.py -k "warmup_mode_browses_and_scrolls_instead_of_running_actions or warmup_mode_fails_when_home_page_ready_is_missing or resumes_warmup_from_remaining_key_hold_duration"
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/desktop/test_worker.py raidbot/desktop/worker.py
git commit -m "feat: switch warmup browsing to held page keys"
```

### Task 3: Run The Affected Regression Slice

**Files:**
- Test: `tests/desktop/automation/test_input.py`
- Test: `tests/desktop/test_worker.py`

- [ ] **Step 1: Run the full affected input and warmup slice**

Run:

```bash
python -m pytest -q tests\desktop\automation\test_input.py tests\desktop\test_worker.py -k "warmup or hold_key or pagedown or pageup"
```

Expected: PASS with no failures.

- [ ] **Step 2: If anything fails, fix the smallest issue and rerun the same command**

Do not widen scope until this slice is green.

- [ ] **Step 3: Commit if any follow-up fix was needed**

```bash
git add tests/desktop/automation/test_input.py tests/desktop/test_worker.py raidbot/desktop/automation/input.py raidbot/desktop/worker.py
git commit -m "test: stabilize warmup held key regressions"
```

### Task 4: Bump Version And Verify Packaging Expectations

**Files:**
- Modify: `pyproject.toml`
- Modify: `raidbot/__init__.py`
- Modify: `tests/desktop/test_packaging.py`

- [ ] **Step 1: Write the version update**

Set the next version after `2.2.16` in:
- `pyproject.toml`
- `raidbot/__init__.py`
- packaging tests

- [ ] **Step 2: Run packaging verification**

Run:

```bash
python -m pytest -q tests\desktop\test_packaging.py
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml raidbot/__init__.py tests/desktop/test_packaging.py
git commit -m "chore: bump version for warmup held page key update"
```

### Task 5: Final Verification

**Files:**
- Test: `tests/desktop/automation/test_input.py`
- Test: `tests/desktop/test_worker.py`
- Test: `tests/desktop/test_packaging.py`

- [ ] **Step 1: Run the final verification command**

Run:

```bash
python -m pytest -q tests\desktop\automation\test_input.py tests\desktop\test_worker.py tests\desktop\test_packaging.py -k "warmup or hold_key or pagedown or pageup or packaging"
```

Expected: PASS.

- [ ] **Step 2: Record the exact passing output in the handoff**

Include:
- total passed count
- version bumped
- files changed

- [ ] **Step 3: Decide integration path**

Use `superpowers:finishing-a-development-branch` if this work is executed in an isolated branch or worktree.
