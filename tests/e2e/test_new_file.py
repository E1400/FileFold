"""New file from the Files tab: an empty file the mother *INCLUDEs, opened in the editor,
listed as added, and folded back on request."""
from __future__ import annotations

from playwright.sync_api import expect

from .conftest import fetch_text
from .test_workflows import make_workspace, row


def mother(page) -> str:
    return fetch_text(page, "/api/workspaces/Job-1/files/Job-1.inp")


def new_file(page, name: str) -> None:
    page.get_by_role("button", name="+ New file").click()
    page.locator("#new-file-name").fill(name)
    page.locator("#new-file-form").get_by_role("button", name="Create").click()


def test_new_file_opens_empty_in_the_editor_and_the_mother_includes_it_before_the_step(app):
    make_workspace(app, "Job-1.inp", cats=("mesh", "step"))
    new_file(app, "extra-loads")
    expect(app.locator(".toast", has_text="Created extra-loads.inp")).to_be_visible()
    expect(app.locator("#editor-body")).to_be_visible(timeout=30_000)
    expect(app.locator("#editor-filename")).to_have_text("extra-loads.inp")
    expect(app.locator("#editor-ta")).to_have_value("")
    text = mother(app)
    assert "*INCLUDE, INPUT=extra-loads.inp" in text
    assert text.index("INPUT=mesh.inp") < text.index("INPUT=extra-loads.inp") < text.index("INPUT=step.inp")

    app.locator("#view-editor").get_by_role("button", name="← Back").click()
    added = row(app, "extra-loads.inp")
    expect(added).to_contain_text("added")
    expect(added).to_contain_text("clean")
    expect(row(app, "Job-1.inp")).to_contain_text("clean")        # FileFold's change, not an edit
    expect(app.locator("#new-file-form")).to_be_hidden()
    expect(app.get_by_role("button", name="+ New file")).to_have_attribute("aria-expanded", "false")
    # the sidebar tree lists it too, in deck order
    tree = app.locator("#ws-list .ws-file").all_inner_texts()
    assert [t.strip() for t in tree].index("extra-loads.inp") < [t.strip() for t in tree].index("step.inp")


def test_written_new_file_folds_into_the_mother(app):
    make_workspace(app, "Job-1.inp", cats=("mesh", "step"))
    new_file(app, "amplitudes.inp")
    ta = app.locator("#editor-ta")
    expect(ta).to_be_visible(timeout=30_000)
    ta.click()
    app.keyboard.type("*AMPLITUDE, NAME=RAMP\n0., 0., 1., 1.\n")
    app.locator("#editor-save-btn").click()
    expect(app.locator(".toast", has_text="Saved amplitudes.inp")).to_be_visible()
    app.locator("#view-editor").get_by_role("button", name="← Back").click()

    row(app, "amplitudes.inp").get_by_role("button", name="Fold into mother").click()
    expect(app.locator(".toast", has_text="Folded amplitudes.inp")).to_be_visible()
    expect(row(app, "amplitudes.inp")).to_have_count(0)
    expect(app.locator("#editor-body")).to_be_hidden()              # the button does not open the file
    text = mother(app)
    assert "INPUT=amplitudes.inp" not in text
    assert text.index("*AMPLITUDE, NAME=RAMP") < text.index("INPUT=step.inp")


def test_new_file_is_a_small_button_under_the_table_whose_box_pops_up(app):
    make_workspace(app, "Job-1.inp", cats=("mesh",))
    expect(row(app, "mesh.inp").get_by_role("button", name="Fold into mother")).to_have_count(0)
    btn = app.get_by_role("button", name="+ New file")
    form = app.locator("#new-file-form")
    expect(form).to_be_hidden()                                   # nothing waits for input
    table = app.locator(".file-table").bounding_box()
    assert btn.bounding_box()["y"] >= table["y"] + table["height"], "the button sits under the table"
    btn.click()
    expect(form).to_be_visible()
    expect(btn).to_have_attribute("aria-expanded", "true")
    expect(app.locator("#new-file-name")).to_be_focused()
    app.keyboard.press("Escape")
    expect(form).to_be_hidden()
    expect(btn).to_be_focused()
    btn.click()
    form.get_by_role("button", name="Cancel").click()
    expect(form).to_be_hidden()
    btn.click()
    app.locator("#detail-meta").click()                            # a click outside closes it
    expect(form).to_be_hidden()
    expect(btn).to_have_attribute("aria-expanded", "false")
    btn.click()
    btn.click()                                                   # the button toggles it
    expect(form).to_be_hidden()


def test_a_name_that_breaks_an_include_or_is_taken_is_shown_on_the_field(app):
    make_workspace(app, "Job-1.inp", cats=("mesh",))
    app.expected_errors.clear()                                   # the server's 400s are the point
    new_file(app, "my loads.inp")
    field = app.locator("#new-file-name")
    expect(field).to_have_attribute("aria-invalid", "true")
    expect(app.locator("#new-file-form")).to_contain_text("can't be used in an *INCLUDE")
    field.fill("mesh.inp")
    app.locator("#new-file-form").get_by_role("button", name="Create").click()
    expect(app.locator("#new-file-form")).to_contain_text("already called")
    app.expected_errors.clear()
    assert "my loads" not in mother(app) and mother(app).count("INPUT=mesh.inp") == 1


def test_the_splits_preview_keeps_the_added_file_in_its_place(app):
    make_workspace(app, "Job-1.inp", cats=("mesh", "step"))
    new_file(app, "extra.inp")
    expect(app.locator("#editor-body")).to_be_visible(timeout=30_000)
    app.locator("#view-editor").get_by_role("button", name="← Back").click()
    app.locator("#tab-btn-splits").click()
    tree = app.locator("#ws-result-tree")
    expect(tree.locator(".result-row[data-file='extra.inp']")).to_contain_text("added")
    names = tree.locator(".result-row").evaluate_all("els => els.map(e => e.dataset.file)")
    assert names.index("mesh.inp") < names.index("extra.inp") < names.index("step.inp")
