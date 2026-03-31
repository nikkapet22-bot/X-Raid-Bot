# Windows Beta Build Design

## Goal

Produce a shareable Windows beta bundle for `L8N Raid Bot v1.5.1` that non-technical testers can unzip and run without installing Python or using the source repository.

The distribution target is a zipped `PyInstaller onedir` folder, not a one-file executable and not an installer.

## Chosen Approach

Use `PyInstaller onedir` to package the existing desktop entrypoint into a self-contained app folder that is later zipped for distribution.

This is the best beta tradeoff because:

- it is more reliable than `onefile` for `PySide6`, `numpy`, `opencv-python-headless`, `mss`, `pywin32`, and tray/window behavior
- it is easier to smoke test and debug if a tester reports a missing runtime dependency
- it does not introduce installer complexity before the beta proves stable

## User Experience

Testers receive a zip file such as:

- `L8N-Raid-Bot-v1.5.1-beta1-win64.zip`

After unzip, they run:

- `L8N Raid Bot.exe`

They do not need:

- Python
- the source repo
- `Launch RaidBot.vbs`
- `Launch RaidBot.bat`

All config, state, and Telegram session data continue to live under:

- `%APPDATA%\RaidBot`

So every tester has their own local setup and data, separate from the unpacked app folder.

## Packaging Scope

Included in the beta package:

- desktop UI
- setup wizard
- tray behavior
- Telegram session flow
- raid automation runtime
- all required Python and Qt runtime dependencies

Not included as separate user-facing artifacts:

- test files
- docs
- source code as a required runtime dependency
- source launch helpers

## Build Inputs

The package should build from the existing desktop app entrypoint:

- `raidbot.desktop.app`

The executable should be named:

- `L8N Raid Bot.exe`

The build must bundle everything needed for runtime startup on a clean tester machine, including:

- `PySide6` Qt plugins and runtime files
- `telethon`
- `numpy`
- `opencv-python-headless`
- `mss`
- `pywin32`

If the current icon is available as a stable asset, it should be applied to the executable as part of the build.

## Build Outputs

The build should produce:

- `dist/L8N Raid Bot/`

The final shareable artifact should be:

- `dist/L8N-Raid-Bot-v1.5.1-beta1-win64.zip`

The packaged folder may also include a tiny beta readme with:

- unzip instructions
- launch instructions
- where app data is stored
- what feedback to report

## Implementation Shape

This packaging pass should stay narrow and should not modify runtime behavior.

Planned additions:

- add `PyInstaller` as a build dependency
- add one repo-local Windows build spec
- add one build script that:
  - clears old build output
  - runs the `onedir` package build
  - places any beta readme into the output folder
  - creates the final zip
- add one smoke-test script for packaged output

This pass should not change:

- app logic
- storage format
- Telegram behavior
- runtime automation behavior

## Verification Plan

Before distribution, verify the packaged output from the built folder itself.

Startup verification:

- `L8N Raid Bot.exe` launches successfully
- first-run wizard appears when app-data is clean
- configured app opens the main window when app-data already exists

Runtime verification:

- tray icon appears
- tray restore works
- quit works
- config/state/session still write to `%APPDATA%\RaidBot`

Packaging verification:

- no missing Qt platform/plugin errors
- no missing dependency import failures
- zip contains only the intended app folder contents

## Non-Goals

This beta build pass does not include:

- a Windows installer
- auto-update support
- code signing
- multi-platform packaging
- launcher-script polish for source users

