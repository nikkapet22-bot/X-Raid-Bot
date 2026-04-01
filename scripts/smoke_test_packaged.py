from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from raidbot.desktop.models import DesktopAppConfig
from raidbot.desktop.storage import DesktopStorage


def _seed_configured_appdata(appdata_root: Path) -> None:
    storage = DesktopStorage(appdata_root / "RaidBot")
    storage.save_config(
        DesktopAppConfig(
            telegram_api_id=1,
            telegram_api_hash="hash",
            telegram_session_path=appdata_root / "RaidBot" / "raidbot.session",
            telegram_phone_number=None,
            whitelisted_chat_ids=[1],
            allowed_sender_ids=[1],
            chrome_profile_directory="Default",
        )
    )


def _resolve_executable(bundle_path: Path) -> Path:
    if bundle_path.is_file():
        return bundle_path
    return bundle_path / "L8N Raid Bot.exe"


def _cleanup_temp_dir(
    path: Path, retries: int = 20, delay_seconds: float = 0.25
) -> bool:
    last_error: BaseException | None = None
    for _ in range(retries):
        try:
            shutil.rmtree(path)
            return True
        except (PermissionError, NotADirectoryError, OSError) as exc:
            last_error = exc
            time.sleep(delay_seconds)
    if last_error is not None:
        print(f"warning: could not remove smoke temp dir {path}: {last_error}")
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--fresh-appdata", action="store_true")
    mode.add_argument("--configured-appdata", action="store_true")
    args = parser.parse_args()

    executable_path = _resolve_executable(Path(args.bundle).resolve())
    if not executable_path.exists():
        raise SystemExit(f"Packaged executable not found: {executable_path}")

    temp_path = Path(tempfile.mkdtemp(prefix="raidbot-packaged-smoke-"))
    try:
        appdata_path = temp_path / "AppData"
        appdata_path.mkdir(parents=True, exist_ok=True)
        if args.configured_appdata:
            _seed_configured_appdata(appdata_path)

        env = os.environ.copy()
        env["APPDATA"] = str(appdata_path)
        env["TEMP"] = str(temp_path)
        env["TMP"] = str(temp_path)

        process = subprocess.Popen(
            [str(executable_path)],
            cwd=str(executable_path.parent),
            env=env,
        )
        try:
            time.sleep(5)
            if process.poll() is not None:
                raise SystemExit(
                    f"Packaged app exited early with code {process.returncode}"
                )
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)
            time.sleep(1.0)
    finally:
        _cleanup_temp_dir(temp_path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
