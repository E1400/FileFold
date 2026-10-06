"""Browser end-to-end fixtures.

Same rule as the barnes-maze-pipeline suite: every test fails on ANY console error,
uncaught page exception, or failed /api call, so a regression like a deleted JS
constant cannot slip through just because the test happened to assert something else.

Two targets, selected with FILEFOLD_E2E_TARGET (default "server"):

* server — a real uvicorn process (the entry point `filefold serve` uses) with an
  isolated workspace directory.
* static — the GitHub Pages build (scripts/build_pages.py) served over plain HTTP, with
  FileFold's Python running in the browser under Pyodide.

The same tests run against both; headless Chromium drives either.
"""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
ROOT = Path(__file__).resolve().parents[2]
TARGET = os.environ.get("FILEFOLD_E2E_TARGET", "server")
assert TARGET in {"server", "static"}, f"FILEFOLD_E2E_TARGET must be server or static, got {TARGET!r}"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def workspace_dir(tmp_path_factory) -> Path:
    return tmp_path_factory.mktemp("e2e-workspaces")


def _spawn(cmd: list[str], log: Path, env: dict | None = None) -> subprocess.Popen:
    """Start a server with its output going to a file.

    Never PIPE a long-lived server's output without draining it: http.server logs every
    request, the pipe buffer fills after a few hundred, and the server then blocks.
    """
    return subprocess.Popen(cmd, env=env, stdout=open(log, "wb"), stderr=subprocess.STDOUT)


def _wait_for(url: str, proc: subprocess.Popen, log: Path, what: str) -> None:
    deadline = time.time() + 60
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=1)
            return
        except OSError:
            if proc.poll() is not None:
                raise RuntimeError(log.read_text())
            time.sleep(0.2)
    proc.kill()
    raise RuntimeError(f"{what} did not start:\n{log.read_text()}")


@pytest.fixture(scope="session")
def base_url(workspace_dir, tmp_path_factory) -> str:
    if TARGET == "static":
        sys.path.insert(0, str(ROOT / "scripts"))
        import build_pages
        site = build_pages.build(tmp_path_factory.mktemp("site") / "site")
        port = _free_port()
        log = site.parent / "static-server.log"
        proc = _spawn([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1",
                       "--directory", str(site)], log)
        url = f"http://127.0.0.1:{port}/app/"
        _wait_for(url, proc, log, "static file server")
        yield url
        proc.terminate()
        proc.wait(timeout=10)
        return
    port = _free_port()
    env = {**os.environ, "FILEFOLD_WORKSPACE_DIR": str(workspace_dir)}
    log = workspace_dir.parent / "uvicorn.log"
    proc = _spawn([sys.executable, "-m", "uvicorn", "filefold.api.main:app",
                   "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"], log, env)
    url = f"http://127.0.0.1:{port}"
    _wait_for(url, proc, log, "FileFold server")
    yield url
    proc.terminate()
    proc.wait(timeout=10)


@pytest.fixture(autouse=True)
def clean_workspaces(workspace_dir):
    """Each test starts with no workspaces."""
    for child in workspace_dir.iterdir():
        shutil.rmtree(child, ignore_errors=True)
    yield


@pytest.fixture()
def app(page, base_url):
    """A page on the app that fails the test on any browser-side error."""
    errors: list[str] = []
    page.on("console", lambda m: errors.append(f"console.error: {m.text}") if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
    # Real HTTP errors (server target). The static build has no network /api; its fetch
    # shim logs the same failures as console errors, which are captured above.
    page.on("response", lambda r: errors.append(f"HTTP {r.status} {r.request.method} {r.url}")
            if r.url.startswith(base_url.rstrip("/") + "/api") and r.status >= 400 else None)
    page.on("dialog", lambda d: d.accept())
    page.set_viewport_size({"width": 1400, "height": 900})
    # New visitors are offered a guided tour. Mark it dismissed on the very first load so the
    # offer does not float over unrelated tests; tour tests remove the key to look like a
    # first-time visitor (it is not re-seeded on reload).
    page.add_init_script(
        "try { if (!localStorage.getItem('ff_seeded')) { localStorage.setItem('ff_seeded', '1');"
        " localStorage.setItem('filefold.tour', 'dismissed'); } } catch (e) {}"
    )
    if TARGET == "static":
        # Python runs in the page's own process here, so a loaded machine (the whole suite
        # running back to back) needs a longer patience than the server target.
        page.set_default_timeout(60_000)
    page.goto(base_url)
    page.wait_for_load_state("networkidle")
    if TARGET == "static":   # Python is starting in a worker; the banner goes away when ready
        page.wait_for_selector("#static-banner", state="detached", timeout=90_000)
    page.expected_errors = errors  # tests that deliberately provoke an error clear this
    yield page
    assert errors == [], "browser-side errors:\n" + "\n".join(errors)


def fixture_path(name: str) -> Path:
    return FIXTURES / name


def fetch_text(page, path: str) -> str:
    """GET an /api path from inside the page, so it works for both targets."""
    return page.evaluate("p => fetch(p).then(r => r.text())", path)


def fail_file_saves(page) -> None:
    """Make every file save (PUT .../files/...) fail with a 500, in either target."""
    page.evaluate("""() => {
      const real = window.fetch;
      window.fetch = (url, init) => (init && init.method === "PUT" && /\\/files\\//.test(String(url)))
        ? Promise.resolve(new Response("disk full", { status: 500 }))
        : real(url, init);
    }""")
