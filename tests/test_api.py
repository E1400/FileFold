"""API endpoint tests using FastAPI TestClient."""
import io
import json
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
    monkeypatch.setattr("filefold.api.main.WORKSPACE_BASE", tmp_path)
    monkeypatch.setattr("filefold.api.server.WORKSPACE_BASE", tmp_path)
    # Also patch the workspace_path helper used inside the app
    import filefold.api.main as m
    monkeypatch.setattr(m, "workspace_path", lambda name: tmp_path / name)
    monkeypatch.setattr(
        m, "list_workspaces",
        lambda: sorted(
            p.name for p in tmp_path.iterdir()
            if p.is_dir() and (p / ".filefold" / "workspace.json").exists()
        ) if tmp_path.exists() else [],
    )


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
