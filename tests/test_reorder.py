"""Reordering child files: the mother's *INCLUDE lines change places, nothing else moves."""
from pathlib import Path

import pytest

from filefold import service
from filefold.core.keywords import Category
from filefold.core.splitter import SplitSelection, SubSplitSelection, read_raw
from filefold.core.workspace import Workspace, permute_includes, planned_order

FIXTURES = Path(__file__).parent / "fixtures"
SELS = [("mesh", "mesh.inp"), ("section", "section.inp"), ("material", "material.inp"),
        ("constraint", "constraint.inp"), ("step", "step.inp")]


@pytest.fixture()
def ws(tmp_path) -> Workspace:
    sels = [SplitSelection(Category(c), f) for c, f in SELS]
    sels[0].sub_selections = [SubSplitSelection("nodes", "mesh-nodes.inp")]
    return Workspace.create(tmp_path / "Job-1", FIXTURES / "Job-1.inp", sels)


def recombined(ws: Workspace) -> str:
    """The whole deck as it would be exported folded back into one file."""
    import re
    def expand(name):
        return re.sub(r"^\*INCLUDE, INPUT=(\S+)\n", lambda m: expand(m.group(1)), read_raw(ws.path / name), flags=re.M)
    return expand(ws.source_name)


def test_planned_order_moves_only_the_listed_files_among_their_own_places():
    cur = ["a", "b", "c", "d"]
    assert planned_order(cur, ["c", "a"]) == ["c", "b", "a", "d"]
    assert planned_order(cur, ["d", "c", "b", "a"]) == ["d", "c", "b", "a"]
    assert planned_order(cur, []) == cur
    assert planned_order(cur, ["b", "b", "x"]) == cur          # duplicates and strangers ignored


def test_permute_keeps_every_other_byte_and_crlf():
    text = "*HEADING\r\n*INCLUDE, INPUT=a.inp\r\n*NODE\r\n1,0\r\n*Include,input=b.inp  \r\n*END\r\n"
    out = permute_includes(text, {"a.inp", "b.inp"}, ["b.inp", "a.inp"])
    assert out == "*HEADING\r\n*INCLUDE, INPUT=b.inp\r\n*NODE\r\n1,0\r\n*Include,input=a.inp  \r\n*END\r\n"


def test_reorder_swaps_includes_and_the_deck_follows(ws, monkeypatch):
    before = ws.include_order()
    assert before == ["mesh.inp", "section.inp", "constraint.inp", "material.inp", "step.inp"]
    deck_before = recombined(ws)
    mother_before = read_raw(ws.path / ws.source_name)
    ws.reorder_children(["material.inp", "mesh.inp"])
    assert ws.include_order() == ["material.inp", "section.inp", "constraint.inp", "mesh.inp", "step.inp"]
    mother = read_raw(ws.path / ws.source_name)
    # only the two include lines changed
    changed = [(a, b) for a, b in zip(mother_before.splitlines(), mother.splitlines()) if a != b]
    assert changed == [("*INCLUDE, INPUT=mesh.inp", "*INCLUDE, INPUT=material.inp"),
                       ("*INCLUDE, INPUT=material.inp", "*INCLUDE, INPUT=mesh.inp")]
    # the deck holds the same lines, materials now first
    deck = recombined(ws)
    assert sorted(deck.splitlines()) == sorted(deck_before.splitlines())
    assert deck.index("*Material") < deck.index("*Node")
    # FileFold's own change does not mark the mother as edited; the manifest follows the order
    reloaded = Workspace.load(ws.path)
    assert [s.filename for s in reloaded.selections][:1] == ["material.inp"]
    names = list(reloaded.file_records)
    assert names[0] == "Job-1.inp" and names.index("mesh-nodes.inp") == names.index("mesh.inp") + 1
    status = {f["filename"]: f for f in service_status(ws, monkeypatch)}
    assert not status["Job-1.inp"]["manually_edited"]


def service_status(ws, monkeypatch):
    monkeypatch.setattr("filefold.api.server.WORKSPACE_BASE", ws.path.parent)
    return service.get_workspace(ws.path.name)["files"]


def test_a_hand_edited_mother_stays_marked_as_edited(ws, monkeypatch):
    p = ws.path / ws.source_name
    p.write_text(read_raw(p) + "** a note\n", encoding="utf-8")
    ws.reorder_children(["section.inp", "mesh.inp"])
    status = {f["filename"]: f for f in service_status(ws, monkeypatch)}
    assert status["Job-1.inp"]["manually_edited"]
    assert "** a note" in read_raw(p)


def test_reimport_keeps_the_chosen_order(ws, tmp_path):
    ws.reorder_children(["material.inp", "mesh.inp"])
    new = tmp_path / "Job-1.inp"
    new.write_bytes((FIXTURES / "Job-1.inp").read_bytes())
    preview = ws.reimport_preview(new)
    ws.reimport_apply(new, preview, set())
    assert ws.include_order() == ["material.inp", "section.inp", "constraint.inp", "mesh.inp", "step.inp"]


@pytest.fixture()
def svc(tmp_path, monkeypatch):
    monkeypatch.setattr("filefold.api.server.WORKSPACE_BASE", tmp_path)
    service.create_workspace("J", "Job-1.inp", (FIXTURES / "Job-1.inp").read_bytes(),
                             [{"category": c, "filename": f} for c, f in SELS])
    return service


def test_service_reports_the_order_and_category_order(svc):
    d = svc.get_workspace("J")
    assert d["include_order"] == ["mesh.inp", "section.inp", "constraint.inp", "material.inp", "step.inp"]
    assert d["category_order"] == ["mesh", "section", "constraint", "material", "step"]
    out = svc.reorder_files("J", ["constraint.inp", "mesh.inp"])
    assert out["order"] == ["constraint.inp", "section.inp", "mesh.inp", "material.inp", "step.inp"]
    assert svc.get_workspace("J")["category_order"] == ["constraint", "section", "mesh", "material", "step"]


def test_model_data_can_never_move_past_the_step_file(svc):
    for order in (["step.inp", "mesh.inp"], ["step.inp", "material.inp"], ["section.inp", "step.inp", "mesh.inp"]):
        with pytest.raises(service.ServiceError) as e:
            svc.reorder_files("J", order)
        assert e.value.code == "step_order"
    assert svc.get_workspace("J")["include_order"][-1] == "step.inp"


def test_unknown_files_are_refused(svc):
    with pytest.raises(service.ServiceError) as e:
        svc.reorder_files("J", ["mesh.inp", "nope.inp"])
    assert e.value.code == "not_extracted" and e.value.value == "nope.inp"


def test_an_order_that_changes_nothing_is_fine(svc):
    assert svc.reorder_files("J", ["material.inp", "step.inp"])["order"][-2:] == ["material.inp", "step.inp"]


def test_api_and_cli_reorder(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from typer.testing import CliRunner

    from filefold.api.main import app
    from filefold.cli.main import app as cli
    monkeypatch.setattr("filefold.api.server.WORKSPACE_BASE", tmp_path)
    service.create_workspace("J", "Job-1.inp", (FIXTURES / "Job-1.inp").read_bytes(),
                             [{"category": c, "filename": f} for c, f in SELS])
    r = TestClient(app).post("/api/workspaces/J/reorder", json={"order": ["material.inp", "mesh.inp"]})
    assert r.status_code == 200 and r.json()["order"][0] == "material.inp"
    r = TestClient(app).post("/api/workspaces/J/reorder", json={"order": ["step.inp", "mesh.inp"]})
    assert r.status_code == 400 and r.json()["code"] == "step_order"
    out = CliRunner().invoke(cli, ["--workspaces", str(tmp_path), "workspace", "reorder", "J", "mesh.inp", "material.inp"])
    assert out.exit_code == 0, out.output
    assert service.get_workspace("J")["include_order"][0] == "mesh.inp"
