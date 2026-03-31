# Windows Beta Build Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reproducible Windows `onedir` beta package for `L8N Raid Bot v1.5.1` and zip it for tester distribution.

**Architecture:** Keep runtime code unchanged and add a small packaging layer around the existing desktop entrypoint. Use a PyInstaller spec plus a repo-local build script and smoke-test script so beta packaging is reproducible and verifiable from source control.

**Tech Stack:** Python 3.10, PyInstaller, PySide6, PowerShell/Windows process launching, zip packaging

---

## File Structure

- Modify: `pyproject.toml`
  - add packaging/build dependency needed for local beta builds
- Create: `raidbot/desktop/packaging.py`
  - pure helpers for artifact names, output paths, and beta readme text so the build logic is testable
- Create: `tests/desktop/test_packaging.py`
  - focused tests for packaging helpers and script-facing behavior
- Create: `packaging/windows/L8N Raid Bot.spec`
  - PyInstaller onedir build definition for `raidbot.desktop.app`
- Create: `packaging/windows/README-beta.txt`
  - tiny bundled beta instructions copied into the packaged folder
- Create: `scripts/build_windows_beta.py`
  - deterministic build script: clean output, run PyInstaller, copy readme, zip folder
- Create: `scripts/smoke_test_packaged.py`
  - launches packaged exe against temporary app-data and verifies startup flows

## Task 1: Add Packaging Helper Module

**Files:**
- Create: `raidbot/desktop/packaging.py`
- Create: `tests/desktop/test_packaging.py`

- [ ] **Step 1: Write the failing tests for artifact naming and readme text**

```python
from raidbot.desktop.packaging import (
    beta_zip_name,
    bundled_folder_name,
    build_beta_readme,
)


def test_beta_zip_name_uses_versioned_windows_artifact():
    assert beta_zip_name("1.5.1", "beta1") == "L8N-Raid-Bot-v1.5.1-beta1-win64.zip"


def test_bundled_folder_name_matches_executable_brand():
    assert bundled_folder_name() == "L8N Raid Bot"


def test_build_beta_readme_mentions_appdata_and_exe_name():
    text = build_beta_readme(version="1.5.1", channel="beta1")
    assert "L8N Raid Bot.exe" in text
    assert "%APPDATA%\\RaidBot" in text
```

- [ ] **Step 2: Run the packaging helper tests to verify they fail**

Run: `python -m pytest -q tests\desktop\test_packaging.py -k "beta_zip_name or bundled_folder_name or build_beta_readme"`

Expected: FAIL because `raidbot.desktop.packaging` does not exist yet.

- [ ] **Step 3: Implement the minimal helper module**

```python
from __future__ import annotations


APP_BUNDLE_NAME = "L8N Raid Bot"


def bundled_folder_name() -> str:
    return APP_BUNDLE_NAME


def beta_zip_name(version: str, channel: str) -> str:
    return f"L8N-Raid-Bot-v{version}-{channel}-win64.zip"


def build_beta_readme(*, version: str, channel: str) -> str:
    return (
        f"L8N Raid Bot v{version} {channel}\\n"
        "\\n"
        "Run: L8N Raid Bot.exe\\n"
        "App data: %APPDATA%\\\\RaidBot\\n"
    )
```

- [ ] **Step 4: Run the helper tests again**

Run: `python -m pytest -q tests\desktop\test_packaging.py -k "beta_zip_name or bundled_folder_name or build_beta_readme"`

Expected: PASS

- [ ] **Step 5: Commit the helper layer**

```bash
git add raidbot/desktop/packaging.py tests/desktop/test_packaging.py
git commit -m "feat: add windows beta packaging helpers"
```

## Task 2: Add Build Dependency, Spec, and Build Script

**Files:**
- Modify: `pyproject.toml`
- Modify: `tests/desktop/test_packaging.py`
- Create: `packaging/windows/L8N Raid Bot.spec`
- Create: `scripts/build_windows_beta.py`

- [ ] **Step 1: Write the failing tests for packaging build configuration**

```python
from pathlib import Path


def test_pyproject_declares_pyinstaller_build_dependency():
    content = Path("pyproject.toml").read_text(encoding="utf-8")
    assert "pyinstaller" in content.lower()


def test_windows_spec_exists_for_l8n_raid_bot():
    spec_path = Path("packaging/windows/L8N Raid Bot.spec")
    assert spec_path.exists()


def test_build_script_references_spec_and_versioned_zip_name():
    content = Path("scripts/build_windows_beta.py").read_text(encoding="utf-8")
    assert "L8N Raid Bot.spec" in content
    assert "beta_zip_name" in content
```

- [ ] **Step 2: Run those tests to verify they fail**

Run: `python -m pytest -q tests\desktop\test_packaging.py -k "pyproject_declares_pyinstaller_build_dependency or windows_spec_exists_for_l8n_raid_bot or build_script_references_spec_and_versioned_zip_name"`

Expected: FAIL because the dependency/spec/script are not present yet.

- [ ] **Step 3: Add the dependency and build assets**

Implementation requirements:
- add `pyinstaller` to `project.optional-dependencies.dev` in `pyproject.toml`
- create `packaging/windows/L8N Raid Bot.spec` using `raidbot.desktop.app` as the entrypoint
- make the spec produce a `onedir` build named `L8N Raid Bot`
- create `scripts/build_windows_beta.py` that:
  - resolves repo root
  - deletes prior `build/` and `dist/` output
  - runs PyInstaller against the spec
  - copies the bundled beta readme into `dist/L8N Raid Bot/`
  - creates the final versioned zip in `dist/`

- [ ] **Step 4: Run the configuration tests again**

Run: `python -m pytest -q tests\desktop\test_packaging.py -k "pyproject_declares_pyinstaller_build_dependency or windows_spec_exists_for_l8n_raid_bot or build_script_references_spec_and_versioned_zip_name"`

Expected: PASS

- [ ] **Step 5: Commit the build configuration**

```bash
git add pyproject.toml packaging/windows/L8N\ Raid\ Bot.spec scripts/build_windows_beta.py tests/desktop/test_packaging.py
git commit -m "feat: add windows beta build scripts"
```

## Task 3: Add Bundled Beta Readme and Smoke Test Script

**Files:**
- Create: `packaging/windows/README-beta.txt`
- Create: `scripts/smoke_test_packaged.py`
- Modify: `tests/desktop/test_packaging.py`

- [ ] **Step 1: Write the failing tests for the smoke-test script and readme template**

```python
from pathlib import Path


def test_beta_readme_template_mentions_unzip_and_appdata():
    content = Path("packaging/windows/README-beta.txt").read_text(encoding="utf-8")
    assert "unzip" in content.lower()
    assert "%APPDATA%\\\\RaidBot" in content


def test_smoke_script_supports_fresh_and_configured_startup_modes():
    content = Path("scripts/smoke_test_packaged.py").read_text(encoding="utf-8")
    assert "--fresh-appdata" in content
    assert "--configured-appdata" in content
```

- [ ] **Step 2: Run those tests to verify they fail**

Run: `python -m pytest -q tests\desktop\test_packaging.py -k "beta_readme_template_mentions_unzip_and_appdata or smoke_script_supports_fresh_and_configured_startup_modes"`

Expected: FAIL because the readme template and smoke script do not exist yet.

- [ ] **Step 3: Implement the beta readme and smoke script**

Smoke script requirements:
- accept the packaged folder or exe path as an argument
- support a fresh temporary app-data launch to verify the wizard path
- support a configured temporary app-data launch to verify the main-window path
- wait long enough to confirm the exe stayed alive
- exit nonzero on startup failure

Readme requirements:
- say to unzip before running
- say to launch `L8N Raid Bot.exe`
- say user data lives in `%APPDATA%\\RaidBot`
- ask testers to report startup, tray, setup, and automation issues

- [ ] **Step 4: Run the smoke/readme tests again**

Run: `python -m pytest -q tests\desktop\test_packaging.py -k "beta_readme_template_mentions_unzip_and_appdata or smoke_script_supports_fresh_and_configured_startup_modes"`

Expected: PASS

- [ ] **Step 5: Commit the smoke-test assets**

```bash
git add packaging/windows/README-beta.txt scripts/smoke_test_packaged.py tests/desktop/test_packaging.py
git commit -m "feat: add beta package smoke test assets"
```

## Task 4: Produce and Verify the Windows Beta Bundle

**Files:**
- Modify: none expected
- Use: `scripts/build_windows_beta.py`
- Use: `scripts/smoke_test_packaged.py`

- [ ] **Step 1: Install build dependencies**

Run: `python -m pip install -e .[dev]`

Expected: editable install succeeds and includes `pyinstaller`

- [ ] **Step 2: Build the Windows beta bundle**

Run: `python scripts/build_windows_beta.py`

Expected:
- `dist/L8N Raid Bot/` exists
- `dist/L8N-Raid-Bot-v1.5.1-beta1-win64.zip` exists

- [ ] **Step 3: Run packaged smoke test for fresh startup**

Run: `python scripts/smoke_test_packaged.py --bundle "dist\\L8N Raid Bot" --fresh-appdata`

Expected: PASS after confirming wizard startup path

- [ ] **Step 4: Run packaged smoke test for configured startup**

Run: `python scripts/smoke_test_packaged.py --bundle "dist\\L8N Raid Bot" --configured-appdata`

Expected: PASS after confirming main-window startup path

- [ ] **Step 5: Manually inspect the packaged folder contents**

Check:
- `L8N Raid Bot.exe` exists in `dist/L8N Raid Bot/`
- bundled readme exists
- no source-only launch scripts are required for testers

- [ ] **Step 6: Commit the packaging setup**

```bash
git add pyproject.toml raidbot/desktop/packaging.py packaging/windows scripts tests/desktop/test_packaging.py
git commit -m "feat: add windows beta packaging"
```

