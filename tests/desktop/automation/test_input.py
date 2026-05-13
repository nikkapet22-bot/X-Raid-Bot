from __future__ import annotations

from pathlib import Path

import pytest

from raidbot.desktop.automation.input import InputDriver, InputStopRequested


class FakeClipboard:
    def __init__(self) -> None:
        self.text = None
        self.image_path = None
        self.file_image_path = None

    def set_text(self, text: str) -> None:
        self.text = text

    def set_image(self, image_path: Path) -> None:
        self.image_path = image_path

    def set_file_image(self, image_path: Path) -> None:
        self.file_image_path = image_path


class FlakyClipboard(FakeClipboard):
    def __init__(self, *, failures: int) -> None:
        super().__init__()
        self.failures_remaining = failures
        self.file_image_calls = 0

    def set_file_image(self, image_path: Path) -> None:
        self.file_image_calls += 1
        if self.failures_remaining > 0:
            self.failures_remaining -= 1
            raise RuntimeError("OpenClipboard Failed")
        super().set_file_image(image_path)


def test_input_driver_can_close_active_tab_without_affecting_click_or_scroll() -> None:
    events: list[tuple[object, ...]] = []
    driver = InputDriver(
        set_cursor_pos=lambda point: events.append(("move", point)),
        click_left=lambda: events.append(("click",)),
        scroll_wheel=lambda amount: events.append(("scroll", amount)),
        send_hotkey=events.append,
        wait=lambda _seconds: None,
    )

    driver.move_click((10, 20), delay_seconds=0.0)
    driver.scroll(-120)
    driver.close_active_tab()

    assert events == [
        ("move", (10, 20)),
        ("click",),
        ("scroll", -120),
        ("ctrl", "w"),
    ]


def test_input_driver_move_click_uses_quarter_second_default_delay() -> None:
    waits: list[float] = []
    driver = InputDriver(
        set_cursor_pos=lambda _point: None,
        click_left=lambda: None,
        wait=waits.append,
    )

    driver.move_click((10, 20))

    assert sum(waits) == pytest.approx(0.25)


def test_input_driver_win32_click_holds_button_briefly_before_release(monkeypatch) -> None:
    import raidbot.desktop.automation.input as input_module

    waits: list[float] = []
    events: list[tuple[int, int, int, int, int]] = []

    class FakeWin32Api:
        def mouse_event(self, event_flag: int, dx: int, dy: int, data: int, extra: int) -> None:
            events.append((event_flag, dx, dy, data, extra))

    class FakeWin32Con:
        MOUSEEVENTF_LEFTDOWN = 2
        MOUSEEVENTF_LEFTUP = 4

    def fake_import_module(name: str):
        if name == "win32api":
            return FakeWin32Api()
        if name == "win32con":
            return FakeWin32Con
        raise AssertionError(name)

    monkeypatch.setattr(input_module.importlib, "import_module", fake_import_module)
    driver = InputDriver(wait=waits.append)

    driver._click_left_win32()

    assert events == [
        (FakeWin32Con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0),
        (FakeWin32Con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0),
    ]
    assert sum(waits) == pytest.approx(0.05)


def test_input_driver_can_close_active_window() -> None:
    events: list[tuple[object, ...]] = []
    driver = InputDriver(send_hotkey=events.append)

    driver.close_active_window()

    assert events == [
        ("ctrl", "shift", "w"),
    ]


def test_input_driver_can_press_escape_to_dismiss_popups() -> None:
    events: list[tuple[object, ...]] = []
    driver = InputDriver(send_hotkey=events.append)

    driver.press_escape()

    assert events == [
        ("esc",),
    ]


def test_input_driver_holds_pagedown_for_requested_duration() -> None:
    events: list[tuple[str, str]] = []
    waits: list[float] = []
    driver = InputDriver(
        key_down=lambda key: events.append(("down", key)),
        key_up=lambda key: events.append(("up", key)),
        wait=waits.append,
    )

    driver.hold_key("pagedown", 5.0)

    down_events = [event for event in events if event == ("down", "pagedown")]
    assert len(down_events) > 1
    assert events[-1] == ("up", "pagedown")
    assert sum(waits) == pytest.approx(5.0)


def test_input_driver_repeats_keydown_while_holding_key() -> None:
    events: list[tuple[str, str]] = []
    waits: list[float] = []
    driver = InputDriver(
        key_down=lambda key: events.append(("down", key)),
        key_up=lambda key: events.append(("up", key)),
        wait=waits.append,
    )

    driver.hold_key("pagedown", 0.7)

    down_events = [event for event in events if event == ("down", "pagedown")]
    assert len(down_events) > 1
    assert events[-1] == ("up", "pagedown")
    assert sum(waits) == pytest.approx(0.7)


def test_input_driver_holds_pageup_for_requested_duration() -> None:
    events: list[tuple[str, str]] = []
    waits: list[float] = []
    driver = InputDriver(
        key_down=lambda key: events.append(("down", key)),
        key_up=lambda key: events.append(("up", key)),
        wait=waits.append,
    )

    driver.hold_key("pageup", 2.0)

    down_events = [event for event in events if event == ("down", "pageup")]
    assert len(down_events) > 1
    assert events[-1] == ("up", "pageup")
    assert sum(waits) == pytest.approx(2.0)


def test_input_driver_releases_held_key_when_stop_is_requested() -> None:
    events: list[tuple[str, str]] = []
    stop_requested = False

    def wait(_seconds: float) -> None:
        nonlocal stop_requested
        stop_requested = True

    driver = InputDriver(
        key_down=lambda key: events.append(("down", key)),
        key_up=lambda key: events.append(("up", key)),
        wait=wait,
    )
    driver.set_stop_check(lambda: stop_requested)

    with pytest.raises(InputStopRequested):
        driver.hold_key("pagedown", 5.0)

    assert events == [("down", "pagedown"), ("up", "pagedown")]


def test_input_driver_pastes_text_then_ctrl_v() -> None:
    events: list[tuple[object, ...]] = []
    clipboard = FakeClipboard()
    driver = InputDriver(send_hotkey=events.append, clipboard=clipboard)

    driver.paste_text("gm")

    assert clipboard.text == "gm"
    assert events == [
        ("ctrl", "v"),
    ]


def test_input_driver_pastes_image_then_ctrl_v(tmp_path: Path) -> None:
    image_path = tmp_path / "reply.png"
    image_path.write_bytes(b"fake image")
    events: list[tuple[object, ...]] = []
    clipboard = FakeClipboard()
    driver = InputDriver(send_hotkey=events.append, clipboard=clipboard)

    driver.paste_image(image_path)

    assert clipboard.image_path == image_path
    assert events == [
        ("ctrl", "v"),
    ]


def test_input_driver_uses_windows_clipboard_backend_by_default(
    monkeypatch,
    tmp_path: Path,
) -> None:
    import raidbot.desktop.automation.input as input_module

    events: list[tuple[object, ...]] = []
    image_path = tmp_path / "reply.png"
    image_path.write_bytes(b"fake image")

    class FakeWindowsClipboard:
        def __init__(self) -> None:
            self.calls: list[tuple[str, object]] = []

        def set_text(self, text: str) -> None:
            self.calls.append(("text", text))

        def set_image(self, selected_image_path: Path) -> None:
            self.calls.append(("image", selected_image_path))

        def set_file_image(self, selected_image_path: Path) -> None:
            self.calls.append(("file_image", selected_image_path))

    monkeypatch.setattr(input_module, "_WindowsClipboard", FakeWindowsClipboard)

    driver = InputDriver(send_hotkey=events.append)

    driver.paste_text("gm")
    driver.paste_image(image_path)

    assert driver._clipboard.calls == [
        ("text", "gm"),
        ("image", image_path),
    ]
    assert events == [
        ("ctrl", "v"),
        ("ctrl", "v"),
    ]


def test_input_driver_pastes_image_file_reference_then_ctrl_v(tmp_path: Path) -> None:
    image_path = tmp_path / "reply.png"
    image_path.write_bytes(b"fake image")
    events: list[tuple[object, ...]] = []
    waits: list[float] = []
    clipboard = FakeClipboard()
    driver = InputDriver(send_hotkey=events.append, clipboard=clipboard, wait=waits.append)

    driver.paste_image_file(image_path)

    assert clipboard.file_image_path == image_path
    assert sum(waits) == pytest.approx(1.0)
    assert events == [
        ("ctrl", "v"),
    ]


def test_input_driver_stops_before_click_when_stop_check_is_active() -> None:
    events: list[tuple[object, ...]] = []
    waits: list[float] = []
    driver = InputDriver(
        set_cursor_pos=lambda point: events.append(("move", point)),
        click_left=lambda: events.append(("click",)),
        wait=waits.append,
    )
    driver.set_stop_check(lambda: True)

    with pytest.raises(InputStopRequested):
        driver.move_click((10, 20), delay_seconds=0.5)

    assert events == []
    assert waits == []


def test_input_driver_retries_file_image_clipboard_when_first_attempt_fails(
    tmp_path: Path,
) -> None:
    image_path = tmp_path / "reply.png"
    image_path.write_bytes(b"fake image")
    events: list[tuple[object, ...]] = []
    waits: list[float] = []
    clipboard = FlakyClipboard(failures=1)
    driver = InputDriver(send_hotkey=events.append, clipboard=clipboard, wait=waits.append)

    driver.paste_image_file(image_path)

    assert clipboard.file_image_calls == 2
    assert clipboard.file_image_path == image_path
    assert sum(waits) == pytest.approx(1.2)
    assert events == [
        ("ctrl", "v"),
    ]


def test_input_driver_raises_after_clipboard_retry_exhaustion(tmp_path: Path) -> None:
    image_path = tmp_path / "reply.png"
    image_path.write_bytes(b"fake image")
    events: list[tuple[object, ...]] = []
    waits: list[float] = []
    clipboard = FlakyClipboard(failures=10)
    driver = InputDriver(send_hotkey=events.append, clipboard=clipboard, wait=waits.append)

    with pytest.raises(RuntimeError, match="OpenClipboard Failed"):
        driver.paste_image_file(image_path)

    assert clipboard.file_image_calls == 3
    assert sum(waits) == pytest.approx(0.4)
    assert events == []


def test_input_driver_uses_windows_clipboard_file_reference_backend_by_default(
    monkeypatch,
    tmp_path: Path,
) -> None:
    import raidbot.desktop.automation.input as input_module

    events: list[tuple[object, ...]] = []
    image_path = tmp_path / "reply.png"
    image_path.write_bytes(b"fake image")

    class FakeWindowsClipboard:
        def __init__(self) -> None:
            self.calls: list[tuple[str, object]] = []

        def set_text(self, text: str) -> None:
            self.calls.append(("text", text))

        def set_image(self, selected_image_path: Path) -> None:
            self.calls.append(("image", selected_image_path))

        def set_file_image(self, selected_image_path: Path) -> None:
            self.calls.append(("file_image", selected_image_path))

    monkeypatch.setattr(input_module, "_WindowsClipboard", FakeWindowsClipboard)

    driver = InputDriver(send_hotkey=events.append)

    driver.paste_image_file(image_path)

    assert driver._clipboard.calls == [
        ("file_image", image_path),
    ]
    assert events == [
        ("ctrl", "v"),
    ]


def test_windows_clipboard_uses_shell_file_clipboard_helper(
    monkeypatch,
    tmp_path: Path,
) -> None:
    import raidbot.desktop.automation.input as input_module

    image_path = tmp_path / "reply.png"
    image_path.write_bytes(b"fake image")
    calls: list[Path] = []

    monkeypatch.setattr(
        input_module,
        "_set_windows_shell_file_clipboard",
        lambda selected_image_path: calls.append(selected_image_path),
        raising=False,
    )

    input_module._WindowsClipboard().set_file_image(image_path)

    assert calls == [image_path]


def test_windows_shell_file_clipboard_uses_co_uninitialize(monkeypatch, tmp_path: Path) -> None:
    import raidbot.desktop.automation.input as input_module

    image_path = tmp_path / "reply.png"
    image_path.write_bytes(b"fake image")
    calls: list[object] = []

    class FakePythonCom:
        IID_IDataObject = object()

        def OleInitialize(self) -> None:
            calls.append("ole_init")

        def OleSetClipboard(self, data_object) -> None:
            calls.append(("ole_set_clipboard", data_object))

        def OleFlushClipboard(self) -> None:
            calls.append("ole_flush")

        def CoUninitialize(self) -> None:
            calls.append("co_uninitialize")

    class FakeShell:
        def SHCreateDataObject(self, folder_pidl, pidls, _unused, iid):
            calls.append(("create_data_object", folder_pidl, pidls, iid))
            return "data-object"

    fake_pythoncom = FakePythonCom()
    fake_shell = FakeShell()

    monkeypatch.setattr(
        input_module,
        "_resolve_shell_folder_item_pidls",
        lambda _image_path: ("folder-pidl", ["child-pidl"]),
    )

    def fake_import_module(name: str):
        if name == "pythoncom":
            return fake_pythoncom
        if name == "win32com.shell.shell":
            return fake_shell
        raise AssertionError(f"Unexpected import: {name}")

    monkeypatch.setattr(input_module.importlib, "import_module", fake_import_module)

    input_module._set_windows_shell_file_clipboard(image_path)

    assert calls == [
        ("create_data_object", "folder-pidl", [["child-pidl"]], fake_pythoncom.IID_IDataObject),
        "ole_init",
        ("ole_set_clipboard", "data-object"),
        "ole_flush",
        "co_uninitialize",
    ]
