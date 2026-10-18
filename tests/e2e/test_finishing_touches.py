"""The finishing touches of the refined look: empty home, compact upload bar, rows that open
their file, finer splits only under ticked categories, consistent wording."""
from __future__ import annotations

import re

from playwright.sync_api import Page, expect

from .test_ui import create, open_new_workspace, upload
from .test_workflows import row


def make_workspace(page: Page, *cats: str) -> None:
    open_new_workspace(page)
    upload(page, "Job-1.inp")
    for cat in cats:
        page.locator(f"#sel-{cat}").check()
    create(page)


def test_empty_home_explains_and_offers_a_sample(app):
    empty = app.locator("#home-cards .empty")
    expect(empty).to_contain_text("No workspaces yet")
    expect(empty).to_contain_text("mother file")
    empty.get_by_role("button", name="Try a sample").click()
    expect(app.locator("#view-new-workspace")).to_be_visible()
    expect(app.locator("#upload-zone")).to_contain_text("Job-1.inp", timeout=30_000)
    expect(app.locator("#inspector-tree .tree-node").first).to_be_visible()


def test_a_loaded_file_shrinks_the_drop_zone_to_one_line_and_can_be_changed(app):
    open_new_workspace(app)
    upload(app, "Job-1.inp")
    zone = app.locator("#upload-zone")
    expect(zone).to_have_class(re.compile(r"\bloaded\b"))
    expect(zone).to_contain_text("blocks detected")
    assert zone.bounding_box()["height"] < 60, "one line, not the big drop box"
    with app.expect_file_chooser() as chooser:
        zone.get_by_role("link", name="Change file").click()
    assert chooser.value is not None


def test_the_drop_zone_is_full_size_again_after_a_reset(app):
    open_new_workspace(app)
    upload(app, "Job-1.inp")
    create(app)
    app.locator("#panel-workspaces .panel-act[aria-label='New workspace']").click()
    zone = app.locator("#upload-zone")
    expect(zone).not_to_have_class(re.compile(r"\bloaded\b"))
    expect(zone).to_contain_text("Drop")


def test_a_files_row_opens_its_file_and_shows_it_on_hover(app):
    make_workspace(app, "mesh")
    mesh = row(app, "mesh.inp")
    expect(mesh.get_by_role("button", name="View / Edit")).to_have_count(0)
    hint = mesh.locator(".open-hint")
    expect(hint).to_have_css("opacity", "0")
    before = mesh.locator("td").nth(4).evaluate("el => getComputedStyle(el).backgroundColor")
    mesh.hover()
    expect(hint).to_have_css("opacity", "1")
    expect(mesh).to_have_css("cursor", "pointer")
    after = mesh.locator("td").nth(4).evaluate("el => getComputedStyle(el).backgroundColor")
    assert before != after, "hovering a row must visibly highlight it"
    mesh.locator("td").nth(4).click()              # the line count, not the name
    expect(app.locator("#editor-body")).to_be_visible(timeout=30_000)
    expect(app.locator("#editor-filename")).to_contain_text("mesh.inp")


def test_the_download_icon_does_not_open_the_file(app):
    make_workspace(app, "mesh")
    app.evaluate("delete Window.prototype.showSaveFilePicker; delete window.showSaveFilePicker")
    with app.expect_download():
        row(app, "mesh.inp").get_by_role("button", name="Download mesh.inp").click()
    expect(app.locator("#view-detail")).to_be_visible()
    expect(app.locator("#editor-body")).to_be_hidden()


def test_the_file_name_is_a_keyboard_target(app):
    make_workspace(app, "mesh")
    name = row(app, "mesh.inp").locator(".filename-open")
    name.focus()
    app.keyboard.press("Enter")
    expect(app.locator("#editor-body")).to_be_visible(timeout=30_000)


def test_finer_splits_show_only_under_ticked_categories_on_the_splits_tab(app):
    make_workspace(app, "mesh")
    app.locator("#tab-btn-splits").click()
    mesh_row = app.locator("#ws-split-config .split-row", has=app.locator("#ws-sel-mesh"))
    expect(mesh_row.locator(".sub-options")).to_be_visible()
    app.locator("#ws-sel-mesh").uncheck()
    expect(mesh_row.locator(".sub-options")).to_be_hidden()
    app.locator("#ws-sel-mesh").check()
    expect(mesh_row.locator(".sub-options")).to_be_visible()


def test_wording_matches_across_home_and_files(app):
    make_workspace(app, "mesh")
    expect(app.locator("#detail-meta")).to_contain_text(re.compile(r"Updated \d{1,2} [A-Z][a-z]{2}, \d\d:\d\d"))
    app.get_by_role("button", name="← Back").first.click()
    expect(app.locator(".sheet-title")).to_have_text("All workspaces")
    expect(app.locator("#sheet-foot-right")).to_contain_text("1 workspace ·")
    expect(app.locator(".sheet-foot")).to_contain_text("Abaqus .inp parser")
