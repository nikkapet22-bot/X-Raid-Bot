from __future__ import annotations

import importlib
import sys


def automation_runtime_available() -> tuple[bool, str | None]:
    if sys.platform != "win32":
        return False, "Windows only"
    try:
        importlib.import_module("cv2")
        importlib.import_module("mss")
        importlib.import_module("win32gui")
    except (ModuleNotFoundError, ImportError) as exc:
        return False, str(exc)
    return True, None
