from __future__ import annotations

import os
import re
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def test_readme_mentions_desktop_setup_wizard_live_stats_and_settings() -> None:
    content = Path("README.md").read_text(encoding="utf-8")

    assert (
        "The desktop app keeps the setup wizard, live stats, and settings in one interface."
        in content
    )
    assert "there is no in-app reauthorize flow" in content
    assert "delete the saved desktop config file" in content


def test_choose_startup_view_returns_wizard_for_first_run() -> None:
    from raidbot.desktop.app import choose_startup_view

    assert choose_startup_view(is_first_run=True) == "wizard"


def test_choose_startup_view_returns_main_window_for_configured_app() -> None:
    from raidbot.desktop.app import choose_startup_view

    assert choose_startup_view(is_first_run=False) == "main_window"


def test_build_application_stylesheet_contains_dark_surface_and_accent() -> None:
    from raidbot.desktop.theme import build_application_stylesheet

    stylesheet = build_application_stylesheet()

    assert "#0f1724" in stylesheet
    assert "#b8a77a" in stylesheet
    assert "QPushButton" in stylesheet
    assert "QWizard QPushButton" in stylesheet
    assert 'QPushButton[variant="secondary"]' in stylesheet
    assert 'QPushButton[variant="secondary"]:hover' in stylesheet
    assert 'QPushButton[variant="secondary"]:pressed' in stylesheet
    assert 'QPushButton[variant="secondary"]:disabled' in stylesheet
    assert 'QPushButton[variant="quiet"]' in stylesheet
    assert 'QPushButton[variant="quiet"]:pressed' in stylesheet
    assert "QPushButton#profileActionConfigButton" in stylesheet
    assert "QPushButton#profileResetButton" in stylesheet


def test_build_application_stylesheet_contains_attention_button_support() -> None:
    from raidbot.desktop.theme import build_application_stylesheet

    stylesheet = build_application_stylesheet()

    assert 'QPushButton[attentionPulseButton="true"]' in stylesheet
    assert 'QPushButton[dashboardActionButton="true"][variant="quiet"]' in stylesheet
    match = re.search(
        r'QPushButton\[variant="quiet"\]:hover \{\s*(.*?)\s*\}',
        stylesheet,
        re.S,
    )
    assert match is not None
    hover_block = match.group(1)
    assert "background-color: #151e2d;" in hover_block
    assert "color: #f3f4f6;" in hover_block
    assert "border-color: transparent;" in hover_block
    assert "QScrollBar:vertical" in stylesheet
    assert "width: 10px;" in stylesheet
    assert "border-radius: 5px;" in stylesheet
    assert "min-height: 28px;" in stylesheet
    assert "QPushButton#shellTabButton" in stylesheet
    assert "QPushButton#shellAccountButton" in stylesheet
    assert "min-height: 48px;" in stylesheet
    assert "QPushButton#metricResetButton" in stylesheet
    assert '[profileStatus="warmup"]' in stylesheet
    assert '[profileStatus="stopped"]' in stylesheet
    assert "background-color: #2a1748;" in stylesheet
    assert "QProgressBar#warmupProgressBar" in stylesheet
    assert "QCheckBox:disabled" in stylesheet
    assert "QCheckBox::indicator:disabled" in stylesheet
    assert "QCheckBox::indicator:checked:disabled" in stylesheet
    metric_reset_match = re.search(
        r'QPushButton#metricResetButton \{\s*(.*?)\s*\}',
        stylesheet,
        re.S,
    )
    assert metric_reset_match is not None
    metric_reset_block = metric_reset_match.group(1)
    assert "max-height: 18px;" in metric_reset_block
    assert "max-width: 18px;" in metric_reset_block
    assert "background-color: transparent;" in metric_reset_block
    assert "border: 1px solid transparent;" in metric_reset_block
    metric_reset_hover_match = re.search(
        r'QPushButton#metricResetButton:hover \{\s*(.*?)\s*\}',
        stylesheet,
        re.S,
    )
    assert metric_reset_hover_match is not None
    metric_reset_hover_block = metric_reset_hover_match.group(1)
    assert "background-color: rgba(17, 37, 63, 0.82);" in metric_reset_hover_block
    assert "border-color: #b8a77a;" in metric_reset_hover_block
    assert "QFrame#statusSummaryCard" in stylesheet
    assert "background: transparent;" in stylesheet
    assert "QWidget#profilesHeaderRow" in stylesheet
    assert "QListWidget#settingsRaidProfilesList::item" in stylesheet
    assert "QWizardPage" in stylesheet
    assert "QWizard > QWidget" in stylesheet


def test_dashboard_preview_bot_actions_uses_compact_presets_without_health_aside() -> None:
    content = Path("docs/ui-preview/dashboard-refresh-preview.html").read_text(
        encoding="utf-8"
    )
    runtime = Path("raidbot/desktop/web_dashboard.py").read_text(encoding="utf-8")

    assert 'data-page="bot-actions"' in content
    assert "bot-actions-wide" in content
    assert "settings-wide" in content
    assert "Raid Profiles" in content
    assert "Profile modal" not in content
    assert "Same desktop settings, redesigned into clean grouped surfaces" not in content
    assert "Auto-saved" not in content
    assert "Test sequence" not in content
    assert "Navy soft sand surface" not in content
    assert ".activity-feed" in content
    assert "overflow-y: auto;" in content
    assert '<div class="monogram">L8N</div>' in content
    assert "stroke-dasharray: 980" not in content
    assert "Survives restarts" not in content
    assert "2 captures" not in content
    assert "Randomized runtime" not in content
    assert "Open presets to edit the full list" in content
    assert "Template Health" not in content
    assert "troubleshoot-wide" in content
    assert "When Page Ready Times Out" not in content
    assert "Operator feedback" not in content
    assert "Trouble Status" not in content
    assert "Page Ready timeout" in runtime
    assert "setPageReadyTimeout" in runtime


def test_dashboard_preview_exposes_performance_mode_toggle() -> None:
    content = Path("docs/ui-preview/dashboard-refresh-preview.html").read_text(
        encoding="utf-8"
    )

    assert 'data-performance-toggle' in content
    assert 'aria-label="Performance mode"' in content
    assert 'aria-label="Account"' not in content
    assert ".performance-mode" in content
    assert "performance-toggle:not(.active)" not in content
    assert "Performance mode off" in content
    assert "Performance mode on" in content
    assert content.index('data-performance-toggle') > content.index(
        '<div class="rail-spacer"></div>'
    )
    assert 'data-app-version' in content
    assert content.index('data-app-version') > content.index('data-performance-toggle')


def test_dashboard_runtime_performance_toggle_has_visible_feedback_and_immediate_ui() -> None:
    content = Path("raidbot/desktop/web_dashboard.py").read_text(encoding="utf-8")

    assert "performance-toggle:not(.active)" not in content
    assert "aria-pressed" in content
    assert "applyPerformanceMode(enabled)" in content
    assert 'call("setPerformanceMode", enabled)' in content
    assert 'closest("[data-performance-toggle]")' in content
    assert "stopImmediatePropagation" in content


def test_dashboard_runtime_updates_sidebar_version_label() -> None:
    content = Path("raidbot/desktop/web_dashboard.py").read_text(encoding="utf-8")

    assert 'first("[data-app-version]")' in content
    assert "data.appVersion" in content


def test_dashboard_settings_raid_profiles_exposes_remove_action() -> None:
    runtime = Path("raidbot/desktop/web_dashboard.py").read_text(encoding="utf-8")
    preview = Path("docs/ui-preview/dashboard-refresh-preview.html").read_text(
        encoding="utf-8"
    )

    assert "Remove profile" in runtime
    assert 'data-web-action="remove-profile"' in runtime
    assert '"remove-profile": () => call("removeProfile", selectedProfile)' in runtime
    assert "Remove profile" in preview


def test_dashboard_performance_mode_uses_aggressive_lightweight_rendering() -> None:
    runtime = Path("raidbot/desktop/web_dashboard.py").read_text(encoding="utf-8")
    preview = Path("docs/ui-preview/dashboard-refresh-preview.html").read_text(
        encoding="utf-8"
    )

    for content in (runtime, preview):
        assert "body.performance-mode .raid-chart" in content
        assert "body.performance-mode .profile-preview" in content
        assert "body.performance-mode .chart-frame::after" in content

    assert 'document.body.classList.contains("performance-mode")' in runtime
    assert 'svg.innerHTML = ""' in runtime
    assert "const lightweightProfiles" in runtime
    assert "renderProfiles(state.latest)" in runtime


def test_dashboard_allowed_chats_do_not_render_numeric_ids_as_secondary_text() -> None:
    runtime = Path("raidbot/desktop/web_dashboard.py").read_text(encoding="utf-8")
    preview = Path("docs/ui-preview/dashboard-refresh-preview.html").read_text(
        encoding="utf-8"
    )

    assert "${html(chat.id)}" not in runtime
    assert "<span>allowed chat</span>" in runtime
    assert "<span>-1001942</span>" not in preview
    assert "<span>-1008841</span>" not in preview


def test_dashboard_bot_actions_hides_slot_section_marketing_and_enabled_badges() -> None:
    preview = Path("docs/ui-preview/dashboard-refresh-preview.html").read_text(
        encoding="utf-8"
    )
    runtime = Path("raidbot/desktop/web_dashboard.py").read_text(encoding="utf-8")

    assert "Runtime captures" not in preview
    assert "Runtime captures" not in runtime
    assert "Reply tooling" not in preview
    assert "Reply tooling" not in runtime
    assert '<h2 class="panel-title">Page Templates</h2>' not in preview
    assert '<h2 class="panel-title">Page Templates</h2>' not in runtime
    assert '<h2 class="panel-title">Presets</h2>' not in preview
    assert '<h2 class="panel-title">Presets</h2>' not in runtime
    assert '<div class="eyebrow">Page Templates</div>' in preview
    assert '<div class="eyebrow">Page Templates</div>' in runtime
    assert '<div class="eyebrow">Presets</div>' in preview
    assert '<div class="eyebrow">Presets</div>' in runtime
    assert "Four Slot Cards" not in preview
    assert "Four Slot Cards" not in runtime
    assert '<h2 class="panel-title">Slots</h2>' not in preview
    assert '<h2 class="panel-title">Slots</h2>' not in runtime
    assert 'class="slot-title">Slot 1' in preview
    assert '<button class="tiny-button">Presets</button>' not in preview
    assert '<button class="tiny-button" data-slot-presets="0">Presets</button>' not in runtime
    assert '<button class="lux-button">Open presets</button>' in preview
    assert '<button class="lux-button" data-slot-presets="0">Open presets</button>' in runtime
    assert '<span class="toggle-pill">Enabled</span>' not in preview
    assert '${slot.enabled ? "Enabled" : "Disabled"}' not in runtime
    assert "Fail fast" not in preview


def test_dashboard_troubleshooting_runtime_replaces_full_capture_panel() -> None:
    preview = Path("docs/ui-preview/dashboard-refresh-preview.html").read_text(
        encoding="utf-8"
    )
    runtime = Path("raidbot/desktop/web_dashboard.py").read_text(encoding="utf-8")

    assert 'class="troubleshoot-content"' in preview
    assert preview.count('class="preview-panel trouble-section-panel"') == 2
    assert preview.count('<div class="eyebrow">CLDF Capture Path</div>') == 1
    assert preview.count('<div class="eyebrow">Black Box Escape</div>') == 1
    assert 'const content = page.querySelector(".troubleshoot-content");' in runtime
    assert 'const path = page.querySelector(".trouble-path");' not in runtime
    assert '<article class="preview-panel trouble-section-panel">' in runtime
    assert 'class="trouble-path ${section.key === "black_box" ? "single" : ""}"' in runtime


def test_dashboard_runtime_renders_profile_raid_now_feedback() -> None:
    content = Path("raidbot/desktop/web_dashboard.py").read_text(encoding="utf-8")

    assert "profile.raidNowFeedback" in content
    assert "profile-error" in content


def test_dashboard_runtime_profile_raid_now_disabled_state_has_feedback() -> None:
    content = Path("raidbot/desktop/web_dashboard.py").read_text(encoding="utf-8")

    assert 'data-disabled-reason="${html(disabledReason)}"' in content
    assert 'aria-disabled="${profile.canRaidNow ? "false" : "true"}"' in content
    assert "profile-raid-now-unavailable" in content
    assert "Use the gear icon to choose this profile's actions" in content
    assert 'profile.canRaidNow ? "" : "disabled"' not in content


def test_dashboard_bridge_routes_performance_mode_toggle() -> None:
    from raidbot.desktop.web_dashboard import DashboardBridge

    calls = []
    bridge = DashboardBridge(
        on_ready=lambda: None,
        on_start=lambda: None,
        on_stop=lambda: None,
        on_toggle_pause=lambda: None,
        on_raid_now=lambda: None,
        on_raid_now_for_profile=lambda _profile: None,
        on_reset_profile=lambda _profile: None,
        on_configure_profile=lambda _profile: None,
        on_reset_all_profiles=lambda: None,
        on_set_raid_on_restart=lambda _enabled: None,
        on_set_performance_mode=calls.append,
        on_set_page_ready_timeout=lambda _seconds: None,
        on_reauthorize=lambda: None,
        on_refresh_chats=lambda: None,
        on_scan_senders=lambda: None,
        on_add_profile=lambda: None,
        on_move_profile=lambda _profile, _direction: None,
        on_remove_profile=lambda _profile: None,
        on_capture_page_template=lambda _key: None,
        on_test_page_template=lambda _key: None,
        on_capture_slot=lambda _slot: None,
        on_test_slot=lambda _slot: None,
        on_open_slot_presets=lambda _slot: None,
        on_capture_slot_finish=lambda _slot: None,
        on_test_enabled_slots=lambda: None,
        on_capture_troubleshoot=lambda _group, _index: None,
        on_test_troubleshoot=lambda _group, _index: None,
    )
    bridge.setPerformanceMode(True)

    assert calls == [True]


def test_dashboard_bridge_routes_page_ready_timeout() -> None:
    from raidbot.desktop.web_dashboard import DashboardBridge

    calls = []
    bridge = DashboardBridge(
        on_ready=lambda: None,
        on_start=lambda: None,
        on_stop=lambda: None,
        on_toggle_pause=lambda: None,
        on_raid_now=lambda: None,
        on_raid_now_for_profile=lambda _profile: None,
        on_reset_profile=lambda _profile: None,
        on_configure_profile=lambda _profile: None,
        on_reset_all_profiles=lambda: None,
        on_set_raid_on_restart=lambda _enabled: None,
        on_set_performance_mode=lambda _enabled: None,
        on_set_page_ready_timeout=calls.append,
        on_reauthorize=lambda: None,
        on_refresh_chats=lambda: None,
        on_scan_senders=lambda: None,
        on_add_profile=lambda: None,
        on_move_profile=lambda _profile, _direction: None,
        on_remove_profile=lambda _profile: None,
        on_capture_page_template=lambda _key: None,
        on_test_page_template=lambda _key: None,
        on_capture_slot=lambda _slot: None,
        on_test_slot=lambda _slot: None,
        on_open_slot_presets=lambda _slot: None,
        on_capture_slot_finish=lambda _slot: None,
        on_test_enabled_slots=lambda: None,
        on_capture_troubleshoot=lambda _group, _index: None,
        on_test_troubleshoot=lambda _group, _index: None,
    )
    bridge.setPageReadyTimeout(45)

    assert calls == [45.0]


def test_dashboard_bridge_routes_remove_profile() -> None:
    from raidbot.desktop.web_dashboard import DashboardBridge

    calls = []
    bridge = DashboardBridge(
        on_ready=lambda: None,
        on_start=lambda: None,
        on_stop=lambda: None,
        on_toggle_pause=lambda: None,
        on_raid_now=lambda: None,
        on_raid_now_for_profile=lambda _profile: None,
        on_reset_profile=lambda _profile: None,
        on_configure_profile=lambda _profile: None,
        on_reset_all_profiles=lambda: None,
        on_set_raid_on_restart=lambda _enabled: None,
        on_set_performance_mode=lambda _enabled: None,
        on_set_page_ready_timeout=lambda _seconds: None,
        on_reauthorize=lambda: None,
        on_refresh_chats=lambda: None,
        on_scan_senders=lambda: None,
        on_add_profile=lambda: None,
        on_move_profile=lambda _profile, _direction: None,
        on_remove_profile=calls.append,
        on_capture_page_template=lambda _key: None,
        on_test_page_template=lambda _key: None,
        on_capture_slot=lambda _slot: None,
        on_test_slot=lambda _slot: None,
        on_open_slot_presets=lambda _slot: None,
        on_capture_slot_finish=lambda _slot: None,
        on_test_enabled_slots=lambda: None,
        on_capture_troubleshoot=lambda _group, _index: None,
        on_test_troubleshoot=lambda _group, _index: None,
    )
    bridge.removeProfile("Profile 3")

    assert calls == ["Profile 3"]


def test_create_startup_window_uses_wizard_for_first_run() -> None:
    from raidbot.desktop.app import create_startup_window

    created = {}

    class FakeStorage:
        def is_first_run(self) -> bool:
            return True

    class FakeWindow:
        pass

    def wizard_factory(*, storage, telegram_service_factory):
        created["wizard_storage"] = storage
        created["telegram_service_factory"] = telegram_service_factory
        return FakeWindow()

    window = create_startup_window(
        storage=FakeStorage(),
        wizard_factory=wizard_factory,
        controller_factory=lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("controller should not be created on first run")
        ),
        main_window_factory=lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("main window should not be created on first run")
        ),
    )

    assert isinstance(window, FakeWindow)
    assert isinstance(created["wizard_storage"], FakeStorage)
    assert callable(created["telegram_service_factory"])


def test_create_startup_window_uses_main_window_for_configured_app() -> None:
    from raidbot.desktop.app import create_startup_window

    created = {}

    class FakeStorage:
        def is_first_run(self) -> bool:
            return False

    class FakeController:
        pass

    class FakeWindow:
        pass

    def controller_factory(*, storage):
        created["controller_storage"] = storage
        return FakeController()

    def main_window_factory(*, controller, storage):
        created["window_controller"] = controller
        created["window_storage"] = storage
        return FakeWindow()

    window = create_startup_window(
        storage=FakeStorage(),
        wizard_factory=lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("wizard should not be created for configured app")
        ),
        controller_factory=controller_factory,
        main_window_factory=main_window_factory,
    )

    assert isinstance(window, FakeWindow)
    assert isinstance(created["window_controller"], FakeController)
    assert created["controller_storage"] is created["window_storage"]


def test_create_startup_window_main_window_path_can_expose_bot_actions_surface() -> None:
    from raidbot.desktop.app import create_startup_window

    class FakeStorage:
        def is_first_run(self) -> bool:
            return False

    class FakeController:
        pass

    class FakeMainWindow:
        def __init__(self) -> None:
            self.bot_actions_page = object()

    window = create_startup_window(
        storage=FakeStorage(),
        wizard_factory=lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("wizard should not be created for configured app")
        ),
        controller_factory=lambda **_kwargs: FakeController(),
        main_window_factory=lambda **_kwargs: FakeMainWindow(),
    )

    assert hasattr(window, "bot_actions_page")
    assert not hasattr(window, "automation_page")


def test_show_startup_window_opens_main_window_after_wizard_finish() -> None:
    from raidbot.desktop.app import show_startup_window

    events: list[str] = []

    class FakeSignal:
        def __init__(self) -> None:
            self._callbacks = []

        def connect(self, callback) -> None:
            self._callbacks.append(callback)

        def emit(self, *args) -> None:
            for callback in list(self._callbacks):
                callback(*args)

    class FakeStorage:
        def is_first_run(self) -> bool:
            return True

    class FakeWizard:
        def __init__(self) -> None:
            self.accepted = FakeSignal()
            self.start_now_requested = False

        def show(self) -> None:
            events.append("wizard.show")

    class FakeController:
        def start_bot(self) -> None:
            events.append("controller.start_bot")

    class FakeMainWindow:
        def show(self) -> None:
            events.append("main_window.show")

    wizard = FakeWizard()

    def wizard_factory(**_kwargs):
        return wizard

    show_startup_window(
        storage=FakeStorage(),
        wizard_factory=wizard_factory,
        controller_factory=lambda **_kwargs: FakeController(),
        main_window_factory=lambda **_kwargs: FakeMainWindow(),
    )
    wizard.accepted.emit()

    assert events == ["wizard.show", "main_window.show"]


def test_show_startup_window_starts_bot_when_wizard_requests_it() -> None:
    from raidbot.desktop.app import show_startup_window

    events: list[str] = []

    class FakeSignal:
        def __init__(self) -> None:
            self._callbacks = []

        def connect(self, callback) -> None:
            self._callbacks.append(callback)

        def emit(self, *args) -> None:
            for callback in list(self._callbacks):
                callback(*args)

    class FakeStorage:
        def is_first_run(self) -> bool:
            return True

    class FakeWizard:
        def __init__(self) -> None:
            self.accepted = FakeSignal()
            self.start_now_requested = True

        def show(self) -> None:
            events.append("wizard.show")

    class FakeController:
        def start_bot(self) -> None:
            events.append("controller.start_bot")

    class FakeMainWindow:
        def show(self) -> None:
            events.append("main_window.show")

    wizard = FakeWizard()

    def wizard_factory(**_kwargs):
        return wizard

    show_startup_window(
        storage=FakeStorage(),
        wizard_factory=wizard_factory,
        controller_factory=lambda **_kwargs: FakeController(),
        main_window_factory=lambda **_kwargs: FakeMainWindow(),
    )
    wizard.accepted.emit()

    assert events == ["wizard.show", "controller.start_bot", "main_window.show"]


def test_show_startup_window_keeps_application_reference_to_startup_window(
    monkeypatch,
) -> None:
    from raidbot.desktop import app as app_module

    fake_app = None

    class FakeApplication:
        @staticmethod
        def instance():
            return fake_app

    class FakeStorage:
        def is_first_run(self) -> bool:
            return True

    class FakeSignal:
        def __init__(self) -> None:
            self._callbacks = []

        def connect(self, callback) -> None:
            self._callbacks.append(callback)

    class FakeWizard:
        def __init__(self) -> None:
            self.accepted = FakeSignal()

        def show(self) -> None:
            pass

    fake_app = type("FakeAppInstance", (), {"_raidbot_window": None})()
    monkeypatch.setattr(app_module, "QApplication", FakeApplication)
    wizard = FakeWizard()

    app_module.show_startup_window(
        storage=FakeStorage(),
        wizard_factory=lambda **_kwargs: wizard,
        controller_factory=lambda **_kwargs: object(),
        main_window_factory=lambda **_kwargs: object(),
    )

    assert fake_app._raidbot_window is wizard


def test_show_startup_window_updates_application_reference_after_wizard_finish(
    monkeypatch,
) -> None:
    from raidbot.desktop import app as app_module

    fake_app = None

    class FakeApplication:
        @staticmethod
        def instance():
            return fake_app

    class FakeStorage:
        def is_first_run(self) -> bool:
            return True

    class FakeSignal:
        def __init__(self) -> None:
            self._callbacks = []

        def connect(self, callback) -> None:
            self._callbacks.append(callback)

        def emit(self, *args) -> None:
            for callback in list(self._callbacks):
                callback(*args)

    class FakeWizard:
        def __init__(self) -> None:
            self.accepted = FakeSignal()
            self.start_now_requested = False

        def show(self) -> None:
            pass

    class FakeMainWindow:
        def show(self) -> None:
            pass

    fake_app = type("FakeAppInstance", (), {"_raidbot_window": None})()
    monkeypatch.setattr(app_module, "QApplication", FakeApplication)
    wizard = FakeWizard()
    main_window = FakeMainWindow()

    app_module.show_startup_window(
        storage=FakeStorage(),
        wizard_factory=lambda **_kwargs: wizard,
        controller_factory=lambda **_kwargs: object(),
        main_window_factory=lambda **_kwargs: main_window,
    )
    wizard.accepted.emit()

    assert fake_app._raidbot_window is main_window


def test_main_uses_storage_first_run_check_to_choose_window(monkeypatch) -> None:
    from raidbot.desktop import app as app_module

    events: list[str] = []

    class FakeWindow:
        def show(self) -> None:
            events.append("window.show")

    class FakeApplication:
        def __init__(self, _args) -> None:
            events.append("app.init")

        def setStyleSheet(self, _stylesheet) -> None:
            events.append("app.setStyleSheet")

        def exec(self) -> int:
            events.append("app.exec")
            return 7

    class FakeStorage:
        def __init__(self, base_dir) -> None:
            events.append(f"storage.init:{base_dir}")

        def is_first_run(self) -> bool:
            events.append("storage.is_first_run")
            return True

    monkeypatch.setattr(app_module, "QApplication", FakeApplication)
    monkeypatch.setattr(app_module, "DesktopStorage", FakeStorage)
    monkeypatch.setattr(app_module, "default_base_dir", lambda: "APPDATA_DIR")
    monkeypatch.setattr(app_module, "_acquire_instance_lock", lambda _base_dir: object())
    monkeypatch.setattr(app_module, "_install_restore_server", lambda _base_dir: None)
    monkeypatch.setattr(
        app_module,
        "create_startup_window",
        lambda **kwargs: events.append(
            f"startup:{app_module.choose_startup_view(is_first_run=kwargs['storage'].is_first_run())}"
        )
        or FakeWindow(),
    )

    exit_code = app_module.main()

    assert exit_code == 7
    assert events == [
        "app.init",
        "app.setStyleSheet",
        "storage.init:APPDATA_DIR",
        "storage.is_first_run",
        "startup:wizard",
        "storage.is_first_run",
        "window.show",
        "app.exec",
    ]


def test_main_applies_application_stylesheet(monkeypatch) -> None:
    from raidbot.desktop import app as app_module

    applied = {}

    class FakeStorage:
        def __init__(self, _path) -> None:
            pass

        def is_first_run(self) -> bool:
            return False

    class FakeWindow:
        def show(self) -> None:
            pass

    class FakeApplication:
        def __init__(self, _argv):
            self.stylesheet = ""

        def setStyleSheet(self, stylesheet):
            applied["stylesheet"] = stylesheet

        def exec(self):
            return 0

    monkeypatch.setattr(app_module, "QApplication", FakeApplication)
    monkeypatch.setattr(app_module, "DesktopStorage", lambda _path: FakeStorage(_path))
    monkeypatch.setattr(app_module, "default_base_dir", lambda: "ignored")
    monkeypatch.setattr(app_module, "_acquire_instance_lock", lambda _base_dir: object())
    monkeypatch.setattr(app_module, "_install_restore_server", lambda _base_dir: None)
    monkeypatch.setattr(app_module, "create_startup_window", lambda **_kwargs: FakeWindow())

    assert app_module.main([]) == 0
    assert "#0f1724" in applied["stylesheet"]


def test_main_signals_existing_instance_and_exits_cleanly(monkeypatch) -> None:
    from raidbot.desktop import app as app_module

    events: list[str] = []

    class FakeApplication:
        def __init__(self, _argv) -> None:
            events.append("app.init")

        def setStyleSheet(self, _stylesheet) -> None:
            events.append("app.setStyleSheet")

    class FakeStorage:
        def __init__(self, base_dir) -> None:
            events.append(f"storage.init:{base_dir}")

    monkeypatch.setattr(app_module, "QApplication", FakeApplication)
    monkeypatch.setattr(app_module, "DesktopStorage", FakeStorage)
    monkeypatch.setattr(app_module, "default_base_dir", lambda: "APPDATA_DIR")
    monkeypatch.setattr(app_module, "_acquire_instance_lock", lambda _base_dir: None)
    monkeypatch.setattr(
        app_module,
        "_signal_existing_instance",
        lambda _base_dir: events.append("duplicate.signal") or True,
    )
    monkeypatch.setattr(
        app_module,
        "show_startup_window",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("startup window should not be shown when another instance is running")
        ),
    )

    assert app_module.main([]) == 0
    assert events == [
        "app.init",
        "app.setStyleSheet",
        "duplicate.signal",
    ]


def test_main_shows_warning_when_existing_instance_cannot_be_signaled(monkeypatch) -> None:
    from raidbot.desktop import app as app_module

    events: list[str] = []

    class FakeApplication:
        def __init__(self, _argv) -> None:
            events.append("app.init")

        def setStyleSheet(self, _stylesheet) -> None:
            events.append("app.setStyleSheet")

    monkeypatch.setattr(app_module, "QApplication", FakeApplication)
    monkeypatch.setattr(app_module, "default_base_dir", lambda: "APPDATA_DIR")
    monkeypatch.setattr(app_module, "_acquire_instance_lock", lambda _base_dir: None)
    monkeypatch.setattr(app_module, "_signal_existing_instance", lambda _base_dir: False)
    monkeypatch.setattr(
        app_module,
        "_show_duplicate_instance_warning",
        lambda: events.append("duplicate.warning"),
    )
    monkeypatch.setattr(
        app_module,
        "DesktopStorage",
        lambda _base_dir: (_ for _ in ()).throw(
            AssertionError("storage should not be created when duplicate instance cannot be signaled")
        ),
    )

    assert app_module.main([]) == 1
    assert events == [
        "app.init",
        "app.setStyleSheet",
        "duplicate.warning",
    ]


def test_present_window_ensures_window_is_visible_on_screen() -> None:
    from raidbot.desktop import app as app_module

    events: list[str] = []

    class FakeWindow:
        def show(self) -> None:
            events.append("show")

        def ensure_visible_on_screen(self) -> None:
            events.append("ensure_visible_on_screen")

        def raise_(self) -> None:
            events.append("raise_")

        def activateWindow(self) -> None:
            events.append("activateWindow")

    app_module._present_window(FakeWindow())

    assert events == [
        "show",
        "ensure_visible_on_screen",
        "raise_",
        "activateWindow",
    ]
