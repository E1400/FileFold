"""Browser end-to-end fixtures.

Same rule as the barnes-maze-pipeline suite: every test fails on ANY console error,
uncaught page exception, or failed /api call, so a regression like a deleted JS
constant cannot slip through just because the test happened to assert something else.

Runs against a real uvicorn process (the same entry point `filefold serve` uses)
with an isolated workspace directory, driven by headless Chromium.
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


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def workspace_dir(tmp_path_factory) -> Path:
    return tmp_path_factory.mktemp("e2e-workspaces")


@pytest.fixture(scope="session")
def base_url(workspace_dir) -> str:
    port = _free_port()
    env = {**os.environ, "FILEFOLD_WORKSPACE_DIR": str(workspace_dir)}
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "filefold.api.main:app",
         "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    url = f"http://127.0.0.1:{port}"
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=1)
            break
        except OSError:
            if proc.poll() is not None:
                raise RuntimeError(proc.stdout.read().decode())
            time.sleep(0.2)
    else:
        proc.kill()
        raise RuntimeError("FileFold server did not start")
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
    page.on("response", lambda r: errors.append(f"HTTP {r.status} {r.request.method} {r.url}")
            if r.url.startswith(base_url + "/api") and r.status >= 400 else None)
    page.on("dialog", lambda d: d.accept())
    page.set_viewport_size({"width": 1400, "height": 900})
    page.goto(base_url)
    page.wait_for_load_state("networkidle")
    page.expected_errors = errors  # tests that deliberately provoke an error clear this
    yield page
    assert errors == [], "browser-side errors:\n" + "\n".join(errors)


def fixture_path(name: str) -> Path:
    return FIXTURES / name
