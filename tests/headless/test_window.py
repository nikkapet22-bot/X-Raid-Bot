from __future__ import annotations

from raidbot.desktop.chrome_profiles import ChromeProfile
from raidbot.headless.models import HeadlessActionToggles, HeadlessAuthState, HeadlessRunResult


def test_headless_window_exposes_bootstrap_start_stop_and_action_toggles(qtbot) -> None:
    from raidbot.headless.window import HeadlessWindow

    window = HeadlessWindow()
    qtbot.addWidget(window)

    assert window.bootstrap_button.text() == "Import X Auth"
    assert window.start_button.text() == "Start"
    assert window.stop_button.text() == "Stop"
    assert window.profile_label.text() == "Chrome Profile"
    assert window.reply_checkbox.text() == "Reply"
    assert window.like_checkbox.text() == "Like"
    assert window.repost_checkbox.text() == "Repost"
    assert window.bookmark_checkbox.text() == "Bookmark"


def test_headless_window_exposes_profile_picker_and_selection(qtbot) -> None:
    from raidbot.headless.window import HeadlessWindow

    window = HeadlessWindow()
    qtbot.addWidget(window)

    window.set_available_profiles(
        [
            ChromeProfile(directory_name="Default", label="Main"),
            ChromeProfile(directory_name="Profile 3", label="Raid"),
        ]
    )
    window.set_selected_profile_directory("Profile 3")

    assert window.profile_combo.count() == 2
    assert window.profile_combo.itemText(0) == "Main [Default]"
    assert window.profile_combo.itemText(1) == "Raid [Profile 3]"
    assert window.selected_profile_directory() == "Profile 3"


def test_headless_window_renders_initial_status_and_log_area(qtbot) -> None:
    from raidbot.headless.window import HeadlessWindow

    window = HeadlessWindow()
    qtbot.addWidget(window)

    assert "Needs Login" in window.auth_status_label.text()
    assert "Stopped" in window.runtime_status_label.text()
    assert window.last_detected_label.text().endswith("—")
    assert window.last_result_label.text().endswith("—")
    assert window.log_output.toPlainText() == ""


def test_headless_window_emits_action_toggle_state(qtbot) -> None:
    from raidbot.headless.window import HeadlessWindow

    window = HeadlessWindow()
    qtbot.addWidget(window)
    emitted: list[HeadlessActionToggles] = []
    window.actionTogglesChanged.connect(emitted.append)

    window.reply_checkbox.setChecked(False)

    assert emitted[-1] == HeadlessActionToggles(
        reply=False,
        like=True,
        repost=True,
        bookmark=True,
    )


def test_headless_window_updates_auth_and_result_labels(qtbot) -> None:
    from raidbot.headless.window import HeadlessWindow

    window = HeadlessWindow()
    qtbot.addWidget(window)

    window.set_auth_state(HeadlessAuthState(status="authenticated"))
    window.set_last_detected_raid("https://x.com/i/status/123")
    window.set_last_result(
        HeadlessRunResult(
            url="https://x.com/i/status/123",
            success=True,
            reason="completed",
            completed_actions=("reply", "like"),
        )
    )

    assert "Authenticated" in window.auth_status_label.text()
    assert "https://x.com/i/status/123" in window.last_detected_label.text()
    assert "completed" in window.last_result_label.text()


def test_headless_window_updates_runtime_state_and_logs(qtbot) -> None:
    from raidbot.headless.window import HeadlessWindow

    window = HeadlessWindow()
    qtbot.addWidget(window)

    window.set_runtime_running(True)
    window.append_log("listener started")

    assert "Running" in window.runtime_status_label.text()
    assert "listener started" in window.log_output.toPlainText()
