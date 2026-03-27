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
- auto-detects supported raid senders such as `Raidar` (`@raidar`) and `D.RaidBot` (`@delugeraidbot`)
- lets you confirm one or more allowed sender IDs
- lets you choose the dedicated Chrome profile that should handle raids

The desktop app keeps the setup wizard, live stats, and settings in one interface.

After setup, the bot can be edited from Settings without re-running the wizard. The desktop config now stores:

- the allowed sender allowlist
- a shared preset-reply pool
- the browser mode and executor name
- the dedicated raid browser profile

The shipped groundwork keeps `browser_mode=launch-only` and `executor_name=noop`. In that mode the app still opens matching X raid links in Chrome, records the browser-pipeline stages, and leaves the actual X action executor as a separate future module.

After setup, there is no in-app reauthorize flow. To re-enter setup, delete the saved desktop config file (`config.json` in the RaidBot app data folder) and restart the app.

Only new incoming raid messages received after the bot starts are handled.

The dedicated raid browser profile must already be logged into X.

## CLI daemon

The original headless daemon is still available.

Create a `.env` file with the settings required by `raidbot.config.Settings.from_env()`, then run:

```powershell
python -m raidbot.main
```

The current CLI config keys are:

- `TELEGRAM_API_ID`
- `TELEGRAM_API_HASH`
- `TELEGRAM_SESSION_PATH`
- `TELEGRAM_CHAT_WHITELIST`
- `ALLOWED_SENDER_IDS`
- `CHROME_PATH`
- `CHROME_USER_DATA_DIR`
- `CHROME_PROFILE_DIRECTORY`
- `BROWSER_MODE`
- `EXECUTOR_NAME`
- `PRESET_REPLIES`
- `DEFAULT_ACTION_LIKE`
- `DEFAULT_ACTION_REPOST`
- `DEFAULT_ACTION_BOOKMARK`
- `DEFAULT_ACTION_REPLY`
- `OPEN_COOLDOWN_SECONDS`
- `LOG_LEVEL`

`RAIDAR_SENDER_ID` is still accepted as a compatibility fallback when `ALLOWED_SENDER_IDS` is not set, but new setups should use the allowlist.
