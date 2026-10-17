"""Result tree: see the files a split will make, with exact line counts, before committing
(UX review, proposal 1). The numbers shown must equal the files the split really writes."""
from __future__ import annotations

from playwright.sync_api import Page, expect

from .test_ui import create, open_new_workspace, upload
from .test_workflows import make_workspace


def shown(page: Page, tree: str) -> dict[str, tuple[int | None, str]]:
    """{filename: (lines or None, mark)} from a rendered result tree."""
    rows = page.evaluate(f"""() => [...document.querySelectorAll('{tree} .result-row')].map(r => [
        r.dataset.file, r.querySelector('.result-lines').textContent.replace(/,/g, ''),
        (r.querySelector('.result-mark') || {{}}).textContent || ''])""")
    return {f: (int(n) if n else None, m) for f, n, m in rows}


def actual(page: Page, ws: str) -> dict[str, int]:
    data = page.evaluate(f"() => api('GET', '/api/workspaces/{ws}')")
    return {f["filename"]: f["line_count"] for f in data["files"] if f["exists"]}


def test_new_workspace_shows_the_files_and_exact_line_counts_before_create(app):
    open_new_workspace(app)
    upload(app, "Job-1.inp")
    tree = "#result-tree"
    expect(app.locator(f"{tree} .result-row")).to_have_count(1)            # just the mother
    expect(app.locator(f"{tree} .result-row.role-mother")).to_contain_text("Job-1.inp")
    app.locator("#sel-mesh").check()
    app.locator("#sub-mesh-nodes").check()
    app.locator("#sel-material").check()
    expect(app.locator(f"{tree} .result-row")).to_have_count(4)
    expect(app.locator("#result-count")).to_have_text("4 files")
    predicted = {f: n for f, (n, _) in shown(app, tree).items()}
    assert set(predicted) == {"Job-1.inp", "mesh.inp", "mesh-nodes.inp", "material.inp"}
    app.locator("#sel-material").uncheck()                                   # follows every tick
    expect(app.locator(f"{tree} .result-row")).to_have_count(3)
    app.locator("#sel-material").check()
    create(app)
    assert actual(app, "Job-1") == predicted


def test_renaming_a_file_renames_it_in_the_result(app):
    open_new_workspace(app)
    upload(app, "Job-1.inp")
    app.locator("#sel-mesh").check()
    app.fill("#fn-mesh", "geometry.inp")
    expect(app.locator("#result-tree .result-row[data-file='geometry.inp']")).to_have_count(1)


def test_splits_tab_shows_what_apply_will_make_and_the_numbers_are_exact(app):
    make_workspace(app, "Job-1.inp", cats=("mesh", "material"))
    app.locator("#tab-btn-splits").click()
    tree = "#ws-result-tree"
    expect(app.locator(f"{tree} .result-row")).to_have_count(3)             # nothing changed yet
    app.locator("#ws-sel-material").uncheck()
    app.locator("#ws-sel-section").check()
    app.locator("#ws-sub-mesh-nodes").check()
    rows = shown(app, tree)
    assert rows["material.inp"] == (None, "folds back into Job-1.inp")
    assert rows["section.inp"][1] == "new" and rows["mesh-nodes.inp"][1] == "new"
    predicted = {f: n for f, (n, m) in rows.items() if not m.startswith("folds back")}
    app.locator("#ws-splits-apply-btn").click()
    expect(app.locator("#splits-pending-count")).to_have_text("No changes", timeout=60_000)
    assert actual(app, "Job-1") == predicted
    after = shown(app, tree)                                                # and the tree now shows that state
    assert all(m == "" for _, m in after.values()), after


def test_folding_back_finer_splits_is_shown_too(app):
    make_workspace(app, "Job-1.inp", cats=("mesh",), subs=("mesh:nodes",))
    app.locator("#tab-btn-splits").click()
    app.locator("#ws-sub-mesh-nodes").uncheck()
    expect(app.locator("#ws-result-tree .result-row[data-file='mesh-nodes.inp'] .result-mark")).to_contain_text("folds back into mesh.inp")
