from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import ctypes

import pytest
from PySide6.QtCore import QByteArray


def test_normalize_ctrl_hotkey_accepts_ctrl_letter() -> None:
    from raidbot.desktop.hotkeys import normalize_ctrl_hotkey

    assert normalize_ctrl_hotkey("Ctrl+P") == "Ctrl+P"


def test_normalize_ctrl_hotkey_accepts_ctrl_digit() -> None:
    from raidbot.desktop.hotkeys import normalize_ctrl_hotkey

    assert normalize_ctrl_hotkey("Ctrl+2") == "Ctrl+2"


def test_normalize_ctrl_hotkey_rejects_non_ctrl_combo() -> None:
    from raidbot.desktop.hotkeys import normalize_ctrl_hotkey

    with pytest.raises(ValueError, match="Ctrl"):
        normalize_ctrl_hotkey("Alt+P")


def test_windows_hotkey_registrar_dispatches_registered_callback() -> None:
    from raidbot.desktop.hotkeys import WindowsGlobalHotkeyRegistrar

    fired: list[bool] = []
    registrar = WindowsGlobalHotkeyRegistrar(
        register_hotkey=lambda *_args: True,
        unregister_hotkey=lambda *_args: None,
        install_native_event_filter=lambda _filter: None,
        remove_native_event_filter=lambda _filter: None,
    )
    registrar.set_hotkey("Ctrl+P", lambda: fired.append(True))

    registrar.handle_hotkey_message(registrar.hotkey_id)

    assert fired == [True]


def test_windows_hotkey_registrar_handles_qbytearray_native_event_type() -> None:
    from ctypes import wintypes

    from raidbot.desktop.hotkeys import WM_HOTKEY, WindowsGlobalHotkeyRegistrar

    fired: list[bool] = []
    registrar = WindowsGlobalHotkeyRegistrar(
        register_hotkey=lambda *_args: True,
        unregister_hotkey=lambda *_args: None,
        install_native_event_filter=lambda _filter: None,
        remove_native_event_filter=lambda _filter: None,
    )
    registrar.set_hotkey("Ctrl+2", lambda: fired.append(True))
    msg = wintypes.MSG()
    msg.message = WM_HOTKEY
    msg.wParam = registrar.hotkey_id

    handled, result = registrar.nativeEventFilter(
        QByteArray(b"windows_generic_MSG"),
        ctypes.addressof(msg),
    )

    assert handled is True
    assert result == 0
    assert fired == [True]
