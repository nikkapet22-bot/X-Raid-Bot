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
    assert "#2f7ef7" in stylesheet
    assert "QPushButton" in stylesheet
    assert "QWizard QPushButton" in stylesheet
    assert 'QPushButton[variant="secondary"]' in stylesheet
    assert 'QPushButton[variant="quiet"]' in stylesheet
    match = re.search(
        r'QPushButton\[variant="quiet"\]:hover \{\s*(.*?)\s*\}',
        stylesheet,
        re.S,
    )
    assert match is not None
    hover_block = match.group(1)
    assert "background-color: #0f1724;" in hover_block
    assert "color: #edf3ff;" in hover_block
    assert "border-color: transparent;" in hover_block


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
