from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QIcon


def _asset_dir() -> Path:
    bundled_root = getattr(sys, "_MEIPASS", None)
    if bundled_root:
        return Path(bundled_root) / "raidbot" / "desktop" / "assets"
    return Path(__file__).resolve().with_name("assets")


def app_icon_path() -> Path:
    return _asset_dir() / "app_icon.png"


def app_icon_ico_path() -> Path:
    return _asset_dir() / "app_icon.ico"


def app_icon() -> QIcon:
    for path in (app_icon_path(), app_icon_ico_path()):
        if not path.exists():
            continue
        icon = QIcon(str(path))
        if not icon.isNull():
            return icon
    return QIcon()
