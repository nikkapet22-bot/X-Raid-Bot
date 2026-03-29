from __future__ import annotations

import importlib
import os
import time
from pathlib import Path
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
        clipboard=None,
        wait: Callable[[float], None] = time.sleep,
    ) -> None:
        self._set_cursor_pos = set_cursor_pos or self._set_cursor_pos_win32
        self._click_left = click_left or self._click_left_win32
        self._scroll_wheel = scroll_wheel or self._scroll_wheel_win32
        self._send_hotkey = send_hotkey or self._send_hotkey_win32
        self._clipboard = clipboard or _default_clipboard()
        self._wait = wait

    def move_click(self, point: Point, *, delay_seconds: float = 0.5) -> None:
        self._set_cursor_pos(point)
        self._wait(delay_seconds)
        self._click_left()

    def scroll(self, amount: int) -> None:
        self._scroll_wheel(amount)

    def close_active_tab(self) -> None:
        self._send_hotkey(("ctrl", "w"))

    def close_active_window(self) -> None:
        self._send_hotkey(("ctrl", "shift", "w"))

    def paste_text(self, text: str) -> None:
        self._clipboard.set_text(text)
        self._send_hotkey(("ctrl", "v"))

    def paste_image(self, image_path: Path) -> None:
        if not Path(image_path).exists():
            raise FileNotFoundError(str(image_path))
        self._clipboard.set_image(Path(image_path))
        self._send_hotkey(("ctrl", "v"))

    def paste_image_file(self, image_path: Path) -> None:
        if not Path(image_path).exists():
            raise FileNotFoundError(str(image_path))
        self._clipboard.set_file_image(Path(image_path))
        self._wait(1.0)
        self._send_hotkey(("ctrl", "v"))

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
        if hotkey not in {("ctrl", "w"), ("ctrl", "shift", "w"), ("ctrl", "v")}:
            raise ValueError(f"Unsupported hotkey: {hotkey}")
        win32api = importlib.import_module("win32api")
        win32con = importlib.import_module("win32con")
        win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
        if hotkey == ("ctrl", "shift", "w"):
            win32api.keybd_event(win32con.VK_SHIFT, 0, 0, 0)
        key_code = ord("W") if hotkey[-1] == "w" else ord("V")
        win32api.keybd_event(key_code, 0, 0, 0)
        win32api.keybd_event(key_code, 0, win32con.KEYEVENTF_KEYUP, 0)
        if hotkey == ("ctrl", "shift", "w"):
            win32api.keybd_event(win32con.VK_SHIFT, 0, win32con.KEYEVENTF_KEYUP, 0)
        win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)


class _QtClipboard:
    def set_text(self, text: str) -> None:
        qt_gui = importlib.import_module("PySide6.QtGui")
        clipboard = qt_gui.QGuiApplication.clipboard()
        clipboard.setText(text)

    def set_image(self, image_path: Path) -> None:
        qt_gui = importlib.import_module("PySide6.QtGui")
        image = qt_gui.QImage(str(image_path))
        if image.isNull():
            raise OSError(f"Could not load {image_path}")
        clipboard = qt_gui.QGuiApplication.clipboard()
        clipboard.setImage(image)

    def set_file_image(self, image_path: Path) -> None:
        raise NotImplementedError("File-reference image clipboard paste is Windows-only")


class _WindowsClipboard:
    def set_text(self, text: str) -> None:
        win32clipboard = importlib.import_module("win32clipboard")
        win32con = importlib.import_module("win32con")
        win32clipboard.OpenClipboard()
        try:
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, text)
        finally:
            win32clipboard.CloseClipboard()

    def set_image(self, image_path: Path) -> None:
        qt_core = importlib.import_module("PySide6.QtCore")
        qt_gui = importlib.import_module("PySide6.QtGui")
        win32clipboard = importlib.import_module("win32clipboard")
        win32con = importlib.import_module("win32con")

        image = qt_gui.QImage(str(image_path))
        if image.isNull():
            raise OSError(f"Could not load {image_path}")

        buffer = qt_core.QBuffer()
        open_mode_owner = getattr(qt_core, "QIODeviceBase", qt_core.QIODevice)
        buffer.open(open_mode_owner.OpenModeFlag.WriteOnly)
        image.save(buffer, "BMP")
        dib_bytes = bytes(buffer.data())[14:]

        win32clipboard.OpenClipboard()
        try:
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardData(win32con.CF_DIB, dib_bytes)
        finally:
            win32clipboard.CloseClipboard()

    def set_file_image(self, image_path: Path) -> None:
        _set_windows_shell_file_clipboard(Path(image_path))


def _default_clipboard():
    if os.name == "nt":
        return _WindowsClipboard()
    return _QtClipboard()


def _set_windows_shell_file_clipboard(image_path: Path) -> None:
    pythoncom = importlib.import_module("pythoncom")
    shell = importlib.import_module("win32com.shell.shell")
    folder_pidl, relative_pidl = _resolve_shell_folder_item_pidls(Path(image_path))
    data_object = shell.SHCreateDataObject(
        folder_pidl,
        [relative_pidl],
        None,
        pythoncom.IID_IDataObject,
    )
    pythoncom.OleInitialize()
    try:
        pythoncom.OleSetClipboard(data_object)
        pythoncom.OleFlushClipboard()
    finally:
        pythoncom.CoUninitialize()


def _resolve_shell_folder_item_pidls(image_path: Path) -> tuple[object, object]:
    shell = importlib.import_module("win32com.shell.shell")
    normalized_image_path = Path(image_path).resolve()
    desktop = shell.SHGetDesktopFolder()
    _eaten, folder_pidl, _attributes = desktop.ParseDisplayName(
        0,
        None,
        str(normalized_image_path.parent),
    )
    _eaten, item_pidl, _attributes = desktop.ParseDisplayName(
        0,
        None,
        str(normalized_image_path),
    )
    relative_pidl = list(item_pidl)
    while len(relative_pidl) > 1:
        relative_pidl.pop(0)
    if not relative_pidl:
        raise OSError(f"Could not resolve shell item PIDL for {normalized_image_path}")
    return folder_pidl, relative_pidl
