from __future__ import annotations

from raidbot.headless.models import HeadlessActionToggles, HeadlessAuthState, HeadlessRunResult


def test_headless_window_exposes_bootstrap_start_stop_and_action_toggles(qtbot) -> None:
    from raidbot.headless.window import HeadlessWindow

    window = HeadlessWindow()
    qtbot.addWidget(window)

    assert window.bootstrap_button.text() == "Bootstrap Login"
    assert window.start_button.text() == "Start"
    assert window.stop_button.text() == "Stop"
    assert window.reply_checkbox.text() == "Reply"
    assert window.like_checkbox.text() == "Like"
    assert window.repost_checkbox.text() == "Repost"
    assert window.bookmark_checkbox.text() == "Bookmark"


def test_headless_window_renders_initial_status_and_log_area(qtbot) -> None:
    from raidbot.headless.window import HeadlessWindow

    window = HeadlessWindow()
    qtbot.addWidget(window)

    assert "Needs Login" in window.auth_status_label.text()
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
