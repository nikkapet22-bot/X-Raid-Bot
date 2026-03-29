from __future__ import annotations

from pathlib import Path

from raidbot.desktop.automation.input import InputDriver


class FakeClipboard:
    def __init__(self) -> None:
        self.text = None
        self.image_path = None

    def set_text(self, text: str) -> None:
        self.text = text

    def set_image(self, image_path: Path) -> None:
        self.image_path = image_path


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
