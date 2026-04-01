from __future__ import annotations

from collections.abc import Callable
import hashlib
from pathlib import Path

from PySide6.QtCore import QLockFile
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMessageBox, QStyle

from raidbot.desktop.branding import APP_NAME
from raidbot.desktop.controller import DesktopController
from raidbot.desktop.main_window import MainWindow
from raidbot.desktop.storage import DesktopStorage, default_base_dir
from raidbot.desktop.theme import build_application_stylesheet
from raidbot.desktop.telegram_setup import TelegramSetupService
from raidbot.desktop.wizard import SetupWizard


def choose_startup_view(*, is_first_run: bool) -> str:
    return "wizard" if is_first_run else "main_window"


def create_startup_window(
    *,
    storage,
    wizard_factory: Callable[..., object] = SetupWizard,
    controller_factory: Callable[..., object] = DesktopController,
    main_window_factory: Callable[..., object] = MainWindow,
):
    startup_view = choose_startup_view(is_first_run=storage.is_first_run())
    if startup_view == "wizard":
        return wizard_factory(
            storage=storage,
            telegram_service_factory=_build_telegram_setup_service,
        )

    controller = controller_factory(storage=storage)
    return main_window_factory(controller=controller, storage=storage)


def show_startup_window(
    *,
    storage,
    wizard_factory: Callable[..., object] = SetupWizard,
    controller_factory: Callable[..., object] = DesktopController,
    main_window_factory: Callable[..., object] = MainWindow,
):
    window = create_startup_window(
        storage=storage,
        wizard_factory=wizard_factory,
        controller_factory=controller_factory,
        main_window_factory=main_window_factory,
    )
    if choose_startup_view(is_first_run=storage.is_first_run()) == "wizard":
        if hasattr(window, "accepted"):
            _wire_wizard_completion(
                wizard=window,
                storage=storage,
                controller_factory=controller_factory,
                main_window_factory=main_window_factory,
            )
    _present_window(window)
    return window


def _wire_wizard_completion(
    *,
    wizard,
    storage,
    controller_factory: Callable[..., object],
    main_window_factory: Callable[..., object],
) -> None:
    def open_main_window() -> None:
        controller = controller_factory(storage=storage)
        if getattr(wizard, "start_now_requested", False):
            controller.start_bot()
        main_window = main_window_factory(controller=controller, storage=storage)
        wizard._main_window = main_window
        _present_window(main_window)

    wizard.accepted.connect(open_main_window)


def _present_window(window) -> None:
    _retain_window_reference(window)
    _ensure_window_icon(window)
    window.show()
    if hasattr(window, "ensure_visible_on_screen"):
        window.ensure_visible_on_screen()
    if hasattr(window, "raise_"):
        window.raise_()
    if hasattr(window, "activateWindow"):
        window.activateWindow()


def _retain_window_reference(window) -> None:
    instance = getattr(QApplication, "instance", None)
    app = instance() if callable(instance) else None
    if app is None:
        return
    app._raidbot_window = window


def _acquire_instance_lock(base_dir: Path) -> QLockFile | None:
    base_dir = Path(base_dir)
    base_dir.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(base_dir / "raidbot.lock"))
    if not lock.tryLock(0):
        return None
    instance = getattr(QApplication, "instance", None)
    app = instance() if callable(instance) else None
    if app is not None:
        app._raidbot_instance_lock = lock
    return lock


def _show_duplicate_instance_warning() -> None:
    QMessageBox.warning(
        None,
        f"{APP_NAME} Already Running",
        f"{APP_NAME} is already running. Look for pythonw.exe in Task Manager or use the tray icon to restore the existing window.",
    )


def _restore_server_name(base_dir: Path) -> str:
    resolved = str(Path(base_dir).resolve())
    digest = hashlib.sha1(resolved.encode("utf-8")).hexdigest()[:16]
    return f"raidbot-{digest}"


def _install_restore_server(base_dir: Path):
    server_name = _restore_server_name(base_dir)
    QLocalServer.removeServer(server_name)
    server = QLocalServer()
    if not server.listen(server_name):
        return None

    def handle_connections() -> None:
        while server.hasPendingConnections():
            socket = server.nextPendingConnection()
            if socket is not None:
                socket.disconnectFromServer()
                if hasattr(socket, "deleteLater"):
                    socket.deleteLater()
            _restore_retained_window()

    server.newConnection.connect(handle_connections)
    instance = getattr(QApplication, "instance", None)
    app = instance() if callable(instance) else None
    if app is not None:
        app._raidbot_restore_server = server
    return server


def _signal_existing_instance(base_dir: Path) -> bool:
    socket = QLocalSocket()
    socket.connectToServer(_restore_server_name(base_dir))
    if not socket.waitForConnected(250):
        return False
    socket.write(b"restore")
    socket.flush()
    socket.waitForBytesWritten(250)
    socket.disconnectFromServer()
    if hasattr(socket, "deleteLater"):
        socket.deleteLater()
    return True


def _restore_retained_window() -> None:
    instance = getattr(QApplication, "instance", None)
    app = instance() if callable(instance) else None
    if app is None:
        return
    window = getattr(app, "_raidbot_window", None)
    if window is None:
        return
    if hasattr(window, "restore_from_tray"):
        window.restore_from_tray()
        return
    if hasattr(window, "showNormal"):
        window.showNormal()
    elif hasattr(window, "show"):
        window.show()
    if hasattr(window, "raise_"):
        window.raise_()
    if hasattr(window, "activateWindow"):
        window.activateWindow()


def _ensure_window_icon(window) -> None:
    if not all(hasattr(window, name) for name in ("windowIcon", "setWindowIcon", "style")):
        return
    if not window.windowIcon().isNull():
        return
    icon = window.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
    if not icon.isNull():
        window.setWindowIcon(icon)


def _build_telegram_setup_service(api_id: int, api_hash: str, session_path):
    return TelegramSetupService(
        api_id=api_id,
        api_hash=api_hash,
        session_path=session_path,
    )


def main(argv: list[str] | None = None) -> int:
    app = QApplication(argv or [])
    if hasattr(app, "setApplicationName"):
        app.setApplicationName(APP_NAME)
    if hasattr(app, "setApplicationDisplayName"):
        app.setApplicationDisplayName(APP_NAME)
    app.setStyleSheet(build_application_stylesheet())
    base_dir = default_base_dir()
    if _acquire_instance_lock(base_dir) is None:
        if _signal_existing_instance(base_dir):
            return 0
        _show_duplicate_instance_warning()
        return 1
    _install_restore_server(base_dir)
    storage = DesktopStorage(base_dir)
    show_startup_window(storage=storage)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
