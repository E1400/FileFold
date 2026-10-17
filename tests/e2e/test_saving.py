"""Saving: Export ZIP and single-file downloads open a Save dialog every time, starting where
the workspace was last saved (the browser remembers the folder per picker id).

Headless Chromium cannot click through a real Save dialog, so the picker is replaced by one
that records what it was asked and hands out real file handles from the browser's private
file system (OPFS); everything after the pick (fetching, writing) is the real code.
"""
from __future__ import annotations

import base64
import io
import json
import zipfile

import pytest
from playwright.sync_api import Page, expect

from .conftest import TARGET, fetch_text
from .test_workflows import make_workspace, row

STUB = """() => {
  window.__asked = []; window.__cancel = false;
  window.showSaveFilePicker = async opts => {
    window.__asked.push(JSON.parse(JSON.stringify(opts)));
    if (window.__cancel) throw new DOMException("The user aborted a request.", "AbortError");
    const root = await navigator.storage.getDirectory();
    const dir = await root.getDirectoryHandle("picked", { create: true });
    return dir.getFileHandle(opts.suggestedName, { create: true });
  };
}"""


def saved(page: Page, name: str) -> bytes | None:
    data = page.evaluate("""async name => {
      try {
        const root = await navigator.storage.getDirectory();
        const file = await (await (await root.getDirectoryHandle("picked")).getFileHandle(name)).getFile();
        return btoa(String.fromCharCode(...new Uint8Array(await file.arrayBuffer())));
      } catch { return null; }
    }""", name)
    return base64.b64decode(data) if data is not None else None


def toast(page: Page, text: str) -> None:
    expect(page.locator(".toast", has_text=text).last).to_be_visible(timeout=60_000)


@pytest.fixture()
def ws(app):
    make_workspace(app, "Job-1.inp", cats=("mesh", "material"))
    app.evaluate(STUB)
    return app


def test_export_zip_asks_where_to_save_every_time(ws):
    for _ in range(2):
        ws.get_by_role("button", name="⬇ Export ZIP").click()
        toast(ws, "Saved Job-1.zip")
    asked = ws.evaluate("window.__asked")
    assert len(asked) == 2
    assert asked[0]["suggestedName"] == "Job-1.zip"
    assert asked[0]["types"][0]["accept"] == {"application/zip": [".zip"]}
    names = zipfile.ZipFile(io.BytesIO(saved(ws, "Job-1.zip"))).namelist()
    assert {"Job-1.inp", "mesh.inp", "material.inp"} <= set(names)
    # There is one way to choose the location: the Save dialog. No separate folder button.
    expect(ws.locator("#save-folder-btn")).to_have_count(0)


def test_a_single_file_opens_in_the_same_place_as_the_export(ws):
    """The browser remembers the last folder per picker id: one id per workspace, shared by
    its export and its single files, different for another workspace."""
    ws.get_by_role("button", name="⬇ Export ZIP").click()
    toast(ws, "Saved Job-1.zip")
    button = row(ws, "mesh.inp").get_by_role("button", name="Download mesh.inp")
    expect(button).to_have_text("⬇")                      # the symbol, not the word
    button.click()
    toast(ws, "Saved mesh.inp")
    assert saved(ws, "mesh.inp").decode() == fetch_text(ws, "/api/workspaces/Job-1/files/mesh.inp")
    export, single = ws.evaluate("window.__asked")
    assert single["suggestedName"] == "mesh.inp" and "types" not in single
    assert export["id"] == single["id"] and len(export["id"]) <= 32
    assert ws.evaluate("savePickerId('Job-1')") != ws.evaluate("savePickerId('Job-2')")
    assert ws.evaluate("/^[A-Za-z0-9_-]{1,32}$/.test(savePickerId('a very long workspace name, with punctuation & ünïcode'))")


def test_canceling_the_save_dialog_saves_nothing_and_shows_no_error(ws):
    ws.evaluate("window.__cancel = true")
    ws.get_by_role("button", name="⬇ Export ZIP").click()
    ws.wait_for_function("window.__asked.length === 1")
    expect(ws.locator(".toast")).to_have_count(0)
    assert saved(ws, "Job-1.zip") is None


def test_the_editor_download_uses_the_same_save_dialog(ws):
    row(ws, "mesh.inp").get_by_role("button", name="View / Edit").click()
    expect(ws.locator("#editor-body")).to_be_visible(timeout=30_000)
    ws.locator("#editor-download").click()
    toast(ws, "Saved mesh.inp")


def test_home_card_export_uses_the_save_dialog(ws):
    ws.evaluate("showView('home')")
    card = ws.locator(".workspace-card[data-ws='Job-1']")
    card.hover()
    card.get_by_role("button", name="Export").click()
    toast(ws, "Saved Job-1.zip")


def test_browsers_without_a_save_dialog_get_an_ordinary_download(app):
    make_workspace(app, "Job-1.inp", cats=("mesh",))
    app.evaluate("delete Window.prototype.showSaveFilePicker; delete window.showSaveFilePicker")
    with app.expect_download() as dl:
        row(app, "mesh.inp").get_by_role("button", name="Download mesh.inp").click()
    assert dl.value.suggested_filename == "mesh.inp"
    with app.expect_download() as dl:
        app.get_by_role("button", name="⬇ Export ZIP").click()
    assert dl.value.suggested_filename == "Job-1.zip"


@pytest.mark.skipif(TARGET == "static", reason="the desktop app always uses the server build")
def test_desktop_app_saves_through_the_apps_own_save_dialog(app, base_url):
    """In the desktop window the app shows a native Save dialog and writes the file; its route
    exists only there, so it is played here by the test and the page's requests checked."""
    make_workspace(app, "Job-1.inp", cats=("mesh",))
    posts = []
    folder = "/Users/me/Projects/bracket"

    def desktop(route):
        body = json.loads(route.request.post_data or "{}")
        posts.append(body)
        leaf = body.get("filename") or "Job-1.zip"
        return route.fulfill(json={"saved": f"{folder}/{leaf}", "dir": folder})

    app.route("**/api/desktop/workspaces/Job-1/save", desktop)
    app.goto(base_url + "/?desktop=1")
    app.wait_for_load_state("networkidle")
    app.evaluate("openWorkspace('Job-1')")
    app.get_by_role("button", name="⬇ Export ZIP").click()
    toast(app, f"Saved Job-1.zip to {folder}")
    row(app, "mesh.inp").get_by_role("button", name="Download mesh.inp").click()
    toast(app, f"Saved mesh.inp to {folder}")
    assert posts == [{}, {"filename": "mesh.inp"}]
