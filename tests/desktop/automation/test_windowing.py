from __future__ import annotations

import pytest

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


def test_window_manager_retries_focus_before_reporting_failure() -> None:
    window = WindowInfo(
        handle=1,
        title="X - Chrome",
        bounds=(0, 0, 100, 100),
        last_focused_at=1.0,
        is_minimized=False,
    )
    clock = [10.0]
    focus_attempts: list[float] = []

    def focus_window(_handle: int) -> bool:
        focus_attempts.append(clock[0])
        return len(focus_attempts) >= 3

    def wait(seconds: float) -> None:
        clock[0] += seconds

    manager = WindowManager(
        list_windows=lambda: [window],
        restore_window=lambda _handle: True,
        focus_window=focus_window,
        clock=lambda: clock[0],
        wait=wait,
    )

    outcome = manager.ensure_interactable_window(window)

    assert outcome.success is True
    assert outcome.window == window
    assert focus_attempts == [10.0, 10.05, 10.100000000000001]


def test_window_manager_reports_maximize_success() -> None:
    window = WindowInfo(
        handle=1,
        title="X - Chrome",
        bounds=(0, 0, 100, 100),
        last_focused_at=1.0,
        is_minimized=False,
    )
    maximize_calls: list[int] = []
    manager = WindowManager(
        list_windows=lambda: [window],
        restore_window=lambda _handle: True,
        focus_window=lambda _handle: True,
        maximize_window=lambda handle: maximize_calls.append(handle) or True,
    )

    assert manager.maximize_window(window) is True
    assert maximize_calls == [1]


def test_window_manager_focus_win32_uses_raise_sequence_when_foreground_call_alone_is_not_enough(
    monkeypatch,
) -> None:
    import raidbot.desktop.automation.windowing as windowing_module

    state = {
        "foreground": 41,
        "raised": False,
        "calls": [],
    }

    class FakeWin32Con:
        SW_RESTORE = 9
        SW_SHOW = 5
        HWND_TOPMOST = -1
        HWND_NOTOPMOST = -2
        SWP_NOMOVE = 0x0002
        SWP_NOSIZE = 0x0001
        SWP_SHOWWINDOW = 0x0040

    class FakeWin32Gui:
        def GetForegroundWindow(self):
            return state["foreground"]

        def IsIconic(self, _handle: int) -> bool:
            return False

        def ShowWindow(self, handle: int, command: int) -> None:
            state["calls"].append(("show", handle, command))

        def BringWindowToTop(self, handle: int) -> None:
            state["calls"].append(("bring_to_top", handle))
            state["raised"] = True

        def SetWindowPos(
            self,
            handle: int,
            insert_after: int,
            _x: int,
            _y: int,
            _cx: int,
            _cy: int,
            flags: int,
        ) -> None:
            state["calls"].append(("set_window_pos", handle, insert_after, flags))
            state["raised"] = True

        def SetForegroundWindow(self, handle: int) -> None:
            state["calls"].append(("set_foreground", handle))
            if state["raised"]:
                state["foreground"] = handle

        def SetActiveWindow(self, handle: int) -> None:
            state["calls"].append(("set_active", handle))

        def SetFocus(self, handle: int) -> None:
            state["calls"].append(("set_focus", handle))

    fake_win32gui = FakeWin32Gui()

    def fake_import_module(name: str):
        if name == "win32con":
            return FakeWin32Con
        if name == "win32gui":
            return fake_win32gui
        raise AssertionError(f"Unexpected import: {name}")

    monkeypatch.setattr(windowing_module.importlib, "import_module", fake_import_module)
    manager = WindowManager()

    assert manager._focus_window_win32(99) is True
    assert ("bring_to_top", 99) in state["calls"]
    assert any(call[0] == "set_window_pos" for call in state["calls"])


def test_window_manager_focus_win32_does_not_restore_non_minimized_window(
    monkeypatch,
) -> None:
    import raidbot.desktop.automation.windowing as windowing_module

    state = {
        "foreground": 41,
        "raised": False,
        "calls": [],
    }

    class FakeWin32Con:
        SW_RESTORE = 9
        SW_SHOW = 5
        HWND_TOPMOST = -1
        HWND_NOTOPMOST = -2
        SWP_NOMOVE = 0x0002
        SWP_NOSIZE = 0x0001
        SWP_SHOWWINDOW = 0x0040

    class FakeWin32Gui:
        def GetForegroundWindow(self):
            return state["foreground"]

        def IsIconic(self, _handle: int) -> bool:
            return False

        def ShowWindow(self, handle: int, command: int) -> None:
            state["calls"].append(("show", handle, command))

        def BringWindowToTop(self, handle: int) -> None:
            state["calls"].append(("bring_to_top", handle))
            state["raised"] = True

        def SetWindowPos(
            self,
            handle: int,
            insert_after: int,
            _x: int,
            _y: int,
            _cx: int,
            _cy: int,
            flags: int,
        ) -> None:
            state["calls"].append(("set_window_pos", handle, insert_after, flags))
            state["raised"] = True

        def SetForegroundWindow(self, handle: int) -> None:
            state["calls"].append(("set_foreground", handle))
            if state["raised"]:
                state["foreground"] = handle

        def SetActiveWindow(self, handle: int) -> None:
            state["calls"].append(("set_active", handle))

        def SetFocus(self, handle: int) -> None:
            state["calls"].append(("set_focus", handle))

    fake_win32gui = FakeWin32Gui()

    def fake_import_module(name: str):
        if name == "win32con":
            return FakeWin32Con
        if name == "win32gui":
            return fake_win32gui
        raise AssertionError(f"Unexpected import: {name}")

    monkeypatch.setattr(windowing_module.importlib, "import_module", fake_import_module)
    manager = WindowManager()

    assert manager._focus_window_win32(99) is True
    assert ("show", 99, FakeWin32Con.SW_RESTORE) not in state["calls"]
    assert ("show", 99, FakeWin32Con.SW_SHOW) in state["calls"]


def test_window_manager_focus_win32_accepts_visible_raised_window_when_foreground_check_stays_elsewhere(
    monkeypatch,
) -> None:
    import raidbot.desktop.automation.windowing as windowing_module

    state = {
        "foreground": 41,
        "raised": False,
        "calls": [],
    }

    class FakeWin32Con:
        SW_RESTORE = 9
        SW_SHOW = 5
        HWND_TOPMOST = -1
        HWND_NOTOPMOST = -2
        SWP_NOMOVE = 0x0002
        SWP_NOSIZE = 0x0001
        SWP_SHOWWINDOW = 0x0040

    class FakeWin32Gui:
        def GetForegroundWindow(self):
            return state["foreground"]

        def IsIconic(self, _handle: int) -> bool:
            return False

        def IsWindowVisible(self, _handle: int) -> bool:
            return True

        def ShowWindow(self, handle: int, command: int) -> None:
            state["calls"].append(("show", handle, command))

        def BringWindowToTop(self, handle: int) -> None:
            state["calls"].append(("bring_to_top", handle))
            state["raised"] = True

        def SetWindowPos(
            self,
            handle: int,
            insert_after: int,
            _x: int,
            _y: int,
            _cx: int,
            _cy: int,
            flags: int,
        ) -> None:
            state["calls"].append(("set_window_pos", handle, insert_after, flags))
            state["raised"] = True

        def SetForegroundWindow(self, handle: int) -> None:
            state["calls"].append(("set_foreground", handle))

        def SetActiveWindow(self, handle: int) -> None:
            state["calls"].append(("set_active", handle))

        def SetFocus(self, handle: int) -> None:
            state["calls"].append(("set_focus", handle))

    fake_win32gui = FakeWin32Gui()

    def fake_import_module(name: str):
        if name == "win32con":
            return FakeWin32Con
        if name == "win32gui":
            return fake_win32gui
        raise AssertionError(f"Unexpected import: {name}")

    monkeypatch.setattr(windowing_module.importlib, "import_module", fake_import_module)
    manager = WindowManager()

    assert manager._focus_window_win32(99) is True
    assert ("bring_to_top", 99) in state["calls"]
    assert ("show", 99, FakeWin32Con.SW_SHOW) in state["calls"]


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

    assert calls[0] == ("move", (25, 35))
    assert calls[-1] == ("click", None)
    assert sum(value for action, value in calls if action == "wait") == pytest.approx(0.5)


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
