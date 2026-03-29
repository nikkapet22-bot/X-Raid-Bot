from __future__ import annotations

from raidbot.desktop.automation.input import InputDriver, validate_click_target
from raidbot.desktop.automation.windowing import (
    WindowInfo,
    WindowManager,
    choose_window_for_rule,
    find_existing_chrome_window,
    find_opened_raid_window,
)


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


def test_window_manager_keeps_most_recently_focused_matching_window_across_refreshes() -> None:
    rounds = iter(
        [
            [
                WindowInfo(
                    handle=1,
                    title="X - Chrome",
                    bounds=(0, 0, 100, 100),
                    last_focused_at=1.0,
                ),
                WindowInfo(
                    handle=2,
                    title="X - Chrome",
                    bounds=(0, 0, 100, 100),
                    last_focused_at=0.0,
                ),
            ],
            [
                WindowInfo(
                    handle=1,
                    title="X - Chrome",
                    bounds=(0, 0, 100, 100),
                    last_focused_at=0.0,
                ),
                WindowInfo(
                    handle=2,
                    title="X - Chrome",
                    bounds=(0, 0, 100, 100),
                    last_focused_at=0.0,
                ),
            ],
        ]
    )
    manager = WindowManager(
        list_windows=lambda: next(rounds),
        restore_window=lambda _handle: True,
        focus_window=lambda _handle: True,
        clock=iter([10.0, 20.0]).__next__,
    )

    first = manager.list_chrome_windows()
    second = manager.list_chrome_windows()

    assert choose_window_for_rule(first, "X - Chrome").handle == 1
    assert choose_window_for_rule(second, "X - Chrome").handle == 1
    assert second[0].last_focused_at == 10.0
    assert second[1].last_focused_at == 0.0


def test_find_existing_chrome_window_accepts_single_candidate_when_profile_cannot_be_proven() -> None:
    manager = WindowManager(
        list_windows=lambda: [
            WindowInfo(
                handle=7,
                title="RaidBot - Chrome",
                bounds=(0, 0, 100, 100),
                last_focused_at=1.0,
            )
        ],
        restore_window=lambda _handle: True,
        focus_window=lambda _handle: True,
    )

    chosen = find_existing_chrome_window(manager, "Profile 3")

    assert chosen is not None
    assert chosen.handle == 7


def test_find_existing_chrome_window_prefers_most_recent_candidate_when_multiple_exist() -> None:
    manager = WindowManager(
        list_windows=lambda: [
            WindowInfo(
                handle=7,
                title="RaidBot - Chrome",
                bounds=(0, 0, 100, 100),
                last_focused_at=1.0,
            ),
            WindowInfo(
                handle=8,
                title="Personal - Chrome",
                bounds=(0, 0, 100, 100),
                last_focused_at=0.8,
            ),
        ],
        restore_window=lambda _handle: True,
        focus_window=lambda _handle: True,
    )

    chosen = find_existing_chrome_window(manager, "Profile 3")

    assert chosen is not None
    assert chosen.handle == 7


def test_find_opened_raid_window_prefers_new_handle() -> None:
    before = [
        WindowInfo(
            handle=7,
            title="RaidBot - Chrome",
            bounds=(0, 0, 100, 100),
            last_focused_at=1.0,
        )
    ]
    after = [
        *before,
        WindowInfo(
            handle=9,
            title="Raid Window - Chrome",
            bounds=(100, 100, 300, 300),
            last_focused_at=2.0,
        ),
    ]

    chosen = find_opened_raid_window(before, after)

    assert chosen is not None
    assert chosen.handle == 9


def test_find_opened_raid_window_falls_back_to_most_recent_changed_candidate() -> None:
    before = [
        WindowInfo(
            handle=7,
            title="Old title - Chrome",
            bounds=(0, 0, 100, 100),
            last_focused_at=1.0,
        )
    ]
    after = [
        WindowInfo(
            handle=7,
            title="New raid title - Chrome",
            bounds=(0, 0, 100, 100),
            last_focused_at=3.0,
        )
    ]

    chosen = find_opened_raid_window(before, after)

    assert chosen is not None
    assert chosen.handle == 7


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
