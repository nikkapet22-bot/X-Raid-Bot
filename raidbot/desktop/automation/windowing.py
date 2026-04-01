from __future__ import annotations

import importlib
import time
from dataclasses import dataclass, replace
from typing import Callable

_FOCUS_RETRY_SECONDS = 0.5
_FOCUS_RETRY_INTERVAL_SECONDS = 0.05


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


def find_existing_chrome_window(
    window_manager: "WindowManager",
    profile_directory: str | None = None,
) -> WindowInfo | None:
    if not profile_directory:
        return None
    finder = getattr(window_manager, "find_owned_chrome_window", None)
    if callable(finder):
        chosen = finder(profile_directory)
        if chosen is not None:
            return chosen
    chrome_windows = window_manager.list_chrome_windows()
    return max(chrome_windows, key=lambda window: window.last_focused_at, default=None)


def find_opened_raid_window(
    before_windows: list[WindowInfo],
    after_windows: list[WindowInfo],
) -> WindowInfo | None:
    before_by_handle = {window.handle: window for window in before_windows}
    new_handles = [
        window for window in after_windows if window.handle not in before_by_handle
    ]
    if new_handles:
        return max(new_handles, key=lambda item: item.last_focused_at, default=None)

    changed_candidates: list[WindowInfo] = []
    for window in after_windows:
        previous = before_by_handle.get(window.handle)
        if previous is None:
            continue
        if (
            window.title != previous.title
            or window.last_focused_at > previous.last_focused_at
            or window.bounds != previous.bounds
        ):
            changed_candidates.append(window)
    return max(changed_candidates, key=lambda item: item.last_focused_at, default=None)


class WindowManager:
    def __init__(
        self,
        *,
        list_windows: Callable[[], list[WindowInfo]] | None = None,
        restore_window: Callable[[int], bool] | None = None,
        focus_window: Callable[[int], bool] | None = None,
        maximize_window: Callable[[int], bool] | None = None,
        clock: Callable[[], float] = time.monotonic,
        wait: Callable[[float], None] = time.sleep,
    ) -> None:
        self._list_windows = list_windows or self._list_windows_win32
        self._restore_window = restore_window or self._restore_window_win32
        self._focus_window = focus_window or self._focus_window_win32
        self._maximize_window = maximize_window or self._maximize_window_win32
        self._clock = clock
        self._wait = wait
        self._focus_history: dict[int, float] = {}

    def list_chrome_windows(self) -> list[WindowInfo]:
        chrome_windows = [
            window for window in self._list_windows() if "chrome" in window.title.lower()
        ]
        if not chrome_windows:
            return []

        if self._uses_foreground_sentinel(chrome_windows):
            now = self._clock()
            for window in chrome_windows:
                if window.last_focused_at > 0.0:
                    self._focus_history[window.handle] = now

        return [
            replace(
                window,
                last_focused_at=max(
                    window.last_focused_at,
                    self._focus_history.get(window.handle, 0.0),
                ),
            )
            for window in chrome_windows
        ]

    def ensure_interactable_window(self, window: WindowInfo) -> WindowInteractionOutcome:
        if window.is_minimized and not self._restore_window(window.handle):
            return WindowInteractionOutcome(success=False, reason="window_not_focusable")
        deadline = self._clock() + _FOCUS_RETRY_SECONDS
        while True:
            if self._focus_window(window.handle):
                return WindowInteractionOutcome(
                    success=True,
                    window=replace(window, is_minimized=False),
                )
            if self._clock() >= deadline:
                return WindowInteractionOutcome(
                    success=False,
                    reason="window_not_focusable",
                )
            self._wait(_FOCUS_RETRY_INTERVAL_SECONDS)

    def find_owned_chrome_window(self, profile_directory: str) -> WindowInfo | None:
        _ = profile_directory
        chrome_windows = self.list_chrome_windows()
        return max(chrome_windows, key=lambda window: window.last_focused_at, default=None)

    def maximize_window(self, window: WindowInfo) -> bool:
        return self._maximize_window(window.handle)

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

    def _maximize_window_win32(self, handle: int) -> bool:
        win32con = importlib.import_module("win32con")
        win32gui = importlib.import_module("win32gui")
        try:
            win32gui.ShowWindow(handle, win32con.SW_MAXIMIZE)
        except Exception:
            return False
        return True

    def _uses_foreground_sentinel(self, windows: list[WindowInfo]) -> bool:
        if not windows:
            return False
        return all(window.last_focused_at in {0.0, 1.0} for window in windows)
