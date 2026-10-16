"""Saving: per-file downloads and Export ZIP into a folder remembered per workspace.

Headless Chromium cannot click through a real folder dialog, so the picker is replaced by
one that hands out real folder handles from the browser's private file system (OPFS);
everything after the pick (permission, IndexedDB, writing, replacing) is the real code.
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

# A picker that returns OPFS folders by name (queue them in window.__nextFolders), counts its
# calls, and a confirm() that records each question and answers from window.__confirmAnswer.
STUBS = """() => {
  window.__picks = 0; window.__nextFolders = []; window.__asked = []; window.__confirmAnswer = true;
  window.showDirectoryPicker = async () => {
    window.__picks++;
    const name = window.__nextFolders.shift();
    if (!name) throw new DOMException("The user aborted a request.", "AbortError");
    const root = await navigator.storage.getDirectory();
    return root.getDirectoryHandle(name, { create: true });
  };
  window.confirm = q => { window.__asked.push(q); return window.__confirmAnswer; };
}"""


def stub_picker(page: Page, *folders: str) -> None:
    page.evaluate(STUBS)
    page.evaluate("names => window.__nextFolders.push(...names)", list(folders))


def opfs_read(page: Page, folder: str, name: str) -> str | None:
    """Text of a file in an OPFS folder (zip as a JSON list of its member names)."""
    return page.evaluate("""async ([folder, name]) => {
      const root = await navigator.storage.getDirectory();
      try {
        const file = await (await (await root.getDirectoryHandle(folder)).getFileHandle(name)).getFile();
        if (name.endsWith('.zip')) return 'zip:' + btoa(String.fromCharCode(...new Uint8Array(await file.arrayBuffer())));
        return await file.text();
      } catch { return null; }
    }""", [folder, name])


def opfs_write(page: Page, folder: str, name: str, text: str) -> None:
    page.evaluate("""async ([folder, name, text]) => {
      const root = await navigator.storage.getDirectory();
      const dir = await root.getDirectoryHandle(folder, { create: true });
      const w = await (await dir.getFileHandle(name, { create: true })).createWritable();
      await w.write(text); await w.close();
    }""", [folder, name, text])


def zip_names(data: str) -> list[str]:
    return zipfile.ZipFile(io.BytesIO(base64.b64decode(data[4:]))).namelist()


def wait_for_toast(page: Page, text: str) -> None:
    expect(page.locator(".toast", has_text=text).last).to_be_visible(timeout=60_000)


@pytest.fixture()
def ws(persistent_app):
    make_workspace(persistent_app, "Job-1.inp", cats=("mesh", "material"))
    stub_picker(persistent_app)
    return persistent_app


def test_first_export_asks_for_a_folder_then_every_save_goes_there(ws):
    ws.evaluate("window.__nextFolders.push('exports')")
    folder_btn = ws.locator("#save-folder-btn")
    expect(folder_btn).to_contain_text("Choose folder")
    ws.get_by_role("button", name="⬇ Export ZIP").click()
    wait_for_toast(ws, 'Saved Job-1.zip to "exports"')
    assert {"Job-1.inp", "mesh.inp", "material.inp"} <= set(zip_names(opfs_read(ws, "exports", "Job-1.zip")))
    expect(folder_btn).to_contain_text("exports")
    # A single file goes to the same folder without asking again.
    row(ws, "mesh.inp").get_by_role("button", name="Download mesh.inp").click()
    wait_for_toast(ws, 'Saved mesh.inp to "exports"')
    assert opfs_read(ws, "exports", "mesh.inp") == fetch_text(ws, "/api/workspaces/Job-1/files/mesh.inp")
    assert ws.evaluate("window.__picks") == 1
    # The folder is remembered across a reload.
    ws.reload(); ws.wait_for_load_state("networkidle")
    if TARGET == "static":
        ws.wait_for_selector("#static-banner", state="detached", timeout=90_000)
    stub_picker(ws)
    ws.evaluate("openWorkspace('Job-1')")
    expect(folder_btn).to_contain_text("exports")
    row(ws, "material.inp").get_by_role("button", name="Download material.inp").click()
    wait_for_toast(ws, 'Saved material.inp to "exports"')
    assert ws.evaluate("window.__picks") == 0


def test_a_file_already_in_the_folder_is_only_replaced_when_confirmed(ws):
    opfs_write(ws, "project", "Job-1.inp", "the original deck")
    ws.evaluate("window.__nextFolders.push('project'); window.__confirmAnswer = false")
    row(ws, "Job-1.inp").get_by_role("button", name="Download Job-1.inp").click()
    ws.wait_for_function("window.__asked.length === 1")
    assert ws.evaluate("window.__asked[0]") == '"Job-1.inp" is already in "project". Replace it?'
    assert opfs_read(ws, "project", "Job-1.inp") == "the original deck"
    ws.evaluate("window.__confirmAnswer = true")
    row(ws, "Job-1.inp").get_by_role("button", name="Download Job-1.inp").click()
    wait_for_toast(ws, 'Saved Job-1.inp to "project"')
    assert opfs_read(ws, "project", "Job-1.inp") == fetch_text(ws, "/api/workspaces/Job-1/files/Job-1.inp")


def test_the_folder_button_sets_or_changes_the_folder_without_exporting(ws):
    ws.evaluate("window.__nextFolders.push('first', 'second')")
    ws.locator("#save-folder-btn").click()
    expect(ws.locator("#save-folder-btn")).to_contain_text("first")
    ws.locator("#save-folder-btn").click()
    expect(ws.locator("#save-folder-btn")).to_contain_text("second")
    assert opfs_read(ws, "first", "Job-1.zip") is None
    ws.get_by_role("button", name="⬇ Export ZIP").click()
    wait_for_toast(ws, 'Saved Job-1.zip to "second"')
    # Canceling the dialog keeps the folder that was set.
    ws.locator("#save-folder-btn").click()
    ws.wait_for_function("window.__picks === 3")
    expect(ws.locator("#save-folder-btn")).to_contain_text("second")


def test_canceling_the_first_folder_dialog_saves_nothing_and_shows_no_error(ws):
    ws.get_by_role("button", name="⬇ Export ZIP").click()
    ws.wait_for_function("window.__picks === 1")
    expect(ws.locator(".toast")).to_have_count(0)
    expect(ws.locator("#save-folder-btn")).to_contain_text("Choose folder")


def test_the_editor_download_saves_to_the_workspace_folder(ws):
    ws.evaluate("window.__nextFolders.push('exports')")
    row(ws, "mesh.inp").get_by_role("button", name="View / Edit").click()
    expect(ws.locator("#editor-body")).to_be_visible(timeout=30_000)
    ws.locator("#editor-download").click()
    wait_for_toast(ws, 'Saved mesh.inp to "exports"')


def test_browsers_without_a_folder_picker_get_an_ordinary_download(app):
    make_workspace(app, "Job-1.inp", cats=("mesh",))
    app.evaluate("delete window.showDirectoryPicker; delete Window.prototype.showDirectoryPicker")
    app.evaluate("openWorkspace('Job-1')")
    expect(app.locator("#detail-files tr").first).to_be_visible()
    expect(app.locator("#save-folder-btn")).to_be_hidden()
    with app.expect_download() as dl:
        row(app, "mesh.inp").get_by_role("button", name="Download mesh.inp").click()
    assert dl.value.suggested_filename == "mesh.inp"
    with app.expect_download() as dl:
        app.get_by_role("button", name="⬇ Export ZIP").click()
    assert dl.value.suggested_filename == "Job-1.zip"


def test_a_renamed_workspace_keeps_its_folder(ws):
    ws.evaluate("window.__nextFolders.push('exports')")
    ws.locator("#save-folder-btn").click()
    expect(ws.locator("#save-folder-btn")).to_contain_text("exports")
    ws.evaluate("showView('home')")
    card = ws.locator(".workspace-card[data-ws='Job-1']")
    card.hover()
    card.get_by_role("button", name="Rename").click()
    ws.locator("#ws-rename-input").fill("Bracket")
    ws.locator("#ws-rename-input").press("Enter")
    wait_for_toast(ws, 'Renamed to "Bracket"')
    ws.evaluate("openWorkspace('Bracket')")
    expect(ws.locator("#save-folder-btn")).to_contain_text("exports")


@pytest.mark.skipif(TARGET == "static", reason="the desktop app always uses the server build")
def test_desktop_app_saves_through_the_app_and_asks_before_replacing(app, base_url):
    """In the desktop window the app itself saves (native folder dialog); its routes exist
    only there, so they are played here by the test and the page's requests checked."""
    make_workspace(app, "Job-1.inp", cats=("mesh",))
    calls = []
    folder = "/Users/me/Projects/bracket"
    chosen = {"dir": None}                    # set by the first save, as the app's dialog would

    def desktop(route):
        req = route.request
        body = json.loads(req.post_data or "{}") if req.method == "POST" else None
        calls.append((req.method, req.url.split("/api/desktop/workspaces/")[1], body))
        if req.url.endswith("/save-dir"):
            return route.fulfill(json={"dir": chosen["dir"]})
        chosen["dir"] = folder
        if body.get("filename") == "mesh.inp" and not body.get("replace"):
            return route.fulfill(json={"saved": None, "exists": True, "dir": folder})
        leaf = body.get("filename") or "Job-1.zip"
        return route.fulfill(json={"saved": f"{folder}/{leaf}", "dir": folder})

    app.route("**/api/desktop/**", desktop)
    app.goto(base_url + "/?desktop=1")
    app.wait_for_load_state("networkidle")
    app.evaluate(STUBS)                                   # only to record confirm()
    app.evaluate("openWorkspace('Job-1')")
    expect(app.locator("#save-folder-btn")).to_contain_text("Choose folder")
    app.get_by_role("button", name="⬇ Export ZIP").click()
    wait_for_toast(app, f"Saved Job-1.zip to {folder}")
    expect(app.locator("#save-folder-btn")).to_contain_text("bracket")
    row(app, "mesh.inp").get_by_role("button", name="Download mesh.inp").click()
    wait_for_toast(app, f"Saved mesh.inp to {folder}")
    assert app.evaluate("window.__asked") == [f'"mesh.inp" is already in {folder}. Replace it?']
    posts = [(u, b) for m, u, b in calls if m == "POST"]
    assert posts == [("Job-1/save", {}), ("Job-1/save", {"filename": "mesh.inp"}),
                     ("Job-1/save", {"filename": "mesh.inp", "replace": True})]
