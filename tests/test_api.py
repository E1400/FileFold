"""API endpoint tests using FastAPI TestClient."""
import io
import json
import re
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from filefold.api.main import app
from filefold.api.server import WORKSPACE_BASE

FIXTURES = Path(__file__).parent / "fixtures"
FEMPY = FIXTURES / "fempy_example.inp"


@pytest.fixture(autouse=True)
def isolated_workspace(tmp_path, monkeypatch):
    """Point WORKSPACE_BASE at a temp dir so tests don't touch ~/.filefold."""
    monkeypatch.setattr("filefold.api.server.WORKSPACE_BASE", tmp_path)
    # Routes resolve workspaces through filefold.api.server, which reads WORKSPACE_BASE
    # at call time, so patching it above redirects every route module.


@pytest.fixture()
def client():
    return TestClient(app)


def _upload(client, path: Path, endpoint: str, extra: dict | None = None):
    """POST a file to an endpoint, optionally with extra form fields."""
    data = extra or {}
    with open(path, "rb") as fh:
        return client.post(endpoint, files={"file": (path.name, fh, "text/plain")}, data=data)


# ---------------------------------------------------------------------------
# Inspect
# ---------------------------------------------------------------------------

def test_inspect_returns_block_tree(client):
    r = _upload(client, FEMPY, "/api/inspect")
    assert r.status_code == 200
    body = r.json()
    assert body["filename"] == FEMPY.name
    assert isinstance(body["blocks"], list)
    assert len(body["blocks"]) > 0
    # Each block has expected keys
    block = body["blocks"][0]
    assert {"keyword", "category", "line_start", "line_end", "children"} <= block.keys()


def test_inspect_unknown_file_still_parses(client):
    r = _upload(client, FIXTURES / "test_2.inp", "/api/inspect")
    assert r.status_code == 200
    assert len(r.json()["blocks"]) > 0


# ---------------------------------------------------------------------------
# Workspace CRUD
# ---------------------------------------------------------------------------

def test_list_workspaces_empty(client):
    r = client.get("/api/workspaces")
    assert r.status_code == 200
    assert r.json()["workspaces"] == []


def test_create_workspace_no_split(client):
    r = _upload(client, FEMPY, "/api/workspaces", {"name": "ws1", "selections": "[]"})
    assert r.status_code == 200
    body = r.json()
    assert body["workspace"] == "ws1"
    assert FEMPY.name in body["files"]


def test_create_workspace_with_split(client):
    sels = json.dumps([
        {"category": "mesh", "filename": "mesh.inp"},
        {"category": "material", "filename": "material.inp"},
    ])
    r = _upload(client, FEMPY, "/api/workspaces", {"name": "ws-split", "selections": sels})
    assert r.status_code == 200
    files = r.json()["files"]
    assert "mesh.inp" in files
    assert "material.inp" in files


def test_create_duplicate_returns_400(client):
    _upload(client, FEMPY, "/api/workspaces", {"name": "dup", "selections": "[]"})
    r = _upload(client, FEMPY, "/api/workspaces", {"name": "dup", "selections": "[]"})
    assert r.status_code == 400


def test_list_workspaces_after_create(client):
    _upload(client, FEMPY, "/api/workspaces", {"name": "alpha", "selections": "[]"})
    _upload(client, FEMPY, "/api/workspaces", {"name": "beta", "selections": "[]"})
    r = client.get("/api/workspaces")
    assert r.json()["workspaces"] == ["alpha", "beta"]


def test_get_workspace_detail(client):
    _upload(client, FEMPY, "/api/workspaces", {"name": "detail-ws", "selections": "[]"})
    r = client.get("/api/workspaces/detail-ws")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "detail-ws"
    assert body["source_name"] == FEMPY.name
    assert isinstance(body["files"], list)
    assert any(f["filename"] == FEMPY.name for f in body["files"])


def test_get_workspace_not_found(client):
    r = client.get("/api/workspaces/does-not-exist")
    assert r.status_code == 404


def test_delete_workspace(client):
    _upload(client, FEMPY, "/api/workspaces", {"name": "to-delete", "selections": "[]"})
    r = client.delete("/api/workspaces/to-delete")
    assert r.status_code == 200
    assert client.get("/api/workspaces/to-delete").status_code == 404


# ---------------------------------------------------------------------------
# File get / save
# ---------------------------------------------------------------------------

def _create_split_ws(client, name="edit-ws"):
    sels = json.dumps([{"category": "mesh", "filename": "mesh.inp"}])
    _upload(client, FEMPY, "/api/workspaces", {"name": name, "selections": sels})
    return name


def test_get_file_returns_text(client):
    name = _create_split_ws(client)
    r = client.get(f"/api/workspaces/{name}/files/mesh.inp")
    assert r.status_code == 200
    assert "*NODE" in r.text or "*ELEMENT" in r.text or len(r.text) > 0


def test_get_mother_file(client):
    _upload(client, FEMPY, "/api/workspaces", {"name": "mother-ws", "selections": "[]"})
    r = client.get(f"/api/workspaces/mother-ws/files/{FEMPY.name}")
    assert r.status_code == 200
    assert len(r.text) > 0


def test_get_file_not_found(client):
    _upload(client, FEMPY, "/api/workspaces", {"name": "nf-ws", "selections": "[]"})
    r = client.get("/api/workspaces/nf-ws/files/nonexistent.inp")
    assert r.status_code == 404


def test_save_file_and_read_back(client):
    name = _create_split_ws(client)
    new_content = "** edited by test\n*NODE\n1,0.0,0.0,0.0\n"
    r = client.put(
        f"/api/workspaces/{name}/files/mesh.inp",
        content=new_content,
        headers={"Content-Type": "text/plain"},
    )
    assert r.status_code == 200
    assert r.json()["saved"] == "mesh.inp"

    r2 = client.get(f"/api/workspaces/{name}/files/mesh.inp")
    assert r2.text == new_content


def test_save_file_marks_as_edited(client):
    name = _create_split_ws(client)
    client.put(
        f"/api/workspaces/{name}/files/mesh.inp",
        content="** changed\n",
        headers={"Content-Type": "text/plain"},
    )
    detail = client.get(f"/api/workspaces/{name}").json()
    mesh = next(f for f in detail["files"] if f["filename"] == "mesh.inp")
    assert mesh["manually_edited"] is True


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def test_export_returns_zip_with_all_files(client):
    sels = json.dumps([{"category": "mesh", "filename": "mesh.inp"}])
    _upload(client, FEMPY, "/api/workspaces", {"name": "exp-ws", "selections": sels})
    r = client.get("/api/workspaces/exp-ws/export")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    names = zf.namelist()
    assert FEMPY.name in names
    assert "mesh.inp" in names


# ---------------------------------------------------------------------------
# Reimport preview
# ---------------------------------------------------------------------------

def test_reimport_preview_no_change(client):
    _create_split_ws(client, "rp-ws")
    r = _upload(client, FEMPY, "/api/workspaces/rp-ws/reimport/preview")
    assert r.status_code == 200
    body = r.json()
    assert "blocks" in body
    assert body["safe_to_update"] == []
    assert body["needs_attention"] == []
    assert len(body["unchanged"]) == 1
    assert body["unchanged"][0]["filename"] == "mesh.inp"


def test_reimport_preview_returns_block_tree(client):
    _create_split_ws(client, "rp-blocks")
    r = _upload(client, FEMPY, "/api/workspaces/rp-blocks/reimport/preview")
    assert r.status_code == 200
    assert isinstance(r.json()["blocks"], list)
    assert len(r.json()["blocks"]) > 0


# ---------------------------------------------------------------------------
# Reimport apply
# ---------------------------------------------------------------------------

def test_reimport_apply_updates_mother(client, tmp_path):
    name = _create_split_ws(client, "ra-ws")

    # Create a modified version of the mother
    original = FEMPY.read_text(encoding="utf-8")
    modified = "** NEW HEADER\n" + original
    new_mother = tmp_path / FEMPY.name
    new_mother.write_text(modified, encoding="utf-8")

    r = client.post(
        f"/api/workspaces/{name}/reimport/apply",
        files={"file": (new_mother.name, new_mother.read_bytes(), "text/plain")},
        data={"filenames": "[]", "added_selections": "[]"},
    )
    assert r.status_code == 200


def test_reimport_apply_adds_new_selection(client, tmp_path):
    # Workspace starts with only mesh; reimport adds material
    _create_split_ws(client, "ra-add")

    new_sel = json.dumps([{"category": "material", "filename": "material.inp"}])
    r = client.post(
        "/api/workspaces/ra-add/reimport/apply",
        files={"file": (FEMPY.name, FEMPY.read_bytes(), "text/plain")},
        data={"filenames": "[]", "added_selections": new_sel},
    )
    assert r.status_code == 200
    detail = client.get("/api/workspaces/ra-add").json()
    filenames = [f["filename"] for f in detail["files"]]
    assert "material.inp" in filenames


# ---------------------------------------------------------------------------
# Contact / loads sub-splits end to end (real deck with contact pairs and BCs)
# ---------------------------------------------------------------------------

def test_contact_and_loads_subsplits_via_api(client):
    mmxmn = FIXTURES / "mmxmn.inp"
    sels = [
        {"category": "contact", "filename": "contact.inp", "sub_selections": [
            {"sub_category": "pairs", "filename": "contact-pairs.inp"}]},
        {"category": "loads", "filename": "loads.inp", "sub_selections": [
            {"sub_category": "amplitudes", "filename": "loads-amplitudes.inp"}]},
    ]
    r = _upload(client, mmxmn, "/api/workspaces",
                {"name": "sub", "selections": json.dumps(sels)})
    assert r.status_code == 200, r.text
    files = set(r.json()["files"])
    assert {"contact.inp", "contact-pairs.inp", "loads.inp", "loads-amplitudes.inp"} <= files

    detail = client.get("/api/workspaces/sub").json()
    assert "pairs" in detail["available_sub_cats"]["contact"]
    assert "amplitudes" in detail["available_sub_cats"]["loads"]
    assert "contact" in {o for o in client.get("/api/sub-options").json()}

    assert "*contact pair" in client.get("/api/workspaces/sub/files/contact-pairs.inp").text.lower()


def test_constraint_category_extractable_and_reported(client):
    job = FIXTURES / "Job-1.inp"
    sels = [{"category": "constraint", "filename": "constraints.inp"}]
    r = _upload(client, job, "/api/workspaces", {"name": "con", "selections": json.dumps(sels)})
    assert r.status_code == 200, r.text
    assert "constraints.inp" in r.json()["files"]
    assert "rigid body" in client.get("/api/workspaces/con/files/constraints.inp").text.lower()


# ---------------------------------------------------------------------------
# Static frontend
# ---------------------------------------------------------------------------

def test_every_asset_linked_from_index_is_served(client):
    import re
    html = client.get("/").text
    assets = re.findall(r'(?:src|href)="(static/[^"]+)"', html)
    assert len(assets) >= 8  # app.css + the script files
    for url in assets:
        r = client.get(url)
        assert r.status_code == 200 and len(r.content) > 0, url


def test_index_has_no_inline_script_or_style(client):
    html = client.get("/").text
    assert "<style" not in html
    assert not re.search(r"<script(?![^>]*src=)", html)


# ---------------------------------------------------------------------------
# Errors carry a code (and the form field) so the UI can word them itself
# ---------------------------------------------------------------------------

def test_errors_name_their_code_and_field(client):
    job1 = FIXTURES / "Job-1.inp"
    assert _upload(client, job1, "/api/workspaces", {"name": "a"}).status_code == 200
    assert _upload(client, job1, "/api/workspaces", {"name": "b"}).status_code == 200

    r = _upload(client, job1, "/api/workspaces", {"name": "a"})
    assert r.status_code == 400
    assert r.json() | {"detail": None} == {"detail": None, "code": "workspace_exists", "field": "name", "value": "a"}

    r = _upload(client, job1, "/api/workspaces", {"name": "../evil"})
    assert (r.json()["code"], r.json()["field"]) == ("invalid_name", "name")

    r = client.patch("/api/workspaces/a", json={"name": "b"})
    assert (r.status_code, r.json()["code"], r.json()["value"]) == (400, "workspace_exists", "b")

    r = client.get("/api/workspaces/nope")
    assert (r.status_code, r.json()["code"]) == (404, "workspace_not_found")

    client.post("/api/workspaces/a/extract", json={"selections": [{"category": "mesh", "filename": "mesh.inp", "sub_selections": []},
                                                                  {"category": "material", "filename": "material.inp", "sub_selections": []}]})
    r = client.post("/api/workspaces/a/rename-file", json={"old_filename": "mesh.inp", "new_filename": "material.inp"})
    assert (r.status_code, r.json()["code"], r.json()["field"], r.json()["value"]) == (400, "filename_taken", "filename", "material.inp")
    r = client.post("/api/workspaces/a/resplit-child", json={"category": "mesh", "sub_selections": [
        {"sub_category": "nodes", "filename": "material.inp"}]})
    assert (r.json()["code"], r.json()["value"]) == ("filename_taken", "material.inp")


# ---------------------------------------------------------------------------
# Re-import review shows what changed (side-by-side rows), and names the mother
# ---------------------------------------------------------------------------

def test_reimport_preview_includes_a_side_by_side_diff_and_the_mother(client, tmp_path):
    job1 = FIXTURES / "Job-1.inp"
    _upload(client, job1, "/api/workspaces", {"name": "rd", "selections": json.dumps(
        [{"category": "mesh", "filename": "mesh.inp", "sub_selections": []}])})
    from filefold import service
    service.write_file("rd", "mesh.inp", b"** mine\r\n" + service.read_file("rd", "mesh.inp"))
    changed = tmp_path / "Job-1.inp"
    changed.write_bytes(job1.read_bytes().replace(b"*Node", b"*Node\r\n** upstream", 1))
    body = _upload(client, changed, "/api/workspaces/rd/reimport/preview").json()
    conflict = body["needs_attention"][0]
    assert conflict["filename"] == "mesh.inp"
    diff = conflict["diff"]
    yours = [t for row in diff["rows"] for _, t in row["left"]]
    incoming = [t for row in diff["rows"] for _, t in row["right"]]
    assert "** mine" in yours and "** mine" not in incoming
    assert "** upstream" in incoming and "** upstream" not in yours
    assert diff["added"] >= 1 and diff["removed"] >= 1
    assert body["mother"] == {"filename": "Job-1.inp", "changed": False}   # the change is inside mesh.inp


def test_reimport_diff_is_capped_for_huge_files():
    from filefold.service import side_by_side_diff
    a = "\n".join(f"line {i}" for i in range(5000))
    b = "\n".join(f"line {i}" if i % 2 else f"changed {i}" for i in range(5000))
    d = side_by_side_diff(a, b, max_rows=50)
    assert d["truncated"] and sum(len(r["left"]) + len(r["right"]) for r in d["rows"]) <= 120
    big = side_by_side_diff("x\n" * 2_000_000, "y\n" * 2_000_000)
    assert big["too_large"] and big["rows"] == []
