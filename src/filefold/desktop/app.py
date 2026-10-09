"""FileFold desktop app: runs FileFold's server on this computer and shows the web UI in a
native window, with a menu-bar (macOS) or system-tray (Windows) icon.

Closing the window keeps FileFold running in the menu bar / tray; reopen it from that icon (or
the Dock on macOS) and quit from the icon or with Cmd/Ctrl+Q. Workspaces live in ~/.filefold/workspaces, shared with the command line.

Environment variables (mostly for tests):
  FILEFOLD_DESKTOP_PORT   preferred local port (default 47321, so the window's saved settings
                          survive restarts; 0 means any free port)
  FILEFOLD_DESKTOP_DATA   where the window's browser storage lives (default ~/.filefold/desktop)
  FILEFOLD_DOWNLOAD_DIR   where exports and downloads are saved (default: the Downloads folder)
  FILEFOLD_WORKSPACE_DIR  the workspace folder (default ~/.filefold/workspaces)

`--smoke-test` starts everything, checks the UI really renders, prints SMOKE OK and exits 0
(non-zero on failure). CI runs it against every built bundle.
"""
from __future__ import annotations

import argparse
import os
import signal
import socket
import sys
import threading
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

# A windowed (no console) frozen app has no stdout/stderr on Windows; libraries that write to
# them, or ask them isatty(), would crash before the window ever appears.
for _name in ("stdout", "stderr"):
    if getattr(sys, _name) is None:
        setattr(sys, _name, open(os.devnull, "w"))

DEFAULT_PORT = 47321


# ---------------------------------------------------------------------------
# Plain helpers (tested without a window)
# ---------------------------------------------------------------------------

def choose_port(preferred: int) -> int:
    """The preferred port if it is free, else any free port.

    A stable port matters: the window's saved settings (theme, tour) are stored per address,
    so a new random port on every launch would forget them.
    """
    if preferred:
        try:
            with socket.socket() as s:
                # Probe the way uvicorn binds (SO_REUSEADDR on POSIX), so connections left in
                # TIME_WAIT by the previous run don't push a quick relaunch onto another port.
                # Never on Windows, where SO_REUSEADDR would let us share a port in use.
                if os.name != "nt":
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(("127.0.0.1", preferred))
            return preferred
        except OSError:
            pass
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def is_external(url: str, port: int) -> bool:
    """True for links that should open in the person's normal browser instead of the app window."""
    parsed = urlparse(url)
    if parsed.scheme in ("blob", "data", "about", "qrc", ""):
        return False
    return not (parsed.hostname in ("127.0.0.1", "localhost") and parsed.port == port)


def unique_download_path(directory: Path, name: str) -> Path:
    """Where to save a download without ever overwriting an existing file."""
    leaf = Path((name or "").replace("\\", "/")).name
    if leaf in ("", ".", ".."):
        leaf = "download"
    stem, suffix = Path(leaf).stem, Path(leaf).suffix
    candidate, n = Path(directory) / leaf, 1
    while candidate.exists():
        candidate = Path(directory) / f"{stem} ({n}){suffix}"
        n += 1
    return candidate


def _download_dir() -> Path:
    if os.environ.get("FILEFOLD_DOWNLOAD_DIR"):
        return Path(os.environ["FILEFOLD_DOWNLOAD_DIR"])
    from PySide6.QtCore import QStandardPaths
    found = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation)
    return Path(found) if found else Path.home() / "Downloads"


def _data_dir() -> Path:
    return Path(os.environ.get("FILEFOLD_DESKTOP_DATA") or Path.home() / ".filefold" / "desktop")


def _wait_for_server(port: int, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=1)
            return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError(f"FileFold's local server did not start within {timeout:.0f} s")


# ---------------------------------------------------------------------------
# Local server
# ---------------------------------------------------------------------------

class _ServerThread(threading.Thread):
    def __init__(self, port: int) -> None:
        super().__init__(daemon=True, name="filefold-server")
        self.port = port
        self._server = None

    def run(self) -> None:
        import uvicorn

        from filefold.api.main import app as fastapi_app   # a real import, so bundlers find it
        # log_config=None: no console to log to in a windowed app
        config = uvicorn.Config(fastapi_app, host="127.0.0.1", port=self.port, log_config=None, log_level="warning")
        self._server = uvicorn.Server(config)
        self._server.run()

    def stop(self) -> None:
        if self._server:
            self._server.should_exit = True


# ---------------------------------------------------------------------------
# Window
# ---------------------------------------------------------------------------

def _build_qt(port: int, smoke: bool):
    """Create the Qt objects. Imported lazily so the helpers above work without Qt."""
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QAction, QDesktopServices, QIcon, QKeySequence
    from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import QMainWindow

    from filefold.desktop import icon as app_icon

    class _ExternalOpener(QWebEnginePage):
        """Receives target=_blank links and hands them to the system browser."""
        def acceptNavigationRequest(self, url, nav_type, is_main_frame):
            QDesktopServices.openUrl(url)
            self.deleteLater()
            return False

    class _Page(QWebEnginePage):
        def acceptNavigationRequest(self, url, nav_type, is_main_frame):
            if is_external(url.toString(), port):
                QDesktopServices.openUrl(url)
                return False
            return super().acceptNavigationRequest(url, nav_type, is_main_frame)

        def createWindow(self, _type):
            return _ExternalOpener(self.profile(), self)

    class _Window(QMainWindow):
        def __init__(self, profile, on_quit):
            super().__init__()
            self.setWindowTitle("FileFold")
            self.resize(1320, 860)
            self.setMinimumSize(900, 600)
            self.view = QWebEngineView(self)
            self.page = _Page(profile, self.view)
            self.view.setPage(self.page)
            self.setCentralWidget(self.view)
            quit_action = QAction("Quit FileFold", self)
            quit_action.setShortcut(QKeySequence.StandardKey.Quit)
            quit_action.triggered.connect(on_quit)
            self.addAction(quit_action)
            self.hide_on_close = not smoke

        def closeEvent(self, event):
            if self.hide_on_close:        # keep running in the menu bar / tray
                event.ignore()
                self.hide()
            else:
                super().closeEvent(event)

    data = _data_dir()
    data.mkdir(parents=True, exist_ok=True)
    # A named profile stores to disk (Qt 6's default profile keeps nothing between launches).
    profile = QWebEngineProfile("FileFold")
    profile.setPersistentStoragePath(str(data / "web"))
    profile.setCachePath(str(data / "cache"))
    profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies)
    return profile, _Window, QIcon(app_icon.make_pixmap(256)), QUrl


class FileFoldApp:
    def __init__(self, smoke: bool = False) -> None:
        from PySide6.QtWidgets import QApplication

        self.smoke = smoke
        self.qt = QApplication.instance() or QApplication(sys.argv[:1])
        self.qt.setApplicationName("FileFold")
        self.qt.setQuitOnLastWindowClosed(smoke)
        preferred = int(os.environ.get("FILEFOLD_DESKTOP_PORT", DEFAULT_PORT))
        self.port = choose_port(preferred)
        self.server = _ServerThread(self.port)
        self.profile, self._Window, self.icon, self._QUrl = _build_qt(self.port, smoke)
        self.qt.setWindowIcon(self.icon)
        self.profile.downloadRequested.connect(self._on_download)
        self.window = None
        self.tray = None
        self.exit_code = 0

    # -- downloads -----------------------------------------------------------------------
    def _on_download(self, request) -> None:
        target = unique_download_path(_download_dir(), request.downloadFileName())
        target.parent.mkdir(parents=True, exist_ok=True)
        request.setDownloadDirectory(str(target.parent))
        request.setDownloadFileName(target.name)
        request.isFinishedChanged.connect(lambda: self._download_done(request, target))
        request.accept()

    def _download_done(self, request, target: Path) -> None:
        if not request.isFinished() or not self.tray:
            return
        from PySide6.QtWebEngineCore import QWebEngineDownloadRequest
        ok = request.state() == QWebEngineDownloadRequest.DownloadState.DownloadCompleted
        self.tray.showMessage("FileFold", f"Saved {target.name} to {target.parent}" if ok
                              else f"Could not save {target.name}")

    # -- tray / menu bar -----------------------------------------------------------------
    def _setup_tray(self) -> None:
        from PySide6.QtGui import QAction
        from PySide6.QtWidgets import QMenu, QSystemTrayIcon

        if not QSystemTrayIcon.isSystemTrayAvailable():
            self.qt.setQuitOnLastWindowClosed(True)
            self.window.hide_on_close = False
            return
        tray = QSystemTrayIcon(self.icon, self.qt)
        menu = QMenu()
        open_act = QAction("Open FileFold", menu)
        open_act.triggered.connect(self.show_window)
        menu.addAction(open_act)
        menu.addSeparator()
        quit_act = QAction("Quit FileFold", menu)
        quit_act.triggered.connect(self.quit)
        menu.addAction(quit_act)
        tray.setContextMenu(menu)
        tray.setToolTip("FileFold")
        tray.activated.connect(self._tray_clicked)
        tray.show()
        self._tray_menu = menu
        self.tray = tray
        if sys.platform == "darwin":                # clicking the Dock icon reopens a closed window
            self.qt.applicationStateChanged.connect(self._app_state_changed)

    def _app_state_changed(self, state) -> None:
        from PySide6.QtCore import Qt
        if state == Qt.ApplicationState.ApplicationActive and self.window and not self.window.isVisible():
            self.show_window()

    def _tray_clicked(self, reason) -> None:
        from PySide6.QtWidgets import QSystemTrayIcon
        if reason == QSystemTrayIcon.ActivationReason.Trigger and sys.platform != "darwin":
            self.show_window()

    def show_window(self) -> None:
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()

    # -- lifecycle -----------------------------------------------------------------------
    def quit(self) -> None:
        self.server.stop()
        if self.window:
            # Release the page before the profile so the browser storage is flushed to disk.
            self.window.view.setPage(None)
            self.window.page.deleteLater()
        self.qt.quit()

    def _smoke_check(self, ok: bool) -> None:
        if not ok:
            print("SMOKE FAIL: the page did not load")
            self.exit_code = 1
            self.qt.quit()
            return

        def done(result):
            try:
                base = f"http://127.0.0.1:{self.port}"
                urllib.request.urlopen(f"{base}/api/workspaces", timeout=5).read()
                urllib.request.urlopen(f"{base}/static/samples/manifest.json", timeout=5).read()
                if result != "ok":
                    raise RuntimeError(f"UI scripts did not run ({result!r})")
                print("SMOKE OK")
            except Exception as exc:          # anything at all is a failed smoke test
                print(f"SMOKE FAIL: {exc}")
                self.exit_code = 1
            self.quit()

        self.window.page.runJavaScript(
            "(typeof showView === 'function' && document.title === 'FileFold'"
            " && document.documentElement.dataset.desktop === '1') ? 'ok' : 'missing'", 0, done)

    def run(self) -> int:
        from PySide6.QtCore import QTimer

        self.server.start()
        _wait_for_server(self.port)
        self.window = self._Window(self.profile, self.quit)
        if self.smoke:
            self.window.page.loadFinished.connect(self._smoke_check)
            QTimer.singleShot(90_000, lambda: (print("SMOKE FAIL: timed out"), setattr(self, "exit_code", 1), self.qt.quit()))
        else:
            self._setup_tray()
        self.window.view.setUrl(self._QUrl(f"http://127.0.0.1:{self.port}/?desktop=1"))
        self.window.show()

        # Let Ctrl+C / SIGTERM end the app cleanly (the Qt loop otherwise never yields to Python).
        signal.signal(signal.SIGINT, lambda *_: self.quit())
        signal.signal(signal.SIGTERM, lambda *_: self.quit())
        self._tick = QTimer()
        self._tick.start(250)
        self._tick.timeout.connect(lambda: None)

        code = self.qt.exec()
        return self.exit_code or code


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="filefold-desktop", description="FileFold desktop app")
    parser.add_argument("--smoke-test", action="store_true", help="start, check the UI renders, then exit")
    args, _unknown = parser.parse_known_args(sys.argv[1:] if argv is None else argv)
    try:
        code = FileFoldApp(smoke=args.smoke_test).run()
    except Exception as exc:
        if args.smoke_test:
            print(f"SMOKE FAIL: {exc}")
            raise SystemExit(1)
        from PySide6.QtWidgets import QApplication, QMessageBox
        QApplication.instance() or QApplication(sys.argv[:1])
        QMessageBox.critical(None, "FileFold", f"FileFold could not start:\n\n{exc}")
        raise SystemExit(1)
    raise SystemExit(code)


if __name__ == "__main__":
    main()
