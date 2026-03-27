from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re


@dataclass(frozen=True)
class ChromeProfile:
    directory_name: str
    label: str


@dataclass(frozen=True)
class ChromeEnvironment:
    chrome_path: Path
    user_data_dir: Path
    profiles: list[ChromeProfile]


def detect_chrome_environment() -> ChromeEnvironment:
    chrome_path = _find_chrome_path()
    user_data_dir = _user_data_dir()
    local_state_path = user_data_dir / "Local State"
    if not local_state_path.exists():
        raise RuntimeError(f"Chrome Local State file not found: {local_state_path}")

    local_state = json.loads(local_state_path.read_text(encoding="utf-8"))
    info_cache = local_state.get("profile", {}).get("info_cache", {})
    profiles = [
        ChromeProfile(directory_name=directory_name, label=info_cache.get(directory_name, {}).get("name", directory_name))
        for directory_name in _profile_directory_names(user_data_dir, info_cache)
    ]
    return ChromeEnvironment(
        chrome_path=chrome_path,
        user_data_dir=user_data_dir,
        profiles=profiles,
    )


def _find_chrome_path() -> Path:
    candidates = []
    for env_name in ("PROGRAMFILES", "PROGRAMFILES(X86)"):
        root = os.environ.get(env_name)
        if root:
            candidates.append(Path(root) / "Google" / "Chrome" / "Application" / "chrome.exe")

    for candidate in candidates:
        if candidate.exists():
            return candidate

    raise RuntimeError("Chrome executable not found in standard Windows locations")


def _user_data_dir() -> Path:
    local_appdata = os.environ.get("LOCALAPPDATA")
    if not local_appdata:
        raise RuntimeError("LOCALAPPDATA is not set")
    return Path(local_appdata) / "Google" / "Chrome" / "User Data"


def _profile_directory_names(user_data_dir: Path, info_cache: dict[str, object]) -> list[str]:
    directory_names = [
        name
        for name in info_cache.keys()
        if (user_data_dir / name).exists()
    ]
    return sorted(directory_names, key=_profile_sort_key)


def _profile_sort_key(directory_name: str) -> tuple[int, int, str]:
    if directory_name == "Default":
        return (0, 0, directory_name)

    match = re.fullmatch(r"Profile (\d+)", directory_name)
    if match:
        return (1, int(match.group(1)), directory_name)

    return (2, 0, directory_name)
