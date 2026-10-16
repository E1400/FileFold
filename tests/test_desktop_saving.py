"""Desktop saving (export folder per workspace), without a window: the dialog is a stub."""
import zipfile
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from filefold import service
from filefold.api.main import _service_error_handler, _unsafe_name_handler
from filefold.api.server import UnsafeName
from filefold.desktop.saving import SaveDirs, make_router

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture()
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr("filefold.api.server.WORKSPACE_BASE", tmp_path / "ws")
    service.create_workspace("Job-1", "Job-1.inp", (FIXTURES / "Job-1.inp").read_bytes(),
                             [{"category": "mesh", "filename": "mesh.inp"}])
    asked = []
    answers = []

    def choose(name, start):
        asked.append((name, start))
        return answers.pop(0) if answers else None

    app = FastAPI()
    app.add_exception_handler(service.ServiceError, _service_error_handler)
    app.add_exception_handler(UnsafeName, _unsafe_name_handler)
    app.include_router(make_router(choose, SaveDirs(tmp_path / "data" / "save_dirs.json")))
    return TestClient(app), asked, answers, tmp_path


def test_first_export_asks_for_a_folder_then_remembers_it(setup):
    client, asked, answers, tmp = setup
    out = tmp / "exports"; out.mkdir()
    answers.append(out)
    r = client.post("/api/desktop/workspaces/Job-1/save", json={}).json()
    assert r["saved"] == str(out / "Job-1.zip") and len(asked) == 1
    assert "mesh.inp" in zipfile.ZipFile(out / "Job-1.zip").namelist()
    # A single file goes to the same folder, without asking again.
    r = client.post("/api/desktop/workspaces/Job-1/save", json={"filename": "mesh.inp"}).json()
    assert r["saved"] == str(out / "mesh.inp") and len(asked) == 1
    assert (out / "mesh.inp").read_bytes() == service.read_file("Job-1", "mesh.inp")
    assert client.get("/api/desktop/workspaces/Job-1/save-dir").json() == {"dir": str(out)}


def test_cancelling_the_dialog_saves_nothing(setup):
    client, asked, answers, tmp = setup
    r = client.post("/api/desktop/workspaces/Job-1/save", json={}).json()
    assert r == {"saved": None, "canceled": True}
    assert client.get("/api/desktop/workspaces/Job-1/save-dir").json() == {"dir": None}


def test_an_existing_file_is_only_replaced_when_asked_to(setup):
    client, asked, answers, tmp = setup
    out = tmp / "project"; out.mkdir()
    (out / "Job-1.inp").write_text("the original deck")
    answers.append(out)
    r = client.post("/api/desktop/workspaces/Job-1/save", json={"filename": "Job-1.inp"}).json()
    assert r["exists"] and r["saved"] is None
    assert (out / "Job-1.inp").read_text() == "the original deck"
    r = client.post("/api/desktop/workspaces/Job-1/save", json={"filename": "Job-1.inp", "replace": True}).json()
    assert r["saved"] == str(out / "Job-1.inp")
    assert (out / "Job-1.inp").read_bytes() == service.read_file("Job-1", "Job-1.inp")


def test_change_folder_starts_from_the_current_one(setup):
    client, asked, answers, tmp = setup
    a, b = tmp / "a", tmp / "b"; a.mkdir(); b.mkdir()
    answers += [a, b]
    assert client.post("/api/desktop/workspaces/Job-1/save-dir").json() == {"dir": str(a)}
    assert client.post("/api/desktop/workspaces/Job-1/save-dir").json() == {"dir": str(b)}
    assert asked[1] == ("Job-1", a)
    assert client.post("/api/desktop/workspaces/Job-1/save-dir").json() == {"dir": None, "canceled": True}
    assert client.get("/api/desktop/workspaces/Job-1/save-dir").json() == {"dir": str(b)}   # cancel keeps it


def test_unknown_workspace_or_file_never_opens_a_dialog(setup):
    client, asked, answers, tmp = setup
    assert client.post("/api/desktop/workspaces/nope/save", json={}).status_code == 404
    assert client.post("/api/desktop/workspaces/Job-1/save", json={"filename": "nope.inp"}).status_code == 404
    assert client.post("/api/desktop/workspaces/nope/save-dir").status_code == 404
    assert client.post("/api/desktop/workspaces/Job-1/save", json={"filename": "../x"}).status_code == 400
    assert asked == []


def test_a_folder_that_was_deleted_is_asked_for_again(setup):
    client, asked, answers, tmp = setup
    gone = tmp / "gone"; gone.mkdir()
    answers.append(gone)
    client.post("/api/desktop/workspaces/Job-1/save-dir")
    gone.rmdir()
    assert client.get("/api/desktop/workspaces/Job-1/save-dir").json() == {"dir": None}


def test_the_hosted_server_never_has_these_routes():
    """Only the desktop app mounts them; on a server "a folder" would be the server's."""
    from filefold.api.main import app
    assert not [r for r in app.routes if getattr(r, "path", "").startswith("/api/desktop")]
