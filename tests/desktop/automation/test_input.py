from __future__ import annotations

from raidbot.desktop.automation.input import InputDriver


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
