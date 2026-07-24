"""PySide6 desktop wrapper — runs the FileFold server locally and shows the
web UI in a native window with a system-tray icon."""
from __future__ import annotations

import socket
import threading
import time

import uvicorn
from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication, QMainWindow, QMenu, QSystemTrayIcon


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _make_icon(size: int = 32) -> QIcon:
    """Generate the FF tray/window icon programmatically."""
    px = QPixmap(size, size)
    px.fill(Qt.GlobalColor.transparent)
    painter = QPainter(px)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    # Background circle
    painter.setBrush(QColor("#58A6FF"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(0, 0, size, size, size * 0.25, size * 0.25)
    # "FF" text
    font = QFont("Arial", max(int(size * 0.38), 8), QFont.Weight.Bold)
    painter.setFont(font)
    painter.setPen(QColor("#000000"))
    painter.drawText(px.rect(), Qt.AlignmentFlag.AlignCenter, "FF")
    painter.end()
    return QIcon(px)


# ---------------------------------------------------------------------------
# Background server thread
# ---------------------------------------------------------------------------

class _ServerThread(threading.Thread):
    def __init__(self, port: int) -> None:
        super().__init__(daemon=True, name="filefold-server")
        self.port = port
        self._server: uvicorn.Server | None = None

    def run(self) -> None:
        config = uvicorn.Config(
            "filefold.api.main:app",
            host="127.0.0.1",
            port=self.port,
            log_level="warning",
        )
        self._server = uvicorn.Server(config)
        self._server.run()

    def stop(self) -> None:
        if self._server:
            self._server.should_exit = True


def _wait_for_server(port: int, timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError(f"FileFold server did not start within {timeout}s")


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class _Window(QMainWindow):
    def __init__(self, url: str, icon: QIcon) -> None:
        super().__init__()
        self.setWindowTitle("FileFold")
        self.setWindowIcon(icon)
        self.resize(1280, 820)

        self._view = QWebEngineView()
        self._view.setUrl(QUrl(url))
        self.setCentralWidget(self._view)

    def closeEvent(self, event):
        # Hide to tray rather than quitting so the server keeps running
        event.ignore()
        self.hide()


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

class FileFoldApp:
    def __init__(self) -> None:
        self._qt = QApplication.instance() or QApplication([])
        self._qt.setApplicationName("FileFold")
        self._qt.setQuitOnLastWindowClosed(False)

        self._port = _find_free_port()
        self._icon = _make_icon(64)
        self._qt.setWindowIcon(self._icon)

        self._server = _ServerThread(self._port)
        self._window: _Window | None = None
        self._tray: QSystemTrayIcon | None = None

    # ------------------------------------------------------------------
    # Tray
    # ------------------------------------------------------------------

    def _setup_tray(self) -> None:
        tray = QSystemTrayIcon(self._icon, self._qt)

        menu = QMenu()

        open_act = QAction("Open FileFold", menu)
        open_act.triggered.connect(self._show_window)
        menu.addAction(open_act)

        menu.addSeparator()

        quit_act = QAction("Quit", menu)
        quit_act.triggered.connect(self._quit)
        menu.addAction(quit_act)

        tray.setContextMenu(menu)
        tray.setToolTip("FileFold")
        tray.activated.connect(self._tray_clicked)
        tray.show()
        self._tray = tray

    def _tray_clicked(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self._window and self._window.isVisible():
                self._window.hide()
            else:
                self._show_window()

    # ------------------------------------------------------------------
    # Window
    # ------------------------------------------------------------------

    def _show_window(self) -> None:
        if self._window:
            self._window.show()
            self._window.raise_()
            self._window.activateWindow()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _quit(self) -> None:
        self._server.stop()
        self._qt.quit()

    def run(self) -> int:
        # Start the API server and wait until it responds
        self._server.start()
        _wait_for_server(self._port)

        url = f"http://127.0.0.1:{self._port}"
        self._window = _Window(url, self._icon)
        self._setup_tray()
        self._window.show()

        return self._qt.exec()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    raise SystemExit(FileFoldApp().run())


if __name__ == "__main__":
    main()
