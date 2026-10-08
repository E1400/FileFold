#!/usr/bin/env python3
"""Regenerate the app screenshots shown on the landing page (docs/img/*.png).

Runs the real app on a temporary port with a throw-away workspace folder, drives it with
headless Chromium (Playwright, a dev dependency) and captures two screens in the light and the
dark theme. Re-run after the app's look changes so the landing page never shows a stale UI:

    python scripts/make_landing_screenshots.py
"""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "img"
SIZE = {"width": 1280, "height": 800}


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    port, workspaces = free_port(), tempfile.mkdtemp()
    env = {**os.environ, "FILEFOLD_WORKSPACE_DIR": workspaces}
    log = open(Path(workspaces) / "server.log", "wb")
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "filefold.api.main:app", "--port", str(port), "--log-level", "warning"],
        env=env, stdout=log, stderr=subprocess.STDOUT,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(base, timeout=1)
                break
            except OSError:
                time.sleep(0.2)
        with sync_playwright() as p:
            browser = p.chromium.launch()
            for scheme in ("light", "dark"):
                page = browser.new_page(viewport=SIZE, color_scheme=scheme)
                # the guided-tour offer is for first-time visitors; keep it out of the pictures
                page.add_init_script("localStorage.setItem('filefold.tour', 'dismissed')")
                if scheme == "dark":
                    page.add_init_script("localStorage.setItem('filefold.theme', 'dark')")
                else:
                    page.add_init_script("localStorage.setItem('filefold.theme', 'light')")
                page.goto(base)
                page.wait_for_load_state("networkidle")

                # screen 1: a deck loaded, categories ticked, finer splits offered
                page.locator("button:visible", has_text="+ New").first.click()
                page.click("#sample-btn")
                page.locator("#sample-menu [data-sample='Job-1']").click()
                page.wait_for_selector("#split-config .split-row")
                for cat in ("mesh", "material", "step"):
                    page.locator(f"#sel-{cat}").check()
                page.locator("#sub-mesh-nodes").check()
                page.locator("#sub-mesh-elements").check()
                page.wait_for_timeout(300)
                page.screenshot(path=OUT / f"new-workspace-{scheme}.png")

                # screen 2: the resulting workspace
                page.locator("#create-btn-row button").click()
                page.wait_for_selector("#detail-files tr")
                page.wait_for_timeout(400)
                page.evaluate("document.getElementById('toast-container').innerHTML = ''")   # keep toasts out of the picture
                page.screenshot(path=OUT / f"workspace-{scheme}.png")
                page.close()
                # a clean slate for the next theme (the workspace name would clash)
                for child in Path(workspaces).iterdir():
                    if child.is_dir():
                        shutil.rmtree(child)
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)
    print("wrote", ", ".join(sorted(p.name for p in OUT.glob("*.png"))))


if __name__ == "__main__":
    main()
