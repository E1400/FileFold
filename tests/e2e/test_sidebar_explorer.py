"""The Workspaces panel as a file explorer (UX review, proposal 2): a workspace expands into
its files, a click opens one in the editor while the tree stays visible, edited and missing
files are marked, and unsaved edits are never dropped by clicking elsewhere."""
from __future__ import annotations

from playwright.sync_api import Page, expect

from .test_workflows import make_workspace


def tree_file(page: Page, ws: str, filename: str):
    return page.locator(f".ws-tree[data-ws='{ws}'] .ws-file[data-file='{filename}']")


def test_the_open_workspace_lists_its_files_nested(app):
    make_workspace(app, "Job-1.inp", cats=("mesh", "material"), subs=("mesh:nodes",))
    files = app.locator(".ws-tree[data-ws='Job-1'] .ws-file")
    expect(files).to_have_count(4)
    names = [f.get_attribute("data-file") for f in files.all()]
    assert names[0] == "Job-1.inp"                                          # mother first
    assert names.index("mesh-nodes.inp") == names.index("mesh.inp") + 1     # sub-child under its child
    expect(app.locator(".ws-file.role-mother[data-file='Job-1.inp']")).to_have_count(1)
    expect(app.locator(".ws-file.role-grandchild[data-file='mesh-nodes.inp']")).to_have_count(1)


def test_a_click_opens_the_file_and_the_tree_stays(app):
    make_workspace(app, "Job-1.inp", cats=("mesh", "material"))
    tree_file(app, "Job-1", "material.inp").click()
    expect(app.locator("#view-editor")).to_be_visible()
    expect(app.locator("#editor-filename")).to_have_text("material.inp")
    expect(tree_file(app, "Job-1", "material.inp")).to_have_attribute("aria-current", "true")
    tree_file(app, "Job-1", "mesh.inp").click()                             # straight to the next file
    expect(app.locator("#editor-filename")).to_have_text("mesh.inp")
    expect(tree_file(app, "Job-1", "mesh.inp")).to_have_attribute("aria-current", "true")


def test_edited_files_are_marked_in_the_tree(app):
    make_workspace(app, "Job-1.inp", cats=("mesh", "material"))
    tree_file(app, "Job-1", "material.inp").click()
    app.locator("#editor-ta").click()
    app.keyboard.type("** note\n")
    app.locator("#editor-save-btn").click()
    expect(app.locator(".toast", has_text="Saved material.inp")).to_be_visible()
    # The tree refreshes after the save's file-list request returns: allow for a slow machine.
    expect(tree_file(app, "Job-1", "material.inp").locator(".file-mark")).to_have_attribute("title", "edited", timeout=15_000)
    expect(app.locator(".ws-item[data-ws='Job-1'] .ws-edited")).to_have_count(1)


def test_switching_files_with_unsaved_edits_asks_first(app):
    make_workspace(app, "Job-1.inp", cats=("mesh", "material"))
    tree_file(app, "Job-1", "material.inp").click()
    app.locator("#editor-ta").click()
    app.keyboard.type("** unsaved\n")
    tree_file(app, "Job-1", "mesh.inp").click()
    dialog = app.locator("#unsaved-dialog")
    expect(dialog).to_be_visible()
    dialog.get_by_role("button", name="Keep editing").click()
    expect(app.locator("#editor-filename")).to_have_text("material.inp")
    tree_file(app, "Job-1", "mesh.inp").click()
    dialog.get_by_role("button", name="Discard changes").click()
    expect(app.locator("#editor-filename")).to_have_text("mesh.inp")


def test_leaving_the_editor_from_the_sidebar_asks_about_unsaved_edits(app):
    make_workspace(app, "Job-1.inp", cats=("mesh",))
    tree_file(app, "Job-1", "mesh.inp").click()
    app.locator("#editor-ta").click()
    app.keyboard.type("** unsaved\n")
    app.get_by_role("button", name="New workspace", exact=True).first.click()
    expect(app.locator("#unsaved-dialog")).to_be_visible()
    app.locator("#unsaved-dialog").get_by_role("button", name="Keep editing").click()
    expect(app.locator("#view-editor")).to_be_visible()


def test_another_workspace_expands_without_opening_it(app):
    make_workspace(app, "Job-1.inp", cats=("mesh",))
    app.get_by_role("button", name="← Back").first.click()
    make_workspace(app, "test_2.inp", cats=())
    other = app.locator(".ws-item[data-ws='Job-1']")
    expect(app.locator(".ws-tree[data-ws='Job-1'] .ws-file")).to_have_count(0)  # closed: not the open one
    other.get_by_role("button", name="Show files").click()
    expect(app.locator(".ws-tree[data-ws='Job-1'] .ws-file")).to_have_count(2)
    expect(app.locator("#detail-title")).to_have_text("test_2")               # still on test_2
    tree_file(app, "Job-1", "mesh.inp").click()                              # opens it in its workspace
    expect(app.locator("#editor-filename")).to_have_text("mesh.inp")
    expect(app.locator(".ws-item.active[data-ws='Job-1']")).to_have_count(1)
