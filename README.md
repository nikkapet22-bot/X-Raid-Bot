# X-Raid-Bot

## Desktop app

Install dependencies with:

```powershell
python -m pip install -e .[dev]
```

Launch the desktop app with:

```powershell
python -m raidbot.desktop.app
```

Or double-click `Launch RaidBot.bat` from the project folder.

If you do not want a console window at all, double-click `Launch RaidBot.vbs` instead. The batch file is still useful as a fallback because it can show a visible Python/path error.

On first run, the app opens a setup wizard that:

- performs one-time Telethon authorization inside the desktop app
- lets you pick the Telegram chats to watch
- lets you confirm the `Raidar` sender
- lets you choose the Chrome profile that should open raids

The desktop app keeps the setup wizard, live stats, and settings in one interface.

After setup, there is no in-app reauthorize flow. To re-enter setup, delete the saved desktop config file (`config.json` in the RaidBot app data folder) and restart the app.

Only new incoming raid messages received after the bot starts are handled.

The selected Chrome profile must already be logged into X.

## Automation

The desktop app also includes an `Automation` tab for Windows. It can target a Chrome window, scan that window for user-provided template images, and run a fixed ordered sequence of find, scroll, and click steps.

Automation prerequisites:

- Windows only
- install dependencies with `python -m pip install -e .[dev]`
- use a visible Chrome window
- provide template image files for each step in the sequence

Automation workflow:

1. Open the desktop app and go to `Automation`.
2. Create or edit a sequence.
3. Add the ordered steps with template path, threshold, search time, scroll attempts, click attempts, settle delay, and optional click offsets.
4. Choose `Auto select from rule` or a specific Chrome window.
5. Use `Dry run step` to verify matching without clicking.
6. Start the run when the sequence looks correct.

The automation runtime captures only the selected Chrome window, picks the highest-confidence match for each step, waits `0.5` seconds before clicking, and moves to the next step only after the UI changes. If a step cannot be found within its search and scroll budget, the run stops and the failure is shown in the activity area.

## CLI daemon

The original headless daemon is still available.

Create a `.env` file with the settings required by `raidbot.config.Settings.from_env()`, then run:

```powershell
python -m raidbot.main
```
