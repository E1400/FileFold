"""End-to-end UI tests. See conftest.py for the fail-on-any-browser-error rule."""
from __future__ import annotations

import io
import zipfile

import pytest
from playwright.sync_api import Page, expect

from .conftest import FIXTURES, fixture_path

ALL_FIXTURES = sorted(p.name for p in FIXTURES.glob("*.inp"))


# --- helpers ----------------------------------------------------------------

def open_new_workspace(page: Page) -> None:
    page.locator("button:visible", has_text="+ New").first.click()
    expect(page.locator("#view-new-workspace")).to_be_visible()


def upload(page: Page, name: str) -> None:
    page.set_input_files("#upload-input", str(fixture_path(name)))
    expect(page.locator("#inspector-tree .tree-node").first).to_be_visible(timeout=30_000)
    expect(page.locator("#split-config .split-row").first).to_be_visible()


def create(page: Page) -> None:
    page.locator("#create-btn-row button").click()
    expect(page.locator("#view-detail")).to_be_visible(timeout=30_000)


def detail_files(page: Page) -> list[str]:
    expect(page.locator("#detail-files tr").first).to_be_visible()  # table fills async
    return page.locator("#detail-files tr").all_inner_texts()


def assert_new_workspace_is_blank(page: Page) -> None:
    expect(page.locator("#view-new-workspace")).to_be_visible()
    expect(page.locator("#ws-name-input")).to_have_value("")
    expect(page.locator("#inspector-section")).to_be_hidden()
    expect(page.locator("#split-config-section")).to_be_hidden()
    expect(page.locator("#create-btn-row")).to_be_hidden()
    expect(page.locator("#inspector-tree .tree-node")).to_have_count(0)
    expect(page.locator("#upload-zone")).to_contain_text("Drop")


# --- load -------------------------------------------------------------------

def test_home_loads_without_errors(app):
    expect(app.locator("#view-home")).to_be_visible()


# --- upload / inspect -------------------------------------------------------

@pytest.mark.parametrize("name", ALL_FIXTURES)
def test_every_fixture_uploads_and_parses(app, name):
    open_new_workspace(app)
    upload(app, name)
    expect(app.locator("#upload-zone")).to_contain_text("blocks detected")
    expect(app.locator("#ws-name-input")).to_have_value(name.removesuffix(".inp"))
    # No block should be left in the "unknown" category (options inherit their parent's).
    expect(app.locator("#inspector-tree .tree-cat", has_text="unknown")).to_have_count(0)
    # At least one category can be extracted.
    assert app.locator("#split-config input[id^='sel-']").count() > 0


def test_rigid_body_and_system_get_real_categories(app):
    open_new_workspace(app)
    upload(app, "Job-1.inp")
    tree = app.locator("#inspector-tree")
    expect(tree.locator(".tree-node-header", has_text="*RIGID BODY").first).to_contain_text("constraint")
    expect(tree.locator(".tree-node-header", has_text="*SYSTEM").first).to_contain_text("mesh")
    expect(app.locator("#sel-constraint")).to_be_visible()


# --- the "New workspace shows the old upload" bug --------------------------

def test_new_workspace_is_blank_after_abandoned_upload(app):
    open_new_workspace(app)
    upload(app, "Job-1.inp")
    app.get_by_role("button", name="← Back").first.click()
    open_new_workspace(app)
    assert_new_workspace_is_blank(app)


def test_new_workspace_is_blank_after_creating_one(app):
    open_new_workspace(app)
    upload(app, "Job-1.inp")
    app.locator("#sel-mesh").check()
    create(app)
    app.get_by_role("button", name="← Back").first.click()
    open_new_workspace(app)
    assert_new_workspace_is_blank(app)


def test_same_file_can_be_uploaded_twice_in_a_row(app):
    open_new_workspace(app)
    upload(app, "Job-1.inp")
    app.get_by_role("button", name="← Back").first.click()
    open_new_workspace(app)
    upload(app, "Job-1.inp")  # input value must have been cleared or onchange never fires
    expect(app.locator("#upload-zone")).to_contain_text("blocks detected")


# --- create -----------------------------------------------------------------

def test_create_workspace_with_categories(app):
    open_new_workspace(app)
    upload(app, "Job-1.inp")
    for cat in ("mesh", "material", "constraint"):
        app.locator(f"#sel-{cat}").check()
    create(app)
    files = "\n".join(detail_files(app))
    for fn in ("mesh.inp", "material.inp", "constraint.inp"):
        assert fn in files, f"{fn} missing from:\n{files}"


def test_create_workspace_with_no_categories_keeps_source_only(app):
    open_new_workspace(app)
    upload(app, "test_2.inp")
    create(app)
    expect(app.locator("#detail-title")).to_contain_text("test_2")


def test_create_requires_a_name(app):
    open_new_workspace(app)
    upload(app, "Job-1.inp")
    app.fill("#ws-name-input", "")
    app.locator("#create-btn-row button").click()
    expect(app.locator("#view-new-workspace")).to_be_visible()  # stayed put, no request sent


def test_contact_subsplit_through_the_ui(app):
    open_new_workspace(app)
    upload(app, "mmxmn.inp")
    app.locator("#sel-contact").check()
    expect(app.locator("#sub-opts-contact")).to_be_visible()
    app.locator("#sub-contact-pairs").check()
    create(app)
    files = "\n".join(detail_files(app))
    assert "contact.inp" in files and "contact-pairs.inp" in files


def test_duplicate_workspace_name_is_reported_not_swallowed(app):
    for _ in range(2):
        open_new_workspace(app)
        upload(app, "test_2.inp")
        if _ == 0:
            create(app)
            app.get_by_role("button", name="← Back").first.click()
    app.locator("#create-btn-row button").click()
    expect(app.locator(".toast", has_text="already exists")).to_be_visible()
    app.expected_errors.clear()  # the 400 is the point of this test


# --- workspace lifecycle ----------------------------------------------------

def test_workspace_listed_on_home_then_deleted(app):
    open_new_workspace(app)
    upload(app, "Job-1.inp")
    create(app)
    app.get_by_role("button", name="← Back").first.click()
    expect(app.locator(".workspace-card[data-ws='Job-1']")).to_be_visible()
    app.locator(".workspace-card[data-ws='Job-1']").click()
    app.get_by_role("button", name="Delete").click()
    expect(app.locator(".workspace-card[data-ws='Job-1']")).to_have_count(0)


def test_export_zip_contains_mother_and_children(app):
    open_new_workspace(app)
    upload(app, "Job-1.inp")
    app.locator("#sel-mesh").check()
    create(app)
    with app.expect_download() as dl:
        app.get_by_role("button", name="Export ZIP").click()
    names = zipfile.ZipFile(dl.value.path()).namelist()
    assert any(n.endswith("Job-1.inp") for n in names) and any(n.endswith("mesh.inp") for n in names), names


# --- client/server agreement ------------------------------------------------

def test_js_and_server_agree_on_non_extractable_categories(app):
    from filefold.api.main import NON_EXTRACTABLE
    assert set(app.evaluate("[...NON_EXTRACTABLE]")) == set(NON_EXTRACTABLE)
