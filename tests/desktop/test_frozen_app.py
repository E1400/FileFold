"""End-to-end tests against the BUILT desktop app (PyInstaller bundle).

Run after building:
    FILEFOLD_DESKTOP_APP=dist/FileFold.app/Contents/MacOS/FileFold pytest tests/desktop -q
(Windows: dist\\FileFold\\FileFold.exe). Skipped when FILEFOLD_DESKTOP_APP is not set.

The app is driven through QtWebEngine's remote-debugging port with a minimal Chrome DevTools
Protocol client (Playwright cannot attach: QtWebEngine lacks browser-level CDP commands it needs).
This exercises the real embedded browser: storage persistence, downloads and the desktop-only UI
tweaks. Click-level UI behaviour is covered by the web e2e suite. Everything (workspaces,
downloads, browser storage) lives in temp folders.
"""
from __future__ import annotations

import os
import socket
import subprocess
import time
import urllib.request
import zipfile
from pathlib import Path

import json
import itertools

import pytest
from websockets.sync.client import connect

APP = os.environ.get("FILEFOLD_DESKTOP_APP")
pytestmark = pytest.mark.skipif(not APP, reason="set FILEFOLD_DESKTOP_APP to a built FileFold binary")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Desktop:
    def __init__(self, root: Path):
        self.root = root
        self.port = _free_port()          # the app's own server
        self.debug = _free_port()         # QtWebEngine remote debugging
        self.proc = None

    def start(self):
        env = {**os.environ,
               "FILEFOLD_WORKSPACE_DIR": str(self.root / "workspaces"),
               "FILEFOLD_DOWNLOAD_DIR": str(self.root / "downloads"),
               "FILEFOLD_DESKTOP_DATA": str(self.root / "data"),
               "FILEFOLD_DESKTOP_PORT": str(self.port),
               "QTWEBENGINE_REMOTE_DEBUGGING": str(self.debug)}
        (self.root / "downloads").mkdir(parents=True, exist_ok=True)
        self.proc = subprocess.Popen([APP], env=env, stdout=open(self.root / "app.log", "ab"), stderr=subprocess.STDOUT)
        deadline = time.time() + 90
        while time.time() < deadline:
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{self.debug}/json", timeout=1)
                return
            except OSError:
                if self.proc.poll() is not None:
                    raise RuntimeError((self.root / "app.log").read_text())
                time.sleep(0.5)
        raise RuntimeError("desktop app did not start")

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                self.proc.kill()


@pytest.fixture()
def desktop(tmp_path):
    d = Desktop(tmp_path)
    d.start()
    yield d
    d.stop()


class Page:
    """Just enough of the DevTools protocol: evaluate JavaScript in the app's page."""

    def __init__(self, d: Desktop):
        deadline = time.time() + 60
        while True:
            targets = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{d.debug}/json", timeout=2).read())
            page = next((t for t in targets if t.get("type") == "page" and f":{d.port}" in t.get("url", "")), None)
            if page or time.time() > deadline:
                break
            time.sleep(0.3)
        assert page, f"no FileFold page among {targets}"
        self.url = page["url"]
        self.ws = connect(page["webSocketDebuggerUrl"], max_size=None, open_timeout=20)
        self.ids = itertools.count(1)
        self.wait("document.readyState === 'complete' && typeof showView === 'function'")

    def evaluate(self, expression: str, gesture: bool = False):
        msg_id = next(self.ids)
        self.ws.send(json.dumps({"id": msg_id, "method": "Runtime.evaluate", "params": {
            "expression": expression, "returnByValue": True, "awaitPromise": True, "userGesture": gesture}}))
        while True:
            reply = json.loads(self.ws.recv(timeout=60))
            if reply.get("id") == msg_id:
                result = reply["result"]
                if "exceptionDetails" in result:
                    raise AssertionError(f"{expression!r} threw: {result['exceptionDetails']}")
                return result["result"].get("value")

    def wait(self, expression: str, timeout: float = 60) -> None:
        deadline = time.time() + timeout
        while not self.evaluate(f"!!({expression})"):
            if time.time() > deadline:
                raise AssertionError(f"timed out waiting for {expression}")
            time.sleep(0.25)

    def click(self, selector: str) -> None:
        self.evaluate(f"document.querySelector({json.dumps(selector)}).click()", gesture=True)

    def close(self):
        self.ws.close()


def test_desktop_app_serves_the_full_ui_with_desktop_tweaks(desktop):
    page = Page(desktop)
    assert f"127.0.0.1:{desktop.port}" in page.url and "desktop=1" in page.url
    assert page.evaluate("document.documentElement.dataset.desktop") == "1"
    # the "Download desktop app" button is pointless inside the desktop app
    assert page.evaluate("getComputedStyle(document.querySelector('[aria-label=\"Download desktop app\"]')).display") == "none"
    page.evaluate("showView('help')")
    text = page.evaluate("document.getElementById('view-help').innerText")
    assert "on this computer" in text and "on the server" not in text and "in this browser" not in text
    page.close()


def test_create_a_workspace_from_a_sample_and_export_it(desktop):
    page = Page(desktop)
    page.evaluate("localStorage.setItem('filefold.tour', 'dismissed'); showView('new-workspace')")
    page.evaluate("loadSample('Job-1')")
    page.wait("document.querySelector('#split-config .split-row')")
    page.evaluate("document.getElementById('sel-mesh').click()")
    page.click("#create-btn-row button")
    page.wait("document.querySelectorAll('#detail-files tr').length > 0")
    assert (desktop.root / "workspaces" / "Job-1" / "mesh.inp").is_file()

    page.evaluate("exportWorkspace()", gesture=True)
    target = desktop.root / "downloads" / "Job-1.zip"
    deadline = time.time() + 30
    while time.time() < deadline and not (target.exists() and zipfile.is_zipfile(target)):
        time.sleep(0.3)
    assert target.is_file(), f"export did not land in the downloads folder: {list((desktop.root / 'downloads').iterdir())}"
    assert {"Job-1.inp", "mesh.inp"} <= set(zipfile.ZipFile(target).namelist())

    page.evaluate("exportWorkspace()", gesture=True)            # a second export must not overwrite the first
    second = desktop.root / "downloads" / "Job-1 (1).zip"
    deadline = time.time() + 30
    while time.time() < deadline and not (second.exists() and zipfile.is_zipfile(second)):
        time.sleep(0.3)
    assert second.is_file() and target.is_file()
    page.close()


@pytest.mark.skipif(os.name == "nt", reason="Windows has no SIGTERM: terminate() kills the app before storage is flushed "
                                            "(users quit from the tray, which saves normally)")
def test_theme_and_tour_choices_survive_a_restart(tmp_path):
    d = Desktop(tmp_path)
    d.start()
    try:
        page = Page(d)
        page.evaluate("localStorage.setItem('filefold.tour', 'dismissed'); toggleTheme()")
        chosen = page.evaluate("document.documentElement.dataset.theme")
        page.close()
    finally:
        d.stop()
    d.start()                                   # same data folder, same port
    try:
        page = Page(d)
        assert page.evaluate("localStorage.getItem('filefold.tour')") == "dismissed"
        assert page.evaluate("document.documentElement.dataset.theme") == chosen
        page.close()
    finally:
        d.stop()
