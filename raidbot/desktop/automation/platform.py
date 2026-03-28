from __future__ import annotations

import importlib
import sys


def automation_runtime_available() -> tuple[bool, str | None]:
    try:
        importlib.import_module("cv2")
        importlib.import_module("mss")
        importlib.import_module("win32gui")
    except ModuleNotFoundError as exc:
        return False, str(exc)
    if sys.platform != "win32":
        return False, "Windows only"
    return True, None

