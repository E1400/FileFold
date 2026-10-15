"""Errors are shown like a web form's checks: the field that is wrong is outlined, the
problem is said in plain words right under it, and it gets focus. Anything else is an error
message that stays until it is closed. Raw server output is never shown."""
from __future__ import annotations

import tempfile
from pathlib import Path

from playwright.sync_api import Page, expect

from .conftest import fail_file_saves
from .test_ui import create, open_new_workspace, upload
from .test_workflows import make_workspace, open_file


def field_error(page: Page, field: str):
    """The message shown under a field (by the field's id)."""
    return page.locator(f"#{field} + .field-error")


def expect_field_error(page: Page, field: str, text: str) -> None:
    expect(page.locator(f"#{field}.field-invalid")).to_have_count(1)
    expect(field_error(page, field)).to_contain_text(text)


def go_home(page: Page) -> None:
    page.get_by_role("button", name="← Back").first.click()


def test_duplicate_workspace_name_highlights_the_name_field(app):
    make_workspace(app, "test_2.inp", cats=())
    go_home(app)
    open_new_workspace(app)
    upload(app, "test_2.inp")                                   # name defaults to "test_2" again
    app.locator("#create-btn-row button").click()
    expect_field_error(app, "ws-name-input", 'You already have a workspace called "test_2"')
    expect(app.locator("#ws-name-input")).to_be_focused()
    expect(app.locator(".toast.error")).to_have_count(0)        # said on the field, not in a pop-up
    app.locator("#ws-name-input").fill("test_2-b")             # typing clears the mark
    expect(app.locator("#ws-name-input.field-invalid")).to_have_count(0)
    expect(app.locator(".field-error")).to_have_count(0)
    create(app)


def test_name_taken_elsewhere_is_still_shown_on_the_field(app):
    """The page's list can be out of date (another window made the workspace); the server's
    answer is then shown on the field too, in the same words."""
    open_new_workspace(app)
    upload(app, "Job-1.inp")
    app.evaluate("""async () => {
        const fd = new FormData();
        fd.append('file', new File(['*HEADING\\n'], 'other.inp'));
        fd.append('name', 'Job-1');
        await fetch('/api/workspaces', {method: 'POST', body: fd});
    }""")
    app.locator("#create-btn-row button").click()
    expect_field_error(app, "ws-name-input", 'You already have a workspace called "Job-1"')
    app.expected_errors.clear()                                  # the server's 400 is the point


def test_missing_or_invalid_names_are_explained_before_anything_is_sent(app):
    open_new_workspace(app)
    upload(app, "Job-1.inp")
    app.fill("#ws-name-input", "")
    app.locator("#create-btn-row button").click()
    expect_field_error(app, "ws-name-input", "Give the workspace a name")
    app.fill("#ws-name-input", "a/b")
    app.locator("#create-btn-row button").click()
    expect_field_error(app, "ws-name-input", "can't contain /")
    expect(app.locator("#view-new-workspace")).to_be_visible()


def test_two_files_with_the_same_name_are_caught_on_the_second_one(app):
    open_new_workspace(app)
    upload(app, "Job-1.inp")
    app.locator("#sel-mesh").check()
    app.locator("#sel-material").check()
    app.fill("#fn-material", "mesh.inp")
    app.locator("#create-btn-row button").click()
    expect_field_error(app, "fn-material", 'Two files would both be called "mesh.inp"')
    app.fill("#fn-material", "Job-1.inp")                       # the mother file's name
    app.locator("#create-btn-row button").click()
    expect_field_error(app, "fn-material", 'The mother file is already called "Job-1.inp"')


def test_a_file_that_is_not_a_deck_is_refused_on_the_drop_zone(app):
    open_new_workspace(app)
    with tempfile.TemporaryDirectory() as d:
        pdf = Path(d) / "notes.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        app.set_input_files("#upload-input", str(pdf))
    expect_field_error(app, "upload-zone", '"notes.pdf" isn\'t one')
    expect(app.locator("#inspector-section")).to_be_hidden()
    upload(app, "Job-1.inp")                                    # a real deck clears it
    expect(app.locator("#upload-zone.field-invalid")).to_have_count(0)


def test_rename_to_an_existing_name_keeps_the_field_open_with_the_problem(app):
    make_workspace(app, "Job-1.inp", cats=())
    go_home(app)
    make_workspace(app, "test_2.inp", cats=())
    go_home(app)
    card = app.locator(".workspace-card[data-ws='test_2']")
    expect(card).to_be_visible()
    card.hover()                                                # the card's actions appear on hover
    card.get_by_role("button", name="Rename").click()
    app.fill("#ws-rename-input", "Job-1")
    app.keyboard.press("Enter")
    expect_field_error(app, "ws-rename-input", 'You already have a workspace called "Job-1"')
    expect(app.locator("#ws-rename-input")).to_be_visible()     # still open to fix
    app.keyboard.press("Escape")                                # or cancel
    expect(app.locator("#ws-rename-input")).to_have_count(0)
    expect(card.locator(".wsc-name")).to_have_text("test_2")


def test_error_messages_are_plain_and_stay_until_closed(app):
    make_workspace(app, "Job-1.inp")
    open_file(app, "mesh.inp")
    fail_file_saves(app)
    app.locator("#editor-ta").click()
    app.keyboard.type("x")
    app.locator("#editor-save-btn").click()
    msg = app.locator(".toast.error")
    expect(msg).to_contain_text("Couldn't save mesh.inp")
    expect(msg).to_contain_text("Something went wrong inside FileFold")
    expect(msg).not_to_contain_text("disk full")                # raw server output is never shown
    app.wait_for_timeout(4500)                                  # longer than a confirmation lasts
    expect(msg).to_be_visible()
    msg.get_by_role("button", name="Dismiss").click()
    expect(msg).to_have_count(0)
    app.expected_errors.clear()                                  # the injected 500 is the point


def test_splits_tab_checks_file_names_like_a_form(app):
    make_workspace(app, "Job-1.inp", cats=("mesh", "material"))
    app.locator("#tab-btn-splits").click()
    app.fill("#ws-fn-material", "mesh.inp")
    app.locator("#ws-splits-apply-btn").click()
    expect_field_error(app, "ws-fn-material", 'Two files would both be called "mesh.inp"')
    app.fill("#ws-fn-material", "")
    app.fill("#ws-fn-material", "a\\b.inp")
    app.locator("#ws-splits-apply-btn").click()
    expect_field_error(app, "ws-fn-material", "isn't a valid file name")
