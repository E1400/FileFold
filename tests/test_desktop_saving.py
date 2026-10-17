"""Desktop saving (a Save dialog every time, starting where the workspace was last saved),
without a window: the dialog is a stub."""
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
    asked, answers = [], []

    def ask(title, start):
        asked.append((title, start))
        return answers.pop(0) if answers else None

    downloads = tmp_path / "Downloads"; downloads.mkdir()
    app = FastAPI()
    app.add_exception_handler(service.ServiceError, _service_error_handler)
    app.add_exception_handler(UnsafeName, _unsafe_name_handler)
    app.include_router(make_router(ask, SaveDirs(tmp_path / "data" / "save_dirs.json"), lambda: downloads))
    return TestClient(app), asked, answers, tmp_path


def test_every_save_asks_starting_where_the_workspace_was_last_saved(setup):
    client, asked, answers, tmp = setup
    out = tmp / "exports"; out.mkdir()
    answers.append(out / "Job-1.zip")
    r = client.post("/api/desktop/workspaces/Job-1/save", json={}).json()
    assert r == {"saved": str(out / "Job-1.zip"), "dir": str(out)}
    assert asked[0] == ("Save Job-1.zip", tmp / "Downloads" / "Job-1.zip")      # first time: Downloads
    assert "mesh.inp" in zipfile.ZipFile(out / "Job-1.zip").namelist()
    answers.append(out / "mesh.inp")
    r = client.post("/api/desktop/workspaces/Job-1/save", json={"filename": "mesh.inp"}).json()
    assert asked[1] == ("Save mesh.inp", out / "mesh.inp")                      # then: where it went last
    assert (out / "mesh.inp").read_bytes() == service.read_file("Job-1", "mesh.inp")


def test_canceling_the_dialog_saves_nothing(setup):
    client, asked, answers, tmp = setup
    assert client.post("/api/desktop/workspaces/Job-1/save", json={}).json() == {"saved": None, "canceled": True}
    assert not list((tmp / "Downloads").iterdir())


def test_unknown_workspace_or_file_never_opens_a_dialog(setup):
    client, asked, answers, tmp = setup
    assert client.post("/api/desktop/workspaces/nope/save", json={}).status_code == 404
    assert client.post("/api/desktop/workspaces/Job-1/save", json={"filename": "nope.inp"}).status_code == 404
    assert client.post("/api/desktop/workspaces/Job-1/save", json={"filename": "../x"}).status_code == 400
    assert asked == []


def test_a_folder_that_was_deleted_falls_back_to_downloads(setup):
    client, asked, answers, tmp = setup
    gone = tmp / "gone"; gone.mkdir()
    answers.append(gone / "Job-1.zip")
    client.post("/api/desktop/workspaces/Job-1/save", json={})
    (gone / "Job-1.zip").unlink(); gone.rmdir()
    client.post("/api/desktop/workspaces/Job-1/save", json={})
    assert asked[1] == ("Save Job-1.zip", tmp / "Downloads" / "Job-1.zip")


def test_the_hosted_server_never_has_these_routes():
    """Only the desktop app mounts them; on a server "a folder" would be the server's."""
    from filefold.api.main import app
    assert not [r for r in app.routes if getattr(r, "path", "").startswith("/api/desktop")]
