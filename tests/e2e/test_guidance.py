"""Guidance for new users: sample data, (i) reminders, the skippable tour, and the Info tab."""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

from filefold.core.keywords import CATEGORY_SUB_OPTIONS, Category

from .conftest import fixture_path
from .test_ui import create, detail_filenames, open_new_workspace, upload

STATIC = os.environ.get("FILEFOLD_E2E_TARGET") == "static"
SAMPLES = ["Job-1", "mmxmn", "fempy_example"]


def reload(page: Page) -> None:
    page.reload()
    if STATIC:
        page.wait_for_selector("#static-banner", state="detached", timeout=90_000)


def as_new_visitor(page: Page) -> None:
    """Forget that the tour was dismissed (as on a first visit)."""
    page.evaluate("localStorage.removeItem('filefold.tour')")


def spotlight_settles_on(page: Page, selector: str) -> None:
    """The spotlight glides between steps; wait until it sits on the target element."""
    page.wait_for_function(
        """sel => {
          const s = document.getElementById('tour-spot'), t = document.querySelector(sel);
          if (!s || !t) return false;
          const a = s.getBoundingClientRect(), b = t.getBoundingClientRect();
          return a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom;
        }""",
        arg=selector, timeout=5000,
    )


def boxes_overlap(a: dict, b: dict) -> bool:
    return not (a["x"] + a["width"] <= b["x"] or b["x"] + b["width"] <= a["x"]
                or a["y"] + a["height"] <= b["y"] or b["y"] + b["height"] <= a["y"])


# --- sample data ---------------------------------------------------------------------------

def test_home_has_no_notes_board_and_no_preloaded_samples(app):
    expect(app.locator("#notes")).to_have_count(0)
    expect(app.locator(".sample-card")).to_have_count(0)


def test_new_workspace_starts_empty_and_offers_sample_data_on_request(app):
    open_new_workspace(app)
    expect(app.locator("#upload-zone")).to_contain_text("Drop")
    expect(app.locator("#inspector-section")).to_be_hidden()        # nothing is pre-loaded
    expect(app.locator("#ws-name-input")).to_have_value("")
    expect(app.locator("#sample-btn")).to_be_visible()
    expect(app.locator("#sample-menu")).to_be_hidden()               # the choice is the user's


def test_sample_menu_lists_the_three_decks(app):
    open_new_workspace(app)
    app.locator("#sample-btn").click()
    expect(app.locator("#sample-btn")).to_have_attribute("aria-expanded", "true")
    items = app.locator("#sample-menu [role=menuitem]")
    expect(items).to_have_count(3)
    for name in SAMPLES:
        expect(app.locator(f"#sample-menu [data-sample='{name}']")).to_be_visible()
    expect(app.locator("#sample-menu [data-sample='mmxmn']")).to_contain_text("4 steps")
    expect(app.locator("#sample-menu [data-sample='fempy_example']")).to_contain_text("30 materials")


@pytest.mark.parametrize("name", SAMPLES)
def test_choosing_a_sample_loads_it_like_an_upload(app, name):
    open_new_workspace(app)
    app.locator("#sample-btn").click()
    app.locator(f"#sample-menu [data-sample='{name}']").click()
    expect(app.locator("#sample-menu")).to_be_hidden()
    expect(app.locator("#inspector-tree .tree-node").first).to_be_visible(timeout=60_000)
    expect(app.locator("#split-config .split-row").first).to_be_visible()
    expect(app.locator("#ws-name-input")).to_have_value(name)


def test_sample_menu_closes_on_escape_and_outside_click(app):
    open_new_workspace(app)
    app.locator("#sample-btn").click()
    app.keyboard.press("Escape")
    expect(app.locator("#sample-menu")).to_be_hidden()
    expect(app.locator("#sample-btn")).to_be_focused()
    app.locator("#sample-btn").click()
    app.locator("#view-new-workspace h1").click()
    expect(app.locator("#sample-menu")).to_be_hidden()


def test_sample_menu_works_from_the_keyboard(app):
    open_new_workspace(app)
    app.locator("#sample-btn").focus()
    app.keyboard.press("Enter")
    expect(app.locator("#sample-menu [role=menuitem]").first).to_be_focused()
    app.keyboard.press("ArrowDown")
    expect(app.locator("#sample-menu [role=menuitem]").nth(1)).to_be_focused()
    app.keyboard.press("Enter")
    expect(app.locator("#inspector-tree .tree-node").first).to_be_visible(timeout=60_000)


def test_a_sample_can_become_a_workspace(app):
    open_new_workspace(app)
    app.locator("#sample-btn").click()
    app.locator("#sample-menu [data-sample='Job-1']").click()
    expect(app.locator("#split-config .split-row").first).to_be_visible(timeout=60_000)
    app.locator("#sel-mesh").check()
    create(app)
    assert "mesh.inp" in detail_filenames(app)


def test_new_workspace_is_blank_again_after_a_sample(app):
    open_new_workspace(app)
    app.locator("#sample-btn").click()
    app.locator("#sample-menu [data-sample='Job-1']").click()
    expect(app.locator("#split-config .split-row").first).to_be_visible(timeout=60_000)
    app.get_by_role("button", name="← Back").first.click()
    open_new_workspace(app)
    expect(app.locator("#ws-name-input")).to_have_value("")
    expect(app.locator("#inspector-section")).to_be_hidden()


# --- (i) reminders -------------------------------------------------------------------------

def test_info_buttons_open_short_reminders_and_close_with_escape(app):
    open_new_workspace(app)
    upload(app, "Job-1.inp")
    buttons = app.locator("#view-new-workspace .info-btn:visible")
    count = buttons.count()
    assert count >= 3, "upload, inspector and extract each deserve a reminder"
    for i in range(count):
        btn = buttons.nth(i)
        label = btn.get_attribute("aria-label")
        assert label and label.startswith("About"), label
        btn.click()
        pop = app.locator("#info-pop")
        expect(pop).to_be_visible()
        expect(btn).to_have_attribute("aria-expanded", "true")
        text = pop.inner_text().strip()
        assert 20 < len(text) <= 240, f"reminders stay minimal ({len(text)} chars): {text!r}"
        app.keyboard.press("Escape")
        expect(pop).to_be_hidden()
        expect(btn).to_be_focused()


def test_only_one_reminder_is_open_and_outside_click_closes_it(app):
    open_new_workspace(app)
    upload(app, "Job-1.inp")
    buttons = app.locator("#view-new-workspace .info-btn:visible")
    buttons.nth(0).click()
    first = app.locator("#info-pop").inner_text()
    buttons.nth(1).click()
    expect(app.locator("#info-pop")).to_have_count(1)
    assert app.locator("#info-pop").inner_text() != first
    app.locator("#view-new-workspace h1").click()
    expect(app.locator("#info-pop")).to_be_hidden()


def test_upload_reminder_mentions_sample_data(app):
    open_new_workspace(app)
    app.locator("#view-new-workspace .info-btn[data-info='upload']").click()
    expect(app.locator("#info-pop")).to_contain_text("Sample data")


def test_reminders_exist_where_the_screens_are_less_obvious(app):
    open_new_workspace(app)
    upload(app, "Job-1.inp")
    app.locator("#sel-mesh").check()
    create(app)
    expect(app.locator("#view-detail .info-btn:visible").first).to_be_visible()      # file statuses
    app.locator("#tab-btn-splits").click()
    expect(app.locator("#tab-content-splits .info-btn:visible").first).to_be_visible()
    app.locator("#tab-btn-files").click()
    app.get_by_role("button", name="Re-import").click()
    expect(app.locator("#view-reimport .info-btn:visible").first).to_be_visible()


# --- the tour ------------------------------------------------------------------------------

def test_new_visitors_are_offered_a_tour_only_on_the_new_workspace_screen(app):
    as_new_visitor(app)
    expect(app.locator("#tour-prompt")).to_have_count(0)          # not on the home screen
    open_new_workspace(app)
    prompt = app.locator("#tour-prompt")
    expect(prompt).to_be_visible()
    expect(prompt.get_by_role("button", name="Start tour")).to_be_visible()
    expect(prompt.get_by_role("button", name="No thanks")).to_be_visible()


def test_declining_the_tour_is_remembered(app):
    as_new_visitor(app)
    open_new_workspace(app)
    app.get_by_role("button", name="No thanks").click()
    expect(app.locator("#tour-prompt")).to_have_count(0)
    reload(app)
    open_new_workspace(app)
    expect(app.locator("#tour-prompt")).to_have_count(0)


def test_the_offer_never_blocks_the_page(app):
    as_new_visitor(app)
    open_new_workspace(app)
    expect(app.locator("#tour-prompt")).to_be_visible()
    upload(app, "Job-1.inp")               # Playwright fails if the floating offer intercepts a click
    app.locator("#sel-mesh").check()
    create(app)
    assert "mesh.inp" in detail_filenames(app)


def start_tour(page: Page) -> None:
    as_new_visitor(page)
    open_new_workspace(page)
    page.get_by_role("button", name="Start tour").click()
    expect(page.locator("#tour-card")).to_be_visible()


def test_tour_walks_through_creating_a_workspace_with_arrows(app):
    start_tour(app)
    card = app.locator("#tour-card")
    expect(card).to_contain_text("1 of 6")
    expect(card.locator(".tour-arrow")).to_have_count(1)
    expect(card.get_by_role("heading")).to_contain_text("Start with a model")
    spotlight_settles_on(app, "#upload-zone")

    card.get_by_role("button", name="Next").click()
    expect(card).to_contain_text("2 of 6")
    spotlight_settles_on(app, "#sample-btn")
    expect(app.locator("#sample-menu")).to_be_hidden()           # the tour never loads anything for you

    card.get_by_role("button", name="Next").click()
    expect(card).to_contain_text("3 of 6")
    # no file yet: the step offers to load one, but only when the user asks
    expect(app.locator("#inspector-section")).to_be_hidden()
    card.get_by_role("button", name="Load the Job-1 sample").click()
    expect(app.locator("#inspector-section")).to_be_visible(timeout=60_000)
    spotlight_settles_on(app, "#inspector-section")

    for n, heading in ((4, "Choose what to extract"), (5, "Go deeper"), (6, "Name it and create")):
        card.get_by_role("button", name="Next").click()
        expect(card).to_contain_text(f"{n} of 6")
        expect(card.get_by_role("heading")).to_contain_text(heading)
    card.get_by_role("button", name="Done").click()
    expect(app.locator("#tour-card")).to_have_count(0)
    expect(app.locator("#tour-spot")).to_have_count(0)
    assert app.evaluate("localStorage.getItem('filefold.tour')") == "done"

    app.locator("#sel-mesh").check()                              # the page is fully usable afterwards
    create(app)
    assert "mesh.inp" in detail_filenames(app)


def test_every_tour_step_can_be_skipped_or_stepped_back(app):
    start_tour(app)
    card = app.locator("#tour-card")
    card.get_by_role("button", name="Next").click()
    expect(card).to_contain_text("2 of 6")
    card.get_by_role("button", name="Back").click()
    expect(card).to_contain_text("1 of 6")
    expect(card.get_by_role("button", name="Back")).to_be_disabled()
    card.get_by_role("button", name="Skip tour").click()
    expect(app.locator("#tour-card")).to_have_count(0)
    assert app.evaluate("localStorage.getItem('filefold.tour')") == "dismissed"


def test_tour_keyboard_controls(app):
    start_tour(app)
    card = app.locator("#tour-card")
    app.keyboard.press("ArrowRight")
    expect(card).to_contain_text("2 of 6")
    app.keyboard.press("ArrowLeft")
    expect(card).to_contain_text("1 of 6")
    app.keyboard.press("Escape")
    expect(app.locator("#tour-card")).to_have_count(0)


def test_tour_can_be_restarted_any_time_from_the_tour_button(app):
    open_new_workspace(app)                       # seeded as dismissed: no offer
    expect(app.locator("#tour-prompt")).to_have_count(0)
    app.locator("#tour-btn").click()
    expect(app.locator("#tour-card")).to_contain_text("1 of 6")


def test_leaving_the_screen_ends_the_tour(app):
    start_tour(app)
    app.get_by_role("button", name="← Back").first.click()
    expect(app.locator("#tour-card")).to_have_count(0)
    expect(app.locator("#tour-spot")).to_have_count(0)


def test_tour_follows_a_file_the_user_uploads_themselves(app):
    start_tour(app)
    app.set_input_files("#upload-input", str(fixture_path("Job-1.inp")))
    expect(app.locator("#inspector-section")).to_be_visible(timeout=60_000)
    card = app.locator("#tour-card")
    card.get_by_role("button", name="Next").click()
    card.get_by_role("button", name="Next").click()
    expect(card).to_contain_text("3 of 6")
    expect(card.get_by_role("button", name="Load the Job-1 sample")).to_have_count(0)   # already have a file
    spotlight_settles_on(app, "#inspector-section")


def test_tour_card_stays_inside_the_window(app):
    start_tour(app)
    vp = app.viewport_size
    for _ in range(2):
        box = app.locator("#tour-card").bounding_box()
        assert box["x"] >= 0 and box["y"] >= 0 and box["x"] + box["width"] <= vp["width"] and box["y"] + box["height"] <= vp["height"]
        app.locator("#tour-card").get_by_role("button", name="Next").click()


# --- the Info tab --------------------------------------------------------------------------

SECTIONS = ["Creating a workspace", "Categories", "Going deeper", "Files and statuses", "Editing files",
            "The Splits tab", "Reimporting a new version", "Export and command line", "How the parser reads your file"]


def open_info(page: Page) -> None:
    page.locator("#nav-info").click()
    expect(page.locator("#view-help")).to_be_visible()


def test_info_tab_describes_every_function(app):
    open_info(app)
    for title in SECTIONS:
        expect(app.locator("#view-help h2", has_text=title)).to_be_visible()
    # all the categories, from the parser itself, so the page cannot go stale
    text = app.locator("#view-help").inner_text().lower()
    for cat in Category:
        assert cat.value in text, f"Info tab never mentions the {cat.value!r} category"
    # and every fixed split option by its label
    for options in CATEGORY_SUB_OPTIONS.values():
        for opt in options:
            assert opt["label"].split(" (")[0].lower() in text, opt["label"]


def test_info_tab_table_of_contents_jumps_to_sections(app):
    open_info(app)
    app.locator("#view-help nav a", has_text="Reimporting a new version").click()
    expect(app.locator("#help-reimport")).to_be_in_viewport()


def test_info_tab_can_start_the_tour(app):
    open_info(app)
    app.locator("#view-help .topbar").get_by_role("button", name="Take the tour").click()
    expect(app.locator("#view-new-workspace")).to_be_visible()
    expect(app.locator("#tour-card")).to_contain_text("1 of 6")


def test_info_tab_says_where_files_are_kept_for_this_build(app):
    open_info(app)
    text = app.locator("#view-help").inner_text()
    assert ("in this browser" if STATIC else "on the server") in text
    assert ("on the server" if STATIC else "in this browser") not in text


def test_info_nav_is_reachable_and_leaves_cleanly(app):
    open_info(app)
    expect(app.locator("#nav-info")).to_have_class(re.compile("active"))
    app.get_by_role("button", name="← Back").first.click()
    expect(app.locator("#view-home")).to_be_visible()


def test_escape_right_after_opening_sample_menu_still_closes_it(app):
    """The list downloads on first open; closing must not wait for it."""
    open_new_workspace(app)
    app.route("**/static/samples/manifest.json", lambda r: (__import__("time").sleep(0.8), r.continue_())[1])
    app.locator("#sample-btn").click()
    app.keyboard.press("Escape")
    expect(app.locator("#sample-menu")).to_be_hidden()
    app.wait_for_timeout(1200)                       # the slow download finishes afterwards
    expect(app.locator("#sample-menu")).to_be_hidden()
    expect(app.locator("#sample-btn")).to_have_attribute("aria-expanded", "false")
