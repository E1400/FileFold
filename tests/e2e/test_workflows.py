"""Multi-step workflows: editor, Splits tab, re-import. Same fail-on-any-error rule."""
from __future__ import annotations

import re
import tempfile
from pathlib import Path

from playwright.sync_api import Page, expect

from .conftest import fixture_path
from .test_ui import create, detail_files, open_new_workspace, upload


def make_workspace(page: Page, fixture: str, cats: tuple[str, ...] = ("mesh",), subs: tuple[str, ...] = ()) -> None:
    open_new_workspace(page)
    upload(page, fixture)
    for c in cats:
        page.locator(f"#sel-{c}").check()
    for s in subs:  # "cat:sub"
        c, sc = s.split(":")
        page.locator(f"#sub-{c}-{sc}").check()
    create(page)
    expect(page.locator("#detail-files tr").first).to_be_visible()


def row(page: Page, filename: str):
    return page.locator("#detail-files tr", has=page.locator(".filename-text", has_text=re.compile(f"^{re.escape(filename)}$")))


def open_file(page: Page, filename: str) -> None:
    row(page, filename).get_by_role("button", name="View / Edit").click()
    expect(page.locator("#editor-body")).to_be_visible(timeout=30_000)


def api_text(page: Page, ws: str, filename: str) -> str:
    return page.request.get(f"{page.url.split('#')[0].rstrip('/')}/api/workspaces/{ws}/files/{filename}").text()


# --- editor -----------------------------------------------------------------

def test_edit_and_save_marks_file_edited_and_persists(app):
    make_workspace(app, "Job-1.inp")
    open_file(app, "mesh.inp")
    ta = app.locator("#editor-ta")
    expect(ta).not_to_have_value("")
    ta.click()
    app.keyboard.type("** edited by e2e\n")
    expect(app.locator("#editor-save-btn")).to_be_visible()
    app.locator("#editor-save-btn").click()
    expect(app.locator(".toast", has_text="Saved mesh.inp")).to_be_visible()
    app.get_by_role("button", name="← Back").last.click()
    expect(row(app, "mesh.inp")).to_contain_text("edited")
    assert "** edited by e2e\r\n" in api_text(app, "Job-1", "mesh.inp")  # Job-1 is CRLF; the save keeps it


def test_failed_save_is_reported_not_claimed_as_saved(app):
    make_workspace(app, "Job-1.inp")
    open_file(app, "mesh.inp")
    app.route("**/api/workspaces/*/files/*", lambda r: r.fulfill(status=500, body="disk full")
              if r.request.method == "PUT" else r.continue_())
    app.locator("#editor-ta").click()
    app.keyboard.type("x")
    app.locator("#editor-save-btn").click()
    expect(app.locator(".toast", has_text="Save failed")).to_be_visible()
    expect(app.locator(".toast", has_text="Saved mesh.inp")).to_have_count(0)
    app.expected_errors.clear()  # the injected 500 is the point of this test


def test_large_mesh_file_opens_in_editor(app):
    make_workspace(app, "fempy_example.inp")  # ~5 MB deck
    open_file(app, "mesh.inp")
    assert len(app.locator("#editor-ta").input_value()) > 100_000
    expect(app.locator("#editor-gutter-inner")).not_to_be_empty()


# --- splits tab -------------------------------------------------------------

def test_splits_tab_extracts_more_categories(app):
    make_workspace(app, "Job-1.inp", cats=("mesh",))
    app.locator("#tab-btn-splits").click()
    app.locator("#ws-sel-material").check()
    app.locator("#ws-splits-apply-btn").click()
    app.locator("#tab-btn-files").click()
    assert "material.inp" in "\n".join(detail_files(app))
    assert "*INCLUDE" in api_text(app, "Job-1", "Job-1.inp")


def test_splits_tab_subsplit_mesh_nodes(app):
    make_workspace(app, "Job-1.inp", cats=("mesh",))
    app.locator("#tab-btn-splits").click()
    app.locator("#ws-sub-mesh-nodes").check()
    app.locator("#ws-splits-apply-btn").click()
    app.locator("#tab-btn-files").click()
    expect(row(app, "mesh-nodes.inp")).to_be_visible()
    assert "*NODE" in api_text(app, "Job-1", "mesh-nodes.inp").upper()


def test_splits_tab_can_merge_a_category_back(app):
    make_workspace(app, "Job-1.inp", cats=("mesh", "material"))
    app.locator("#tab-btn-splits").click()
    app.locator("#ws-sel-material").uncheck()
    app.locator("#ws-splits-apply-btn").click()
    app.locator("#tab-btn-files").click()
    expect(row(app, "material.inp")).to_have_count(0)
    assert "*MATERIAL" in api_text(app, "Job-1", "Job-1.inp").upper()


# --- re-import --------------------------------------------------------------

def test_reimport_unchanged_mother_updates_cleanly(app):
    make_workspace(app, "Job-1.inp", cats=("mesh", "material"))
    app.get_by_role("button", name="Re-import").click()
    app.set_input_files("#reimp-input", str(fixture_path("Job-1.inp")))
    expect(app.locator("#reimp-preview-section")).to_be_visible(timeout=30_000)
    expect(app.locator(".badge-warn", has_text="Conflict")).to_have_count(0)
    app.locator("#reimp-apply-btn").click()
    expect(app.locator(".toast", has_text="Reimport applied")).to_be_visible()


def test_reimport_flags_manual_edit_conflict(app):
    make_workspace(app, "Job-1.inp", cats=("mesh",))
    open_file(app, "mesh.inp")
    app.locator("#editor-ta").click()
    app.keyboard.type("** my edit\n")
    app.locator("#editor-save-btn").click()
    expect(app.locator(".toast", has_text="Saved mesh.inp")).to_be_visible()
    app.get_by_role("button", name="← Back").last.click()

    # New mother: same deck with the mesh changed, so mesh.inp differs from both.
    changed = Path(tempfile.mkdtemp()) / "Job-1.inp"
    text = fixture_path("Job-1.inp").read_text()
    changed.write_text(text.replace("*NODE", "*NODE ** changed upstream", 1))
    app.get_by_role("button", name="Re-import").click()
    app.set_input_files("#reimp-input", str(changed))
    expect(app.locator("#reimp-preview-section")).to_be_visible(timeout=30_000)
    expect(app.locator(".badge-warn", has_text="Conflict").first).to_be_visible()


# --- chrome -----------------------------------------------------------------

def test_theme_toggle_does_not_error(app):
    app.get_by_role("button", name="◑").click()
    app.get_by_role("button", name="◑").click()


# --- leaving the editor -----------------------------------------------------

def _go_back(page: Page) -> None:
    page.locator("#view-editor").get_by_role("button", name="← Back").click()


def _watch_native_dialogs(page: Page) -> list[str]:
    """The app must use its own dialog; any native alert/confirm is recorded and accepted."""
    seen: list[str] = []
    page.on("dialog", lambda d: seen.append(d.message))
    return seen


def test_back_without_edits_leaves_silently(app):
    native = _watch_native_dialogs(app)
    make_workspace(app, "mmxmn.inp")
    open_file(app, "mesh.inp")
    _go_back(app)
    expect(app.locator("#view-detail")).to_be_visible()
    expect(app.locator("#unsaved-dialog")).not_to_be_visible()
    assert native == []


def test_back_without_edits_leaves_silently_for_crlf_deck(app):
    """Job-1.inp uses CRLF; a textarea normalises it to LF, which used to look like an edit."""
    native = _watch_native_dialogs(app)
    make_workspace(app, "Job-1.inp")
    open_file(app, "mesh.inp")
    expect(app.locator("#unsaved-dot")).not_to_have_class(re.compile("visible"))
    _go_back(app)
    expect(app.locator("#view-detail")).to_be_visible()
    expect(app.locator("#unsaved-dialog")).not_to_be_visible()
    assert native == []


def test_back_with_edits_offers_save_discard_and_keep_editing(app):
    make_workspace(app, "mmxmn.inp")
    open_file(app, "mesh.inp")
    app.locator("#editor-ta").click()
    app.keyboard.type("** unsaved\n")
    _go_back(app)
    dialog = app.locator("#unsaved-dialog")
    expect(dialog).to_be_visible()
    for name in ("Save and close", "Discard changes", "Keep editing"):
        expect(dialog.get_by_role("button", name=name)).to_be_visible()


def test_back_with_edits_save_and_close_saves(app):
    make_workspace(app, "mmxmn.inp")
    open_file(app, "mesh.inp")
    app.locator("#editor-ta").click()
    app.keyboard.type("** keep me\n")
    _go_back(app)
    app.get_by_role("button", name="Save and close").click()
    expect(app.locator("#view-detail")).to_be_visible()
    expect(row(app, "mesh.inp")).to_contain_text("edited")
    assert "** keep me\n" in api_text(app, "mmxmn", "mesh.inp")


def test_back_with_edits_discard_does_not_save(app):
    make_workspace(app, "mmxmn.inp")
    open_file(app, "mesh.inp")
    app.locator("#editor-ta").click()
    app.keyboard.type("** throw away\n")
    _go_back(app)
    app.get_by_role("button", name="Discard changes").click()
    expect(app.locator("#view-detail")).to_be_visible()
    expect(row(app, "mesh.inp")).to_contain_text("clean")
    assert "** throw away" not in api_text(app, "mmxmn", "mesh.inp")


def test_back_with_edits_keep_editing_stays_put(app):
    make_workspace(app, "mmxmn.inp")
    open_file(app, "mesh.inp")
    app.locator("#editor-ta").click()
    app.keyboard.type("** still here\n")
    _go_back(app)
    app.get_by_role("button", name="Keep editing").click()
    expect(app.locator("#view-editor")).to_be_visible()
    expect(app.locator("#unsaved-dialog")).not_to_be_visible()
    assert "** still here" in app.locator("#editor-ta").input_value()


def test_escape_closes_the_dialog_like_keep_editing(app):
    make_workspace(app, "mmxmn.inp")
    open_file(app, "mesh.inp")
    app.locator("#editor-ta").click()
    app.keyboard.type("x")
    _go_back(app)
    app.keyboard.press("Escape")
    expect(app.locator("#unsaved-dialog")).not_to_be_visible()
    expect(app.locator("#view-editor")).to_be_visible()


def test_failed_save_from_dialog_keeps_the_editor_open(app):
    make_workspace(app, "mmxmn.inp")
    open_file(app, "mesh.inp")
    app.route("**/api/workspaces/*/files/*", lambda r: r.fulfill(status=500, body="disk full")
              if r.request.method == "PUT" else r.continue_())
    app.locator("#editor-ta").click()
    app.keyboard.type("x")
    _go_back(app)
    app.get_by_role("button", name="Save and close").click()
    expect(app.locator(".toast", has_text="Save failed")).to_be_visible()
    expect(app.locator("#view-editor")).to_be_visible()  # edits must not be lost
    app.expected_errors.clear()


# --- CRLF decks keep their line endings through an editor save --------------

def test_saving_a_crlf_deck_preserves_crlf(app):
    make_workspace(app, "Job-1.inp")
    open_file(app, "mesh.inp")
    app.locator("#editor-ta").click()
    app.keyboard.type("** edited\n")
    app.locator("#editor-save-btn").click()
    expect(app.locator(".toast", has_text="Saved mesh.inp")).to_be_visible()
    raw = app.request.get(f"{app.url.rstrip('/')}/api/workspaces/Job-1/files/mesh.inp").body()
    assert b"\r\n" in raw
    assert b"\n" not in raw.replace(b"\r\n", b"")  # no bare LF anywhere
