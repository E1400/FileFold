"""File order: moving files in the Splits and Files tabs moves the mother's *INCLUDE lines."""
from __future__ import annotations

import re

from playwright.sync_api import Page, expect

from .conftest import fetch_text
from .test_workflows import make_workspace, row

ALL = ("mesh", "section", "constraint", "material", "step")


def split_rows(page: Page) -> list[str]:
    return page.eval_on_selector_all("#ws-split-config .split-row[data-cat]", "rs => rs.map(r => r.dataset.cat)")


def file_rows(page: Page) -> list[str]:
    return [t.strip() for t in page.locator("#detail-files .filename-text").all_inner_texts()]


def includes(page: Page) -> list[str]:
    return re.findall(r"^\*INCLUDE, INPUT=(\S+)", fetch_text(page, "/api/workspaces/Job-1/files/Job-1.inp"), flags=re.M)


def up(page: Page, cat: str):
    return page.get_by_role("button", name=f"Move {cat} file up")


def down(page: Page, cat: str):
    return page.get_by_role("button", name=f"Move {cat} file down")


def apply(page: Page) -> None:
    page.locator("#ws-splits-apply-btn").click()
    expect(page.locator(".toast", has_text="file order changed")).to_be_visible(timeout=60_000)
    expect(page.locator("#ws-splits-apply-btn")).to_have_text("Apply changes")


def open_splits(page: Page, cats=ALL, subs=()) -> None:
    make_workspace(page, "Job-1.inp", cats=cats, subs=subs)
    page.locator("#tab-btn-splits").click()
    expect(page.locator("#ws-sel-mesh")).to_be_visible()


def drag(page: Page, source, target, where: str = "top") -> None:
    """Drag `source` (a grip) over `target` to its top or bottom edge, step by step, as a hand
    would; the list rearranges live while hovering."""
    box = target.bounding_box()
    y = box["y"] + (6 if where == "top" else box["height"] - 6)
    source.hover()
    page.mouse.down()
    page.mouse.move(box["x"] + 60, box["y"] + box["height"] / 2, steps=8)
    page.mouse.move(box["x"] + 60, y, steps=8)
    page.mouse.up()


# --- Splits tab ---------------------------------------------------------------

def test_rows_follow_the_deck_and_the_arrows_on_the_left_move_a_file(app):
    open_splits(app)
    assert split_rows(app) == list(ALL)                       # deck order, not alphabetical
    assert includes(app) == [f"{c}.inp" for c in ALL]
    # grip and arrows sit at the start of the row, before the checkbox
    handle, box = app.locator("#ws-row-material .sort-handle").bounding_box(), app.locator("#ws-sel-material").bounding_box()
    assert handle["x"] + handle["width"] <= box["x"]
    expect(up(app, "mesh")).to_be_disabled()
    expect(down(app, "material")).to_be_disabled()               # cannot pass the step file
    expect(app.locator("#ws-order-hint")).to_be_hidden()
    up(app, "material").click()
    assert split_rows(app) == ["mesh", "section", "material", "constraint", "step"]
    expect(app.locator("#ws-order-hint")).to_be_visible()
    expect(up(app, "material")).to_be_focused()                  # keyboard users keep their place
    up(app, "material").press("Enter")
    assert split_rows(app) == ["mesh", "material", "section", "constraint", "step"]
    apply(app)
    assert includes(app) == ["mesh.inp", "material.inp", "section.inp", "constraint.inp", "step.inp"]
    assert split_rows(app) == ["mesh", "material", "section", "constraint", "step"]
    expect(app.locator("#ws-order-hint")).to_be_hidden()
    app.locator("#tab-btn-files").click()
    assert file_rows(app)[:4] == ["Job-1.inp", "mesh.inp", "material.inp", "section.inp"]
    # FileFold changed the mother, the person did not: it is not marked as edited.
    expect(row(app, "Job-1.inp").locator(".badge-ok")).to_be_visible()


def test_moving_back_to_the_original_order_is_no_change(app):
    open_splits(app)
    up(app, "material").click()
    down(app, "material").click()
    expect(app.locator("#ws-order-hint")).to_be_hidden()
    app.locator("#ws-splits-apply-btn").click()
    expect(app.locator(".toast", has_text="No changes to apply")).to_be_visible()


def test_dragging_rearranges_live_and_shows_the_landing_slot(app):
    open_splits(app)
    grip = app.locator("#ws-row-constraint .grip")
    target = app.locator("#ws-row-mesh")
    box = target.bounding_box()
    grip.hover()
    app.mouse.down()
    app.mouse.move(box["x"] + 60, box["y"] + box["height"] / 2, steps=8)
    app.mouse.move(box["x"] + 60, box["y"] + 6, steps=8)
    # while still held: the list already shows the new order, the dragged card is the slot
    assert split_rows(app) == ["constraint", "mesh", "section", "material", "step"]
    expect(app.locator("#ws-row-constraint")).to_have_class(re.compile("sort-slot"))
    app.mouse.up()
    expect(app.locator("#ws-row-constraint")).not_to_have_class(re.compile("sort-slot"))
    apply(app)
    assert includes(app) == ["constraint.inp", "mesh.inp", "section.inp", "material.inp", "step.inp"]


def test_escape_while_dragging_puts_everything_back(app):
    open_splits(app)
    grip = app.locator("#ws-row-constraint .grip")
    box = app.locator("#ws-row-mesh").bounding_box()
    grip.hover()
    app.mouse.down()
    app.mouse.move(box["x"] + 60, box["y"] + 6, steps=10)
    app.keyboard.press("Escape")
    app.mouse.up()
    assert split_rows(app) == list(ALL)
    expect(app.locator("#ws-order-hint")).to_be_hidden()


def test_a_file_that_cannot_move_says_why(app):
    """User-reported: some rows could not be dragged and nothing said why."""
    open_splits(app, cats=("mesh", "material", "step"))
    expect(app.locator("#ws-row-constraint .sort-handle.fixed")).to_be_visible()
    for cat, reason in [("constraint", "constraint is still part of the mother file"),
                        ("step", "The step file stays last")]:
        app.locator(f"#ws-row-{cat} .grip").click()
        expect(app.locator(".toast", has_text=reason).last).to_be_visible()
    # trying to drag it says the same, and nothing moves
    drag(app, app.locator("#ws-row-constraint .grip"), app.locator("#ws-row-mesh"))
    expect(app.locator(".toast", has_text="constraint is still part of the mother file")).to_have_count(2)
    assert split_rows(app) == list(ALL)
    # ticked but not applied yet
    app.locator("#ws-sel-constraint").check()
    app.locator("#ws-row-constraint .grip").click()
    expect(app.locator(".toast", has_text="Apply changes first").last).to_be_visible()


def test_categories_still_in_the_mother_stay_where_they_are(app):
    """Only *INCLUDE lines move; a section still written in the mother keeps its place."""
    open_splits(app, cats=("mesh", "material"))
    assert split_rows(app) == ["mesh", "section", "constraint", "material", "step"]
    up(app, "material").click()                                   # jumps over the mother's rows
    assert split_rows(app) == ["material", "section", "constraint", "mesh", "step"]
    apply(app)
    mother = fetch_text(app, "/api/workspaces/Job-1/files/Job-1.inp")
    assert mother.index("INPUT=material.inp") < mother.index("*Solid Section") < mother.index("INPUT=mesh.inp")


def test_order_and_rename_apply_together(app):
    open_splits(app)
    app.locator("#ws-fn-constraint").fill("ties.inp")
    up(app, "constraint").click()
    apply(app)
    assert includes(app) == ["mesh.inp", "ties.inp", "section.inp", "material.inp", "step.inp"]


# --- Files tab ----------------------------------------------------------------

def test_files_tab_moves_a_file_with_its_sub_files_straight_away(app):
    make_workspace(app, "Job-1.inp", cats=("mesh", "section", "material"), subs=("mesh:nodes",))
    assert file_rows(app) == ["Job-1.inp", "mesh.inp", "mesh-nodes.inp", "section.inp", "material.inp"]
    expect(app.get_by_role("button", name="Move mesh.inp up")).to_be_disabled()
    app.get_by_role("button", name="Move mesh.inp down").click()
    expect(app.locator(".toast", has_text="File order changed")).to_be_visible()
    expect(app.locator("#detail-files .filename-text").nth(1)).to_have_text("section.inp")
    assert file_rows(app) == ["Job-1.inp", "section.inp", "mesh.inp", "mesh-nodes.inp", "material.inp"]
    assert includes(app) == ["section.inp", "mesh.inp", "material.inp"]
    # drag material.inp to the top of the files
    drag(app, row(app, "material.inp").locator(".grip"), row(app, "section.inp"))
    expect(app.locator(".toast", has_text="File order changed")).to_have_count(2)
    expect(app.locator("#detail-files .filename-text").nth(1)).to_have_text("material.inp")
    assert includes(app) == ["material.inp", "section.inp", "mesh.inp"]
    # the Splits tab shows the new order too
    app.locator("#tab-btn-splits").click()
    expect(app.locator("#ws-sel-mesh")).to_be_visible()
    assert [c for c in split_rows(app) if c in ("material", "section", "mesh")] == ["material", "section", "mesh"]


def test_files_tab_says_why_the_mother_and_sub_files_do_not_move(app):
    make_workspace(app, "Job-1.inp", cats=("mesh", "step"), subs=("mesh:nodes",))
    for name, reason in [("Job-1.inp", "stays at the top"), ("mesh-nodes.inp", "Sub-files move with their parent"),
                         ("step.inp", "The step file stays last")]:
        row(app, name).locator(".grip").click()
        expect(app.locator(".toast", has_text=reason).last).to_be_visible()
    drag(app, row(app, "mesh-nodes.inp").locator(".grip"), row(app, "Job-1.inp"))
    assert file_rows(app) == ["Job-1.inp", "mesh.inp", "mesh-nodes.inp", "step.inp"]
