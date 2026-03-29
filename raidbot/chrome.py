from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Any


@dataclass(frozen=True)
class OpenedRaidContext:
    normalized_url: str
    opened_at: float
    window_handle: int | None
    profile_directory: str


class ChromeOpener:
    def __init__(
        self,
        chrome_path: Path,
        user_data_dir: Path,
        profile_directory: str,
        launcher: Callable[[list[str]], Any] = subprocess.Popen,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.chrome_path = chrome_path
        self.user_data_dir = user_data_dir
        self.profile_directory = profile_directory
        self.launcher = launcher
        self.clock = clock

    def open(self, url: str, *, window_handle: int | None = None) -> OpenedRaidContext:
        self.launcher(
            [
                str(self.chrome_path),
                "--new-tab",
                f"--user-data-dir={self.user_data_dir}",
                f"--profile-directory={self.profile_directory}",
                url,
            ]
        )
        return OpenedRaidContext(
            normalized_url=url,
            opened_at=self.clock(),
            window_handle=window_handle,
            profile_directory=self.profile_directory,
        )

    def open_raid_window(self, url: str) -> OpenedRaidContext:
        self.launcher(
            [
                str(self.chrome_path),
                "--new-window",
                f"--user-data-dir={self.user_data_dir}",
                f"--profile-directory={self.profile_directory}",
                url,
            ]
        )
        return OpenedRaidContext(
            normalized_url=url,
            opened_at=self.clock(),
            window_handle=None,
            profile_directory=self.profile_directory,
        )
