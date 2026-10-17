"""Re-import review: show what changed before asking to overwrite (UX review, proposal 3).

Before, a conflict (edited here AND changed upstream) was a bare checkbox: the user could not
see their own edit or the incoming change, so the choice was blind and one click lost work.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from playwright.sync_api import Page, expect

from .conftest import fixture_path
from .test_workflows import api_text, make_workspace, open_file


def edit_and_save(page: Page, filename: str, text: str) -> None:
    open_file(page, filename)
    page.locator("#editor-ta").click()
    page.keyboard.press("ControlOrMeta+Home")
    page.keyboard.type(text)
    page.locator("#editor-save-btn").click()
    expect(page.locator(".toast", has_text=f"Saved {filename}")).to_be_visible()
    page.get_by_role("button", name="← Back").last.click()


def reimport_changed_job1(page: Page) -> None:
    changed = Path(tempfile.mkdtemp()) / "Job-1.inp"
    text = fixture_path("Job-1.inp").read_text()
    changed.write_text(text.replace("*Node", "*Node\n** changed upstream", 1))
    page.get_by_role("button", name="Re-import").click()
    page.set_input_files("#reimp-input", str(changed))
    expect(page.locator("#reimp-preview-section")).to_be_visible(timeout=30_000)


def setup_conflict(page: Page) -> None:
    make_workspace(page, "Job-1.inp", cats=("mesh", "material"))
    edit_and_save(page, "mesh.inp", "** my local note\n")
    reimport_changed_job1(page)


def test_a_conflict_shows_both_versions_side_by_side(app):
    setup_conflict(app)
    row = app.locator(".reimp-item.is-conflict", has_text="mesh.inp")
    expect(row).to_have_count(1)
    expect(row.locator(".diff-side.yours")).to_contain_text("** my local note")
    expect(row.locator(".diff-side.incoming")).to_contain_text("** changed upstream")
    expect(row.get_by_role("radio", name="Keep my edits")).to_be_checked()
    expect(row.get_by_role("radio", name="Take incoming")).not_to_be_checked()


def test_keep_my_edits_keeps_the_local_change(app):
    setup_conflict(app)
    app.locator("#reimp-apply-btn").click()
    expect(app.locator(".toast", has_text="Reimport applied")).to_be_visible()
    text = api_text(app, "Job-1", "mesh.inp")
    assert "** my local note" in text and "** changed upstream" not in text


def test_take_incoming_replaces_the_local_change(app):
    setup_conflict(app)
    app.locator(".reimp-item.is-conflict", has_text="mesh.inp").get_by_role("radio", name="Take incoming").check()
    expect(app.locator("#reimp-summary")).to_contain_text("1 replaced")
    app.locator("#reimp-apply-btn").click()
    expect(app.locator(".toast", has_text="Reimport applied")).to_be_visible()
    text = api_text(app, "Job-1", "mesh.inp")
    assert "** changed upstream" in text and "** my local note" not in text


def test_review_is_ordered_by_the_decision_needed_and_names_the_mother(app):
    setup_conflict(app)
    groups = [g.get_attribute("data-group") for g in app.locator("#reimp-results .reimp-group").all()]
    order = ["conflict", "update", "new", "unchanged", "mother"]
    assert groups == [g for g in order if g in groups], groups
    assert groups[0] == "conflict"
    expect(app.locator(".reimp-group[data-group='mother']")).to_contain_text("Job-1.inp")
    expect(app.locator(".reimp-group[data-group='mother']")).to_contain_text("always updated")
    expect(app.locator("#reimp-preview-section")).not_to_contain_text("sections")   # child files, not "sections"


def test_a_safe_update_can_be_inspected_before_applying(app):
    make_workspace(app, "Job-1.inp", cats=("mesh",))
    reimport_changed_job1(app)
    row = app.locator(".reimp-item.is-update", has_text="mesh.inp")
    expect(row.get_by_role("checkbox")).to_be_checked()
    row.get_by_role("button", name="Show changes").click()
    expect(row.locator(".diff-side.incoming")).to_contain_text("** changed upstream")


def test_a_change_of_line_endings_only_is_named_as_such(app):
    make_workspace(app, "Job-1.inp", cats=("mesh", "material"))
    lf = Path(tempfile.mkdtemp()) / "Job-1.inp"
    lf.write_bytes(fixture_path("Job-1.inp").read_bytes().replace(b"\r\n", b"\n"))   # Job-1 is CRLF
    app.get_by_role("button", name="Re-import").click()
    app.set_input_files("#reimp-input", str(lf))
    expect(app.locator("#reimp-preview-section")).to_be_visible(timeout=30_000)
    row = app.locator(".reimp-item.is-update", has_text="material.inp")
    expect(row).to_contain_text("line endings only")
    row.get_by_role("button", name="Show changes").click()
    expect(row).to_contain_text("only the line endings differ")


def test_messages_never_cover_the_apply_bar(app):
    make_workspace(app, "Job-1.inp", cats=("mesh",))       # leaves a "created" toast on screen
    app.locator("#tab-btn-splits").click()
    app.locator("#ws-sel-material").check()
    toast_box = app.locator(".toast").first.bounding_box()
    bar_box = app.locator("#splits-pending-bar").bounding_box()
    assert toast_box["y"] + toast_box["height"] <= bar_box["y"] or toast_box["y"] >= bar_box["y"] + bar_box["height"]
