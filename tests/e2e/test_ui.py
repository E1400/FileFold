"""End-to-end UI tests. See conftest.py for the fail-on-any-browser-error rule."""
from __future__ import annotations

import io
import re
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


def detail_filenames(page: Page) -> list[str]:
    expect(page.locator("#detail-files tr").first).to_be_visible()
    return [t.strip() for t in page.locator("#detail-files .filename-text").all_inner_texts()]


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


# --- create menu only offers sub-splits that exist in the uploaded deck -----

def _offered_subs(page: Page, cat: str) -> list[str]:
    page.locator(f"#sel-{cat}").check()
    return [i.get_attribute("value") for i in page.locator(f"#sub-opts-{cat} input[type=checkbox][id^='sub-{cat}-']").all()]


def test_constraint_only_offers_rigid_for_job1(app):
    open_new_workspace(app)
    upload(app, "Job-1.inp")  # only *RIGID BODY present, no ties/couplings/equations
    assert _offered_subs(app, "constraint") == ["rigid"]


def test_contact_only_offers_what_mmxmn_contains(app):
    open_new_workspace(app)
    upload(app, "mmxmn.inp")  # contact pairs + interactions, no general contact
    assert _offered_subs(app, "contact") == ["pairs", "interactions"]
    app.locator("#sel-loads").check()
    assert [i.get_attribute("value") for i in app.locator("#sub-opts-loads input[id^='sub-loads-']").all()] == ["amplitudes"]


def test_category_with_no_sub_options_has_no_sub_panel(app):
    open_new_workspace(app)
    upload(app, "Job-1.inp")
    expect(app.locator("#sub-opts-section")).to_have_count(0)  # no static or name-based groups for sections


def test_selecting_all_subs_creates_every_offered_file(app):
    open_new_workspace(app)
    upload(app, "mmxmn.inp")
    app.locator("#sel-contact").check()
    app.locator("#submaster-contact").check()
    create(app)
    files = "\n".join(detail_files(app))
    assert "contact-pairs.inp" in files and "contact-interactions.inp" in files
    assert "contact-general.inp" not in files


# --- name-based sub-splits through the UI -----------------------------------

def _dynamic_ids(page: Page, cat: str, axis: str) -> list[str]:
    return [i.get_attribute("id") for i in page.locator(f"input[id^='sub-{cat}-{axis}.']").all()]


def test_each_material_is_offered_by_name_and_split_into_its_own_file(app):
    open_new_workspace(app)
    upload(app, "fempy_example.inp")
    app.locator("#sel-material").check()
    ids = _dynamic_ids(app, "material", "material")
    assert len(ids) > 3, "expected one option per material in the deck"
    labels = [t.strip() for t in app.locator("#sub-opts-material .sub-option-row label").all_text_contents()]
    assert labels and all(l.startswith("Material:") for l in labels), labels
    app.locator("#submaster-material").check()
    create(app)
    expect(app.locator("#detail-files .badge-sub")).to_have_count(len(ids), timeout=90_000)
    subs = [n for n in detail_filenames(app) if n.startswith("material-")]
    assert len(subs) == len(ids), subs


def test_steps_split_by_name(app):
    open_new_workspace(app)
    upload(app, "Job-1.inp")
    app.locator("#sel-step").check()
    ids = _dynamic_ids(app, "step", "step")
    assert ids, "Job-1 has a step"
    app.locator(f"[id=\"{ids[0]}\"]").check()
    create(app)
    assert "step-1.inp" in detail_filenames(app)


def test_mesh_offers_parts_and_element_types(app):
    open_new_workspace(app)
    upload(app, "fempy_example.inp")
    app.locator("#sel-mesh").check()
    assert _dynamic_ids(app, "mesh", "part"), "fempy_example is built from *PART blocks"
    assert _dynamic_ids(app, "mesh", "etype"), "element type is offered as a finer split of Elements"


def _box(page: Page, box_id: str):
    return page.locator(f'[id="{box_id}"]')


def _apply_splits(page: Page) -> None:
    btn = page.locator("#ws-splits-apply-btn")
    btn.click()
    expect(btn).to_have_text("Apply changes", timeout=30_000)      # finished, tab re-rendered
    expect(btn).to_be_enabled()


def test_elements_and_element_type_tick_together_and_never_disappear(app):
    """Regression: in Job-1 every element is CPS4R, so "Elements" and "Element type: CPS4R"
    claim the same lines. They used to exclude each other, and since element type was hidden
    from the menus, switching to Elements and applying made it vanish for good."""
    open_new_workspace(app)
    upload(app, "Job-1.inp")
    app.locator("#sel-mesh").check()
    etype, elements = _box(app, "sub-mesh-etype.cps4r"), _box(app, "sub-mesh-elements")
    expect(etype).to_be_enabled()
    etype.check()                                     # a refinement ticks its parent
    expect(elements).to_be_checked()
    expect(elements).to_be_enabled()
    expect(_box(app, "subhint-mesh-elements")).to_contain_text("split by type")
    create(app)
    files = detail_filenames(app)
    assert "elements-cps4r.inp" in files and "mesh-elements.inp" not in files   # no empty file

    app.locator("#tab-btn-splits").click()
    ws_etype, ws_elements = _box(app, "ws-sub-mesh-etype.cps4r"), _box(app, "ws-sub-mesh-elements")
    expect(ws_etype).to_be_checked()
    expect(ws_elements).to_be_checked()
    ws_etype.uncheck()                                # switch to plain Elements
    expect(ws_elements).to_be_checked()
    expect(ws_elements).to_be_enabled()
    expect(_box(app, "ws-subhint-mesh-elements")).to_have_text("")
    _apply_splits(app)
    app.locator("#tab-btn-files").click()
    files = detail_filenames(app)
    assert "mesh-elements.inp" in files and "elements-cps4r.inp" not in files

    app.locator("#tab-btn-splits").click()
    expect(ws_etype).to_have_count(1)                 # still offered: the door goes both ways
    expect(ws_etype).to_be_enabled()
    ws_etype.check()                                  # and back to element type
    _apply_splits(app)
    expect(ws_etype).to_be_checked()
    expect(ws_elements).to_be_checked()
    app.locator("#tab-btn-files").click()
    files = detail_filenames(app)
    assert "elements-cps4r.inp" in files and "mesh-elements.inp" not in files

    app.locator("#tab-btn-splits").click()
    ws_elements.uncheck()                             # unticking the parent unticks its refinements
    expect(ws_etype).not_to_be_checked()
    _apply_splits(app)
    app.locator("#tab-btn-files").click()
    files = detail_filenames(app)
    assert "elements-cps4r.inp" not in files and "mesh-elements.inp" not in files


def test_dynamic_sub_split_from_the_splits_tab(app):
    make_workspace_for_dynamic(app)
    app.locator("#tab-btn-splits").click()
    ids = [i.get_attribute("id") for i in app.locator("input[id^='ws-sub-material-material.']").all()]
    assert ids
    app.locator(f"[id=\"{ids[0]}\"]").check()
    app.locator("#ws-splits-apply-btn").click()
    app.locator("#tab-btn-files").click()
    expect(app.locator("#detail-files .badge-sub").first).to_be_visible()


def make_workspace_for_dynamic(page: Page) -> None:
    open_new_workspace(page)
    upload(page, "Job-1.inp")
    page.locator("#sel-material").check()
    create(page)
    expect(page.locator("#detail-files tr").first).to_be_visible()


# --- static (in-browser) build only -----------------------------------------

import os as _os

@pytest.mark.skipif(_os.environ.get("FILEFOLD_E2E_TARGET") != "static", reason="static build only")
def test_static_build_warns_about_decks_over_100mb(app):
    assert app.evaluate("staticSizeWarning(50 * 1024 * 1024)") is None
    assert "desktop app" in app.evaluate("staticSizeWarning(150 * 1024 * 1024)")


@pytest.mark.skipif(_os.environ.get("FILEFOLD_E2E_TARGET") != "static", reason="static build only")
def test_static_build_keeps_workspaces_across_reload(app):
    open_new_workspace(app)
    upload(app, "Job-1.inp")
    app.locator("#sel-mesh").check()
    create(app)
    app.reload()
    app.wait_for_selector("#static-banner", state="detached", timeout=90_000)
    expect(app.locator(".ws-item", has_text="Job-1")).to_be_visible()


@pytest.mark.skipif(_os.environ.get("FILEFOLD_E2E_TARGET") != "static", reason="static build only")
def test_landing_page_opens_the_app(app, base_url):
    """The Pages site root is the landing page; its main button must open the working app."""
    errors = []
    app.on("pageerror", lambda e: errors.append(str(e)))
    app.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    app.goto(base_url + "../")
    expect(app.get_by_role("heading", name="FEA models.")).to_be_visible()
    for text in ("Split as deep as you need", "Private by design", "Command line included"):
        expect(app.get_by_text(text)).to_be_visible()
    app.get_by_role("link", name="Open FileFold").first.click()
    app.wait_for_url(re.compile(r"/app/$"))
    app.wait_for_selector("#static-banner", state="detached", timeout=90_000)
    expect(app.locator("#view-home")).to_be_visible()
    assert errors == []


@pytest.mark.skipif(_os.environ.get("FILEFOLD_E2E_TARGET") != "static", reason="static build only")
def test_landing_page_looks_right_and_works(app, base_url):
    errors = []
    app.on("pageerror", lambda e: errors.append(str(e)))
    app.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    app.goto(base_url + "../")
    # screenshots load, and only the ones for the current theme are shown
    app.evaluate("document.documentElement.dataset.theme = 'light'")
    assert app.locator("img.img-light:visible").count() == 2
    assert app.locator("img.img-dark:visible").count() == 0, "dark screenshots must hide in the light theme"
    app.wait_for_function("[...document.querySelectorAll('img')].filter(i => i.offsetParent).every(i => i.complete && i.naturalWidth > 0)")
    app.evaluate("document.documentElement.dataset.theme = 'dark'")
    assert app.locator("img.img-dark:visible").count() == 2
    assert app.locator("img.img-light:visible").count() == 0, "light screenshots must hide in the dark theme"
    # every in-page link goes to a real section
    for href in app.eval_on_selector_all("a[href^='#']", "els => els.map(e => e.getAttribute('href'))"):
        if href != "#":
            assert app.locator(href).count() == 1, f"nav link {href} has no target"
    # the theme toggle changes the page and is remembered
    app.evaluate("delete document.documentElement.dataset.theme; localStorage.removeItem('filefold.theme')")
    app.get_by_role("button", name="Toggle theme").click()
    first = app.evaluate("document.documentElement.dataset.theme")
    assert first in {"light", "dark"}
    app.reload()
    assert app.evaluate("document.documentElement.dataset.theme") == first
    # no horizontal scrolling on a phone
    app.set_viewport_size({"width": 390, "height": 800})
    assert not app.evaluate("document.documentElement.scrollWidth > window.innerWidth")
    # skip link is the first thing a keyboard user reaches
    app.keyboard.press("Tab")
    assert app.evaluate("document.activeElement.textContent.trim()").lower().startswith("skip")
    assert errors == []


@pytest.mark.skipif(_os.environ.get("FILEFOLD_E2E_TARGET") != "static", reason="static build only")
def test_theme_choice_made_on_the_landing_page_carries_into_the_app(app, base_url):
    app.goto(base_url + "../")
    app.evaluate("localStorage.setItem('filefold.theme', 'dark'); delete document.documentElement.dataset.theme")
    app.goto(base_url)
    app.wait_for_selector("#static-banner", state="detached", timeout=90_000)
    assert app.evaluate("document.documentElement.dataset.theme") == "dark"


def test_the_apps_theme_toggle_is_remembered(app):
    app.evaluate("localStorage.removeItem('filefold.theme')")
    app.locator("#theme-btn").click()
    chosen = app.evaluate("document.documentElement.dataset.theme")
    app.reload()
    if _os.environ.get("FILEFOLD_E2E_TARGET") == "static":
        app.wait_for_selector("#static-banner", state="detached", timeout=90_000)
    assert app.evaluate("document.documentElement.dataset.theme") == chosen


@pytest.mark.skipif(_os.environ.get("FILEFOLD_E2E_TARGET") != "static", reason="static build only")
@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_landing_page_follows_the_system_theme_when_nothing_is_saved(app, base_url, scheme):
    app.emulate_media(color_scheme=scheme)
    app.goto(base_url + "../")
    app.evaluate("localStorage.removeItem('filefold.theme'); delete document.documentElement.dataset.theme")
    shown, hidden = (f"img.img-{scheme}", f"img.img-{'dark' if scheme == 'light' else 'light'}")
    assert app.locator(shown + ":visible").count() == 2 and app.locator(hidden + ":visible").count() == 0
    bg = app.evaluate("getComputedStyle(document.body).backgroundColor")
    assert bg == ("rgb(217, 219, 215)" if scheme == "light" else "rgb(27, 26, 24)")   # the app's own ground colours
