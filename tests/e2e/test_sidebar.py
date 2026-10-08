"""Sidebar: activity bar, collapsible panel, workspace group, search."""
from __future__ import annotations

from playwright.sync_api import Page, expect

from .test_ui import create, open_new_workspace, upload


def make_workspace(page: Page) -> None:
    open_new_workspace(page)
    upload(page, "Job-1.inp")
    page.locator("#sel-mesh").check()
    create(page)


def test_icon_toggles_panel_like_vscode(app):
    side = app.locator("#side-panel")
    expect(side).to_be_visible()
    expect(app.locator("#act-workspaces")).to_have_class("act-btn active")
    app.locator("#act-workspaces").click()          # active icon collapses
    expect(side).to_be_hidden()
    expect(app.locator("#act-workspaces")).not_to_have_class("act-btn active")
    app.locator("#act-search").click()              # another icon reopens on that panel
    expect(side).to_be_visible()
    expect(app.locator("#panel-search")).to_be_visible()
    expect(app.locator("#panel-workspaces")).to_be_hidden()
    expect(app.locator("#search-input")).to_be_focused()


def test_collapse_state_survives_reload(app):
    app.locator("#act-workspaces").click()
    expect(app.locator("#side-panel")).to_be_hidden()
    app.reload()
    app.wait_for_selector("#static-banner", state="detached", timeout=90_000)
    expect(app.locator("#side-panel")).to_be_hidden()
    app.locator("#act-workspaces").click()
    expect(app.locator("#side-panel")).to_be_visible()


def test_workspace_group_collapses_and_counts(app):
    make_workspace(app)
    expect(app.locator("#ws-count")).to_have_text("1")
    expect(app.locator("#ws-list .ws-item")).to_have_count(1)
    app.locator("#ws-group-toggle").click()
    expect(app.locator("#ws-list")).to_be_hidden()
    app.locator("#ws-group-toggle").click()
    expect(app.locator("#ws-list .ws-item")).to_be_visible()
    app.locator("#ws-list .ws-item").click()
    expect(app.locator("#view-detail")).to_be_visible()
    expect(app.locator("#ws-list .ws-item.active")).to_have_count(1)


def test_info_icon_opens_info_and_marks_active(app):
    app.locator("#nav-info").click()
    expect(app.locator("#view-help")).to_be_visible()
    expect(app.locator("#nav-info")).to_have_class("act-btn active")


def test_search_filters_workspace_titles(app):
    make_workspace(app)
    app.locator("#act-search").click()
    box = app.locator("#search-input")
    box.fill("job")
    expect(app.locator("#search-results .ws-item")).to_have_count(1)
    app.locator("#search-results .ws-item").click()
    expect(app.locator("#view-detail")).to_be_visible()
    box.fill("reimport")  # help topics and categories are not searched
    expect(app.locator("#search-results .panel-empty")).to_contain_text("No results")
    box.press("Escape")
    expect(box).to_have_value("")
