from __future__ import annotations

import importlib
from dataclasses import dataclass, replace
from typing import Callable


Bounds = tuple[int, int, int, int]


@dataclass(eq=True)
class WindowInfo:
    handle: int
    title: str
    bounds: Bounds
    last_focused_at: float
    is_minimized: bool = False


@dataclass(eq=True)
class WindowInteractionOutcome:
    success: bool
    reason: str | None = None
    window: WindowInfo | None = None


def choose_window_for_rule(windows: list[WindowInfo], rule: str) -> WindowInfo | None:
    normalized_rule = rule.strip().lower()
    matches = [window for window in windows if normalized_rule in window.title.lower()]
    return max(matches, key=lambda item: item.last_focused_at, default=None)


class WindowManager:
    def __init__(
        self,
        *,
        list_windows: Callable[[], list[WindowInfo]] | None = None,
        restore_window: Callable[[int], bool] | None = None,
        focus_window: Callable[[int], bool] | None = None,
    ) -> None:
        self._list_windows = list_windows or self._list_windows_win32
        self._restore_window = restore_window or self._restore_window_win32
        self._focus_window = focus_window or self._focus_window_win32

    def list_chrome_windows(self) -> list[WindowInfo]:
        return [window for window in self._list_windows() if "chrome" in window.title.lower()]

    def ensure_interactable_window(self, window: WindowInfo) -> WindowInteractionOutcome:
        if window.is_minimized and not self._restore_window(window.handle):
            return WindowInteractionOutcome(success=False, reason="window_not_focusable")
        if not self._focus_window(window.handle):
            return WindowInteractionOutcome(success=False, reason="window_not_focusable")
        return WindowInteractionOutcome(
            success=True,
            window=replace(window, is_minimized=False),
        )

    def _list_windows_win32(self) -> list[WindowInfo]:
        win32gui = importlib.import_module("win32gui")
        foreground_handle = int(win32gui.GetForegroundWindow())
        windows: list[WindowInfo] = []

        def callback(handle, _extra) -> None:
            if not win32gui.IsWindowVisible(handle):
                return
            title = str(win32gui.GetWindowText(handle))
            if not title:
                return
            left, top, right, bottom = win32gui.GetWindowRect(handle)
            windows.append(
                WindowInfo(
                    handle=int(handle),
                    title=title,
                    bounds=(int(left), int(top), int(right), int(bottom)),
                    last_focused_at=1.0 if int(handle) == foreground_handle else 0.0,
                    is_minimized=bool(win32gui.IsIconic(handle)),
                )
            )

        win32gui.EnumWindows(callback, None)
        return windows

    def _restore_window_win32(self, handle: int) -> bool:
        win32con = importlib.import_module("win32con")
        win32gui = importlib.import_module("win32gui")
        try:
            win32gui.ShowWindow(handle, win32con.SW_RESTORE)
        except Exception:
            return False
        return not bool(win32gui.IsIconic(handle))

    def _focus_window_win32(self, handle: int) -> bool:
        win32gui = importlib.import_module("win32gui")
        try:
            win32gui.SetForegroundWindow(handle)
        except Exception:
            return False
        return int(win32gui.GetForegroundWindow()) == int(handle)
