from __future__ import annotations

import importlib
import time
from typing import Callable


Bounds = tuple[int, int, int, int]
Point = tuple[int, int]


def validate_click_target(bounds: Bounds, point: Point) -> bool:
    left, top, right, bottom = bounds
    x, y = point
    return left <= x < right and top <= y < bottom


class InputDriver:
    def __init__(
        self,
        *,
        set_cursor_pos: Callable[[Point], None] | None = None,
        click_left: Callable[[], None] | None = None,
        scroll_wheel: Callable[[int], None] | None = None,
        send_hotkey: Callable[[tuple[str, ...]], None] | None = None,
        wait: Callable[[float], None] = time.sleep,
    ) -> None:
        self._set_cursor_pos = set_cursor_pos or self._set_cursor_pos_win32
        self._click_left = click_left or self._click_left_win32
        self._scroll_wheel = scroll_wheel or self._scroll_wheel_win32
        self._send_hotkey = send_hotkey or self._send_hotkey_win32
        self._wait = wait

    def move_click(self, point: Point, *, delay_seconds: float = 0.5) -> None:
        self._set_cursor_pos(point)
        self._wait(delay_seconds)
        self._click_left()

    def scroll(self, amount: int) -> None:
        self._scroll_wheel(amount)

    def close_active_tab(self) -> None:
        self._send_hotkey(("ctrl", "w"))

    def _set_cursor_pos_win32(self, point: Point) -> None:
        win32api = importlib.import_module("win32api")
        win32api.SetCursorPos(point)

    def _click_left_win32(self) -> None:
        win32api = importlib.import_module("win32api")
        win32con = importlib.import_module("win32con")
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)

    def _scroll_wheel_win32(self, amount: int) -> None:
        win32api = importlib.import_module("win32api")
        win32con = importlib.import_module("win32con")
        win32api.mouse_event(win32con.MOUSEEVENTF_WHEEL, 0, 0, amount, 0)

    def _send_hotkey_win32(self, hotkey: tuple[str, ...]) -> None:
        if hotkey != ("ctrl", "w"):
            raise ValueError(f"Unsupported hotkey: {hotkey}")
        win32api = importlib.import_module("win32api")
        win32con = importlib.import_module("win32con")
        win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
        win32api.keybd_event(ord("W"), 0, 0, 0)
        win32api.keybd_event(ord("W"), 0, win32con.KEYEVENTF_KEYUP, 0)
        win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)
