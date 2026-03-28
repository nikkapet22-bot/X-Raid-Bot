from __future__ import annotations

from raidbot.desktop.automation.input import InputDriver, validate_click_target
from raidbot.desktop.automation.windowing import WindowInfo, WindowManager, choose_window_for_rule


def test_choose_window_for_rule_prefers_most_recent_focus() -> None:
    windows = [
        WindowInfo(handle=1, title="X - Chrome", bounds=(0, 0, 100, 100), last_focused_at=1.0),
        WindowInfo(handle=2, title="X - Chrome", bounds=(0, 0, 100, 100), last_focused_at=5.0),
    ]

    chosen = choose_window_for_rule(windows, "X - Chrome")

    assert chosen is not None
    assert chosen.handle == 2


def test_validate_click_target_rejects_points_outside_window() -> None:
    assert validate_click_target((10, 10, 110, 110), (200, 200)) is False
    assert validate_click_target((10, 10, 110, 110), (50, 50)) is True


def test_window_manager_reports_focus_failure_for_minimized_window() -> None:
    window = WindowInfo(
        handle=1,
        title="X - Chrome",
        bounds=(0, 0, 100, 100),
        last_focused_at=1.0,
        is_minimized=True,
    )
    manager = WindowManager(
        list_windows=lambda: [window],
        restore_window=lambda _handle: False,
        focus_window=lambda _handle: True,
    )

    outcome = manager.ensure_interactable_window(window)

    assert outcome.success is False
    assert outcome.reason == "window_not_focusable"


def test_input_driver_moves_waits_and_clicks() -> None:
    calls: list[tuple[str, object]] = []
    driver = InputDriver(
        set_cursor_pos=lambda point: calls.append(("move", point)),
        click_left=lambda: calls.append(("click", None)),
        scroll_wheel=lambda amount: calls.append(("scroll", amount)),
        wait=lambda seconds: calls.append(("wait", seconds)),
    )

    driver.move_click((25, 35), delay_seconds=0.5)

    assert calls == [
        ("move", (25, 35)),
        ("wait", 0.5),
        ("click", None),
    ]


def test_input_driver_scroll_uses_wheel_amount() -> None:
    scroll_calls: list[int] = []
    driver = InputDriver(
        set_cursor_pos=lambda _point: None,
        click_left=lambda: None,
        scroll_wheel=scroll_calls.append,
        wait=lambda _seconds: None,
    )

    driver.scroll(-240)

    assert scroll_calls == [-240]
