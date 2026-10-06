"""Home page: chalkboard notes and the sample data section."""
from __future__ import annotations

import os

import pytest
from playwright.sync_api import Page, expect

from .test_ui import create, detail_filenames, open_new_workspace

STATIC = os.environ.get("FILEFOLD_E2E_TARGET") == "static"
SAMPLES = ["Job-1", "mmxmn", "fempy_example"]
NOTE_TITLES = [
    "The idea", "Upload and inspect", "Choose what to extract", "Go deeper",
    "Edit freely", "Re-split any time", "Reimport a new version", "Take it with you",
]


def test_home_shows_chalkboard_notes_for_every_function(app):
    notes = app.locator("#notes")
    expect(notes).to_be_visible()
    for title in NOTE_TITLES:
        expect(notes.get_by_role("heading", name=title)).to_be_visible()
    # where files live depends on the build
    expect(notes).to_contain_text("in this browser" if STATIC else "on the server")


def test_home_lists_the_three_sample_decks_with_facts(app):
    cards = app.locator(".sample-card")
    expect(cards).to_have_count(3)
    for name in SAMPLES:
        card = app.locator(f".sample-card[data-sample='{name}']")
        expect(card).to_be_visible()
        expect(card.get_by_role("button", name="Load into new workspace")).to_be_enabled()
        expect(card.get_by_role("link", name="Download")).to_have_attribute("href", f"static/samples/{name}.inp")
    expect(app.locator(".sample-card[data-sample='mmxmn']")).to_contain_text("4 steps")
    expect(app.locator(".sample-card[data-sample='fempy_example']")).to_contain_text("30 materials")
    expect(app.locator(".sample-card[data-sample='Job-1']")).to_contain_text("Windows line endings")


def test_notes_can_be_collapsed_and_stay_collapsed(app):
    toggle = app.locator("#notes-toggle")
    expect(toggle).to_have_attribute("aria-expanded", "true")
    toggle.click()
    expect(toggle).to_have_attribute("aria-expanded", "false")
    expect(app.locator("#notes-body")).to_be_hidden()
    app.reload()
    if STATIC:
        app.wait_for_selector("#static-banner", state="detached", timeout=90_000)
    expect(app.locator("#notes-toggle")).to_have_attribute("aria-expanded", "false")
    app.locator("#notes-toggle").click()
    expect(app.locator("#notes-body")).to_be_visible()


def test_notes_toggle_works_from_the_keyboard(app):
    app.locator("#notes-toggle").focus()
    app.keyboard.press("Enter")
    expect(app.locator("#notes-toggle")).to_have_attribute("aria-expanded", "false")
    app.keyboard.press("Space")
    expect(app.locator("#notes-toggle")).to_have_attribute("aria-expanded", "true")


@pytest.mark.parametrize("name", SAMPLES)
def test_loading_a_sample_fills_the_new_workspace_flow(app, name):
    app.locator(f".sample-card[data-sample='{name}'] button", has_text="Load into new workspace").click()
    expect(app.locator("#view-new-workspace")).to_be_visible()
    expect(app.locator("#inspector-tree .tree-node").first).to_be_visible(timeout=60_000)
    expect(app.locator("#split-config .split-row").first).to_be_visible()
    expect(app.locator("#ws-name-input")).to_have_value(name)


def test_a_loaded_sample_can_be_turned_into_a_workspace(app):
    app.locator(".sample-card[data-sample='Job-1'] button", has_text="Load into new workspace").click()
    expect(app.locator("#split-config .split-row").first).to_be_visible(timeout=60_000)
    app.locator("#sel-mesh").check()
    create(app)
    assert "mesh.inp" in detail_filenames(app)


def test_sample_section_is_not_in_the_way_of_new_workspace(app):
    """Back then New again must still start blank even after loading a sample."""
    app.locator(".sample-card[data-sample='Job-1'] button", has_text="Load into new workspace").click()
    expect(app.locator("#split-config .split-row").first).to_be_visible(timeout=60_000)
    app.get_by_role("button", name="← Back").first.click()
    open_new_workspace(app)
    expect(app.locator("#ws-name-input")).to_have_value("")
    expect(app.locator("#inspector-section")).to_be_hidden()


def test_notes_start_collapsed_for_people_who_already_have_workspaces(app):
    open_new_workspace(app)
    app.locator(".sample-card, #upload-input").first  # page object exists
    app.set_input_files("#upload-input", str(__import__("pathlib").Path(__file__).resolve().parent.parent / "fixtures" / "test_2.inp"))
    expect(app.locator("#split-config .split-row").first).to_be_visible(timeout=60_000)
    create(app)
    app.get_by_role("button", name="← Back").first.click()
    app.reload()
    if STATIC:
        app.wait_for_selector("#static-banner", state="detached", timeout=90_000)
    expect(app.locator(".workspace-card").first).to_be_visible()
    expect(app.locator("#notes-toggle")).to_have_attribute("aria-expanded", "false")
