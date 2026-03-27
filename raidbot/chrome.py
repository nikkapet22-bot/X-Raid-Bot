from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable, Any


class ChromeOpener:
    def __init__(
        self,
        chrome_path: Path,
        user_data_dir: Path,
        profile_directory: str,
        launcher: Callable[[list[str]], Any] = subprocess.Popen,
    ) -> None:
        self.chrome_path = chrome_path
        self.user_data_dir = user_data_dir
        self.profile_directory = profile_directory
        self.launcher = launcher

    def open(self, url: str) -> None:
        self.launcher(
            [
                str(self.chrome_path),
                "--new-tab",
                f"--user-data-dir={self.user_data_dir}",
                f"--profile-directory={self.profile_directory}",
                url,
            ]
        )
