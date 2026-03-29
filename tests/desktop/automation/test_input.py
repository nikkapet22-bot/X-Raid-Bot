from __future__ import annotations

from pathlib import Path

from raidbot.desktop.automation.input import InputDriver


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


def test_input_driver_can_close_active_window() -> None:
    events: list[tuple[object, ...]] = []
    driver = InputDriver(send_hotkey=events.append)

    driver.close_active_window()

    assert events == [
        ("ctrl", "shift", "w"),
    ]


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
    assert waits == [1.0]
    assert events == [
        ("ctrl", "v"),
    ]


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
