"""Splits tab: choices that are not applied yet are visible, kept and never lost silently.

From the UX review (SWE/previews/ux-review-2026-10-16): unapplied choices were thrown away
when switching Files -> Splits, nothing marked what Apply would do, "No changes to apply" only
appeared after clicking, and the Apply button sat at the bottom of a long page.
"""
from __future__ import annotations

from playwright.sync_api import Page, expect

from .test_ui import create, open_new_workspace, upload
from .test_workflows import make_workspace


def splits(page: Page) -> None:
    page.locator("#tab-btn-splits").click()
    expect(page.locator("#ws-split-config .split-row").first).to_be_visible()


def bar(page: Page):
    return page.locator("#splits-pending-bar")


def test_unapplied_choices_survive_a_tab_switch(app):
    make_workspace(app, "Job-1.inp", cats=("mesh", "material"))
    splits(app)
    app.locator("#ws-sel-material").uncheck()
    app.locator("#ws-sel-section").check()
    app.locator("#tab-btn-files").click()
    splits(app)
    expect(app.locator("#ws-sel-material")).not_to_be_checked()
    expect(app.locator("#ws-sel-section")).to_be_checked()
    expect(bar(app)).to_contain_text("2 changes")


def test_the_bar_counts_changes_and_discard_restores_the_workspace(app):
    make_workspace(app, "Job-1.inp", cats=("mesh",))
    splits(app)
    expect(bar(app)).to_contain_text("No changes")
    expect(bar(app).get_by_role("button", name="Apply changes")).to_be_disabled()
    app.locator("#ws-sel-material").check()
    app.locator("#ws-sub-mesh-nodes").check()
    expect(bar(app)).to_contain_text("2 changes")
    expect(bar(app).get_by_role("button", name="Apply changes")).to_be_enabled()
    bar(app).get_by_role("button", name="Discard").click()
    expect(app.locator("#ws-sel-material")).not_to_be_checked()
    expect(app.locator("#ws-sub-mesh-nodes")).not_to_be_checked()
    expect(bar(app)).to_contain_text("No changes")


def test_rows_say_what_apply_will_do(app):
    make_workspace(app, "Job-1.inp", cats=("mesh", "material"))
    splits(app)
    app.locator("#ws-sel-material").uncheck()
    expect(app.locator("#ws-row-material .pending-mark")).to_contain_text("folds back into Job-1.inp")
    app.locator("#ws-sel-section").check()
    expect(app.locator("#ws-row-section .pending-mark")).to_contain_text("new")
    app.fill("#ws-fn-mesh", "geometry.inp")
    expect(app.locator("#ws-row-mesh .pending-mark")).to_contain_text("renamed")
    app.locator("#ws-sel-material").check()                     # back to what it was
    expect(app.locator("#ws-row-material .pending-mark")).to_have_count(0)


def test_apply_is_always_reachable_without_scrolling(app):
    app.set_viewport_size({"width": 1024, "height": 768})
    make_workspace(app, "mmxmn.inp", cats=("mesh", "contact", "loads"))
    splits(app)
    app.locator("#ws-sel-step").check()
    apply_btn = bar(app).get_by_role("button", name="Apply changes")
    expect(apply_btn).to_be_in_viewport()
    apply_btn.click()
    expect(bar(app)).to_contain_text("No changes", timeout=60_000)
    app.locator("#tab-btn-files").click()
    expect(app.locator("#detail-files .filename-text", has_text="step.inp")).to_have_count(1)


def test_leaving_with_unapplied_changes_asks_first(app):
    make_workspace(app, "Job-1.inp", cats=("mesh",))
    splits(app)
    app.locator("#ws-sel-material").check()
    app.get_by_role("button", name="← Back").first.click()
    dialog = app.locator("#pending-dialog")
    expect(dialog).to_be_visible()
    dialog.get_by_role("button", name="Keep editing").click()
    expect(app.locator("#view-detail")).to_be_visible()
    expect(app.locator("#ws-sel-material")).to_be_checked()

    app.get_by_role("button", name="← Back").first.click()
    dialog.get_by_role("button", name="Apply and leave").click()
    expect(app.locator("#view-home")).to_be_visible(timeout=60_000)
    expect(app.locator(".workspace-card[data-ws='Job-1']")).to_contain_text("material")


def test_discard_from_the_leave_dialog_leaves_without_changing_anything(app):
    make_workspace(app, "Job-1.inp", cats=("mesh",))
    splits(app)
    app.locator("#ws-sel-material").check()
    app.get_by_role("button", name="New workspace", exact=True).first.click()   # the sidebar's +
    dialog = app.locator("#pending-dialog")
    expect(dialog).to_be_visible()
    dialog.get_by_role("button", name="Discard changes").click()
    expect(app.locator("#view-new-workspace")).to_be_visible()


def test_splits_tab_lists_categories_in_the_same_order_as_new_workspace(app):
    open_new_workspace(app)
    upload(app, "mmxmn.inp")
    create_order = [i.get_attribute("id")[len("sel-"):] for i in app.locator("#split-config input[id^='sel-']").all()]
    app.locator("#sel-mesh").check()
    create(app)
    splits(app)
    tab_order = [i.get_attribute("id")[len("ws-sel-"):] for i in app.locator("#ws-split-config input[id^='ws-sel-']").all()]
    assert [c for c in tab_order if c in create_order] == create_order


def test_the_leave_dialog_looks_like_the_editors_dialog(app):
    make_workspace(app, "Job-1.inp", cats=("mesh",))
    splits(app)
    app.locator("#ws-sel-material").check()
    app.get_by_role("button", name="← Back").first.click()
    style = lambda sel: app.evaluate(f"""() => {{ const d = document.querySelector('{sel}'); const s = getComputedStyle(d);
        return [s.paddingTop, s.borderTopWidth, s.maxWidth]; }}""")
    pending = style("#pending-dialog")
    assert pending[0] != "0px", pending                       # styled, not the browser default
    app.locator("#pending-dialog").get_by_role("button", name="Keep editing").click()
