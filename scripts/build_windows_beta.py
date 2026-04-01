from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from raidbot.desktop.packaging import (
    APP_VERSION,
    DEFAULT_BETA_CHANNEL,
    beta_zip_name,
    bundled_folder_name,
)


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    spec_path = repo_root / "packaging" / "windows" / "L8N Raid Bot.spec"
    readme_template_path = repo_root / "packaging" / "windows" / "README-beta.txt"
    build_dir = repo_root / "build"
    dist_dir = repo_root / "dist"

    shutil.rmtree(build_dir, ignore_errors=True)
    shutil.rmtree(dist_dir, ignore_errors=True)

    subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            str(spec_path),
        ],
        cwd=repo_root,
        check=True,
    )

    bundle_dir = dist_dir / bundled_folder_name()
    shutil.copy2(readme_template_path, bundle_dir / "README-beta.txt")
    artifact_path = dist_dir / beta_zip_name(APP_VERSION, DEFAULT_BETA_CHANNEL)
    if artifact_path.exists():
        artifact_path.unlink()
    shutil.make_archive(str(artifact_path.with_suffix("")), "zip", bundle_dir)
    print(artifact_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
