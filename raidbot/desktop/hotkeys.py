from __future__ import annotations

import ctypes
from ctypes import wintypes
from typing import Callable

from PySide6.QtCore import QAbstractNativeEventFilter, Qt, Signal
from PySide6.QtWidgets import QLineEdit

WM_HOTKEY = 0x0312
MOD_CONTROL = 0x0002
MOD_NOREPEAT = 0x4000

_CTRL_PREFIX = "Ctrl+"
_FUNCTION_KEY_PREFIX = "F"
_KEY_NAME_TO_VK = {
    "SPACE": 0x20,
    "TAB": 0x09,
    "ESC": 0x1B,
    "UP": 0x26,
    "DOWN": 0x28,
    "LEFT": 0x25,
    "RIGHT": 0x27,
    "HOME": 0x24,
    "END": 0x23,
    "PAGEUP": 0x21,
    "PAGEDOWN": 0x22,
    "INSERT": 0x2D,
    "DELETE": 0x2E,
}
_QT_KEY_TO_NAME = {
    Qt.Key.Key_Space: "Space",
    Qt.Key.Key_Tab: "Tab",
    Qt.Key.Key_Escape: "Esc",
    Qt.Key.Key_Up: "Up",
    Qt.Key.Key_Down: "Down",
    Qt.Key.Key_Left: "Left",
    Qt.Key.Key_Right: "Right",
    Qt.Key.Key_Home: "Home",
    Qt.Key.Key_End: "End",
    Qt.Key.Key_PageUp: "PageUp",
    Qt.Key.Key_PageDown: "PageDown",
    Qt.Key.Key_Insert: "Insert",
    Qt.Key.Key_Delete: "Delete",
}
_CONTROL_MODIFIER = Qt.KeyboardModifier.ControlModifier
_DISALLOWED_MODIFIERS = (
    Qt.KeyboardModifier.ShiftModifier
    | Qt.KeyboardModifier.AltModifier
    | Qt.KeyboardModifier.MetaModifier
)


def normalize_ctrl_hotkey(hotkey: str | None) -> str | None:
    if hotkey is None:
        return None
    text = str(hotkey).strip()
    if not text:
        return None
    normalized = text.replace(" ", "")
    if not normalized.lower().startswith("ctrl+"):
        raise ValueError("Only Ctrl + key hotkeys are supported.")
    key_name = normalized[len(_CTRL_PREFIX) :]
    canonical_key_name = _normalize_key_name(key_name)
    if canonical_key_name is None:
        raise ValueError("Only Ctrl + key hotkeys are supported.")
    return f"{_CTRL_PREFIX}{canonical_key_name}"


def hotkey_from_qt_key_event(event) -> str:
    modifiers = event.modifiers()
    if not modifiers & _CONTROL_MODIFIER:
        raise ValueError("Only Ctrl + key hotkeys are supported.")
    if modifiers & _DISALLOWED_MODIFIERS:
        raise ValueError("Only Ctrl + key hotkeys are supported.")
    key_name = _qt_key_to_name(int(event.key()), str(event.text() or ""))
    if key_name is None:
        raise ValueError("Only Ctrl + key hotkeys are supported.")
    return f"{_CTRL_PREFIX}{key_name}"


class CtrlHotkeyCaptureField(QLineEdit):
    hotkeyChanged = Signal(object)

    def __init__(self, hotkey: str | None = None, *, parent=None) -> None:
        super().__init__(parent)
        self._hotkey = normalize_ctrl_hotkey(hotkey)
        self._capture_active = False
        self._invalid_reason: str | None = None
        self.setReadOnly(True)
        self.setPlaceholderText("Click and press Ctrl + key")
        self.setText(self._hotkey or "")

    def hotkey(self) -> str | None:
        return self._hotkey

    def invalid_reason(self) -> str | None:
        return self._invalid_reason

    def set_hotkey(self, hotkey: str | None) -> None:
        self._hotkey = normalize_ctrl_hotkey(hotkey)
        self._invalid_reason = None
        self._capture_active = False
        self.setText(self._hotkey or "")
        self.hotkeyChanged.emit(self._hotkey)

    def begin_capture(self) -> None:
        self._capture_active = True
        self._invalid_reason = None
        self.setText("Press Ctrl + key")
        self.setFocus(Qt.FocusReason.MouseFocusReason)

    def mousePressEvent(self, event) -> None:
        self.begin_capture()
        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:
        if not self._capture_active:
            super().keyPressEvent(event)
            return
        if event.key() in {
            Qt.Key.Key_Control,
            Qt.Key.Key_Shift,
            Qt.Key.Key_Alt,
            Qt.Key.Key_Meta,
        }:
            event.accept()
            return
        if event.key() in {Qt.Key.Key_Backspace, Qt.Key.Key_Delete}:
            self._hotkey = None
            self._invalid_reason = None
            self._capture_active = False
            self.clear()
            self.hotkeyChanged.emit(self._hotkey)
            event.accept()
            return
        if event.key() == Qt.Key.Key_Escape:
            self._capture_active = False
            self._invalid_reason = None
            self.setText(self._hotkey or "")
            event.accept()
            return
        try:
            self._hotkey = hotkey_from_qt_key_event(event)
        except ValueError as exc:
            self._invalid_reason = str(exc)
            self._capture_active = False
            self.setText(self._hotkey or "")
            event.accept()
            return
        self._invalid_reason = None
        self._capture_active = False
        self.setText(self._hotkey or "")
        self.hotkeyChanged.emit(self._hotkey)
        event.accept()


class WindowsGlobalHotkeyRegistrar(QAbstractNativeEventFilter):
    def __init__(
        self,
        *,
        register_hotkey: Callable[[int, int, int], bool] | None = None,
        unregister_hotkey: Callable[[int], None] | None = None,
        install_native_event_filter: Callable[[QAbstractNativeEventFilter], None] | None = None,
        remove_native_event_filter: Callable[[QAbstractNativeEventFilter], None] | None = None,
        hotkey_id: int = 0xA11CE,
    ) -> None:
        super().__init__()
        self.hotkey_id = int(hotkey_id)
        self._register_hotkey = register_hotkey or _register_hotkey_win32
        self._unregister_hotkey = unregister_hotkey or _unregister_hotkey_win32
        self._install_native_event_filter = install_native_event_filter
        self._remove_native_event_filter = remove_native_event_filter
        self._callback: Callable[[], None] | None = None
        self._current_hotkey: str | None = None
        self._installed = False
        self._install_filter()

    @property
    def current_hotkey(self) -> str | None:
        return self._current_hotkey

    def set_hotkey(self, hotkey: str | None, callback: Callable[[], None]) -> None:
        normalized = normalize_ctrl_hotkey(hotkey)
        if self._current_hotkey is not None:
            self._unregister_hotkey(self.hotkey_id)
            self._current_hotkey = None
        self._callback = callback
        if normalized is None:
            return
        virtual_key = hotkey_to_virtual_key(normalized)
        if not self._register_hotkey(self.hotkey_id, MOD_CONTROL | MOD_NOREPEAT, virtual_key):
            raise RuntimeError(f"Could not register global hotkey {normalized}")
        self._current_hotkey = normalized

    def clear_hotkey(self) -> None:
        if self._current_hotkey is None:
            return
        self._unregister_hotkey(self.hotkey_id)
        self._current_hotkey = None

    def handle_hotkey_message(self, hotkey_id: int) -> bool:
        if int(hotkey_id) != self.hotkey_id:
            return False
        if self._callback is None:
            return False
        self._callback()
        return True

    def nativeEventFilter(self, event_type, message):
        normalized_event_type = _normalize_native_event_type(event_type)
        if normalized_event_type not in {"windows_generic_MSG", "windows_dispatcher_MSG"}:
            return False, 0
        try:
            msg = wintypes.MSG.from_address(int(message))
        except (TypeError, ValueError, OSError):
            return False, 0
        if msg.message != WM_HOTKEY:
            return False, 0
        handled = self.handle_hotkey_message(int(msg.wParam))
        return handled, 0

    def close(self) -> None:
        self.clear_hotkey()
        if self._installed and self._remove_native_event_filter is not None:
            self._remove_native_event_filter(self)
            self._installed = False

    def _install_filter(self) -> None:
        if self._install_native_event_filter is None:
            return
        self._install_native_event_filter(self)
        self._installed = True


def hotkey_to_virtual_key(hotkey: str) -> int:
    normalized = normalize_ctrl_hotkey(hotkey)
    if normalized is None:
        raise ValueError("Hotkey is required.")
    key_name = normalized[len(_CTRL_PREFIX) :]
    if len(key_name) == 1 and key_name.isalpha():
        return ord(key_name.upper())
    if len(key_name) == 1 and key_name.isdigit():
        return ord(key_name)
    if key_name.upper().startswith(_FUNCTION_KEY_PREFIX):
        try:
            function_index = int(key_name[1:])
        except ValueError as exc:
            raise ValueError("Unsupported hotkey key.") from exc
        if 1 <= function_index <= 24:
            return 0x70 + (function_index - 1)
    mapped = _KEY_NAME_TO_VK.get(key_name.upper())
    if mapped is not None:
        return mapped
    raise ValueError("Unsupported hotkey key.")


def _normalize_key_name(key_name: str) -> str | None:
    normalized = str(key_name).strip()
    if len(normalized) == 1 and normalized.isalpha():
        return normalized.upper()
    if len(normalized) == 1 and normalized.isdigit():
        return normalized
    uppercase = normalized.upper()
    if uppercase.startswith(_FUNCTION_KEY_PREFIX):
        try:
            function_index = int(uppercase[1:])
        except ValueError:
            return None
        if 1 <= function_index <= 24:
            return f"F{function_index}"
        return None
    if uppercase in _KEY_NAME_TO_VK:
        return normalized[0].upper() + normalized[1:] if normalized else None
    return None


def _qt_key_to_name(key: int, text: str) -> str | None:
    if Qt.Key.Key_A <= key <= Qt.Key.Key_Z:
        return chr(key)
    if Qt.Key.Key_0 <= key <= Qt.Key.Key_9:
        return chr(key)
    if Qt.Key.Key_F1 <= key <= Qt.Key.Key_F24:
        return f"F{(key - int(Qt.Key.Key_F1)) + 1}"
    mapped = _QT_KEY_TO_NAME.get(Qt.Key(key))
    if mapped is not None:
        return mapped
    stripped_text = text.strip()
    if len(stripped_text) == 1 and stripped_text.isalnum():
        return stripped_text.upper()
    return None


def _normalize_native_event_type(event_type) -> str | None:
    if isinstance(event_type, str):
        return event_type
    if isinstance(event_type, (bytes, bytearray)):
        try:
            return bytes(event_type).decode("ascii")
        except UnicodeDecodeError:
            return None
    if hasattr(event_type, "data"):
        try:
            return bytes(event_type).decode("ascii")
        except (TypeError, ValueError, UnicodeDecodeError):
            return None
    return None


def _register_hotkey_win32(hotkey_id: int, modifiers: int, virtual_key: int) -> bool:
    user32 = ctypes.windll.user32
    return bool(user32.RegisterHotKey(None, int(hotkey_id), int(modifiers), int(virtual_key)))


def _unregister_hotkey_win32(hotkey_id: int) -> None:
    user32 = ctypes.windll.user32
    user32.UnregisterHotKey(None, int(hotkey_id))
