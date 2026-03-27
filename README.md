# raidbot

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

## CLI daemon

The original headless daemon is still available.

Create a `.env` file with the settings required by `raidbot.config.Settings.from_env()`, then run:

```powershell
python -m raidbot.main
```
