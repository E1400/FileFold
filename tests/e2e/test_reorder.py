"""Changing the order of files in the Splits tab moves the mother's *INCLUDE lines."""
from __future__ import annotations

import re

from playwright.sync_api import Page, expect

from .conftest import fetch_text
from .test_workflows import make_workspace

ALL = ("mesh", "section", "constraint", "material", "step")


def split_rows(page: Page) -> list[str]:
    return page.eval_on_selector_all("#ws-split-config .split-row[data-cat]", "rs => rs.map(r => r.dataset.cat)")


def includes(page: Page) -> list[str]:
    return re.findall(r"^\*INCLUDE, INPUT=(\S+)", fetch_text(page, "/api/workspaces/Job-1/files/Job-1.inp"), flags=re.M)


def apply(page: Page) -> None:
    page.locator("#ws-splits-apply-btn").click()
    expect(page.locator(".toast", has_text="file order changed")).to_be_visible(timeout=60_000)
    expect(page.locator("#ws-splits-apply-btn")).to_have_text("Apply changes")


def open_splits(page: Page, cats=ALL) -> None:
    make_workspace(page, "Job-1.inp", cats=cats)
    page.locator("#tab-btn-splits").click()
    expect(page.locator("#ws-sel-mesh")).to_be_visible()


def test_rows_follow_the_deck_and_buttons_move_a_file(app):
    open_splits(app)
    assert split_rows(app) == list(ALL)                     # deck order, not alphabetical
    assert includes(app) == [f"{c}.inp" for c in ALL]
    expect(app.locator("#ws-up-mesh")).to_be_disabled()
    expect(app.locator("#ws-row-step .move-btn")).to_have_count(0)   # the step file is the fence
    expect(app.locator("#ws-row-step")).to_contain_text("stays last")
    expect(app.locator("#ws-down-material")).to_be_disabled()        # cannot pass the step file
    expect(app.locator("#ws-order-hint")).to_be_hidden()
    app.locator("#ws-up-material").click()
    assert split_rows(app) == ["mesh", "section", "material", "constraint", "step"]
    expect(app.locator("#ws-order-hint")).to_be_visible()
    expect(app.locator("#ws-up-material")).to_be_focused()           # keyboard users keep their place
    app.locator("#ws-up-material").press("Enter")
    assert split_rows(app) == ["mesh", "material", "section", "constraint", "step"]
    apply(app)
    assert includes(app) == ["mesh.inp", "material.inp", "section.inp", "constraint.inp", "step.inp"]
    assert split_rows(app) == ["mesh", "material", "section", "constraint", "step"]
    expect(app.locator("#ws-order-hint")).to_be_hidden()
    app.locator("#tab-btn-files").click()
    names = [t.strip() for t in app.locator("#detail-files .filename-text").all_inner_texts()]
    assert names[:4] == ["Job-1.inp", "mesh.inp", "material.inp", "section.inp"]
    # FileFold changed the mother, the person did not: it is not marked as edited.
    expect(app.locator("#detail-files tr").first.locator(".badge-ok")).to_be_visible()


def test_moving_back_to_the_original_order_is_no_change(app):
    open_splits(app)
    app.locator("#ws-up-material").click()
    app.locator("#ws-down-material").click()
    expect(app.locator("#ws-order-hint")).to_be_hidden()
    app.locator("#ws-splits-apply-btn").click()
    expect(app.locator(".toast", has_text="No changes to apply")).to_be_visible()


def test_drag_and_drop_moves_a_file(app):
    open_splits(app)
    handle = app.locator("#ws-row-constraint .drag-handle")
    target = app.locator("#ws-row-mesh")
    handle.drag_to(target, target_position={"x": 40, "y": 4})    # top edge of Mesh: drop before it
    assert split_rows(app) == ["constraint", "mesh", "section", "material", "step"]
    apply(app)
    assert includes(app) == ["constraint.inp", "mesh.inp", "section.inp", "material.inp", "step.inp"]


def test_categories_still_in_the_mother_stay_where_they_are(app):
    """Only *INCLUDE lines move; a section still written in the mother keeps its place."""
    open_splits(app, cats=("mesh", "material"))
    assert split_rows(app) == ["mesh", "section", "constraint", "material", "step"]
    expect(app.locator("#ws-row-section .move-btn")).to_have_count(0)
    app.locator("#ws-up-material").click()                         # jumps over the mother's rows
    assert split_rows(app) == ["material", "section", "constraint", "mesh", "step"]
    apply(app)
    mother = fetch_text(app, "/api/workspaces/Job-1/files/Job-1.inp")
    assert mother.index("INPUT=material.inp") < mother.index("*Solid Section") < mother.index("INPUT=mesh.inp")


def test_order_and_rename_apply_together(app):
    open_splits(app)
    app.locator("#ws-fn-constraint").fill("ties.inp")
    app.locator("#ws-up-constraint").click()
    apply(app)
    assert includes(app) == ["mesh.inp", "ties.inp", "section.inp", "material.inp", "step.inp"]


def test_a_newly_ticked_category_can_be_moved_after_apply(app):
    open_splits(app, cats=("mesh",))
    expect(app.locator("#ws-row-material .move-btn")).to_have_count(0)    # not a file yet
    app.locator("#ws-sel-material").check()
    app.locator("#ws-splits-apply-btn").click()
    expect(app.locator("#ws-up-material")).to_be_visible(timeout=60_000)
    app.locator("#ws-up-material").click()
    apply(app)
    assert includes(app) == ["material.inp", "mesh.inp"]
