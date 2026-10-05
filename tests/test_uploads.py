"""Upload handling: safe filenames, streaming to disk, optional size cap."""
import io
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from filefold import service
from filefold.api.main import app

FIXTURES = Path(__file__).parent / "fixtures"
DECK = (FIXTURES / "test_2.inp").read_bytes()


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    """Temp dirs are created inside tmp_path/sandbox/t, so an escape is observable."""
    root = tmp_path / "sandbox"
    (root / "t").mkdir(parents=True)
    monkeypatch.setattr("tempfile.tempdir", str(root / "t"))
    monkeypatch.setattr("filefold.api.server.WORKSPACE_BASE", tmp_path / "ws")
    return root


@pytest.mark.parametrize("evil", ["../../escape.inp", "..", "a/b/c.inp", "..\\..\\escape.inp"])
def test_service_never_writes_outside_its_temp_dir(sandbox, evil):
    service.inspect(evil, DECK)
    created = {p.relative_to(sandbox) for p in sandbox.rglob("*") if p.is_file()}
    assert created == set(), created  # the temp dir is cleaned up and nothing escaped


@pytest.mark.parametrize("evil", ["../../escape.inp", "a/b/c.inp"])
def test_api_upload_with_path_in_filename_is_contained(sandbox, evil):
    c = TestClient(app)
    r = c.post("/api/workspaces", files={"file": (evil, io.BytesIO(DECK))}, data={"name": "w"})
    assert r.status_code == 200, r.text
    assert not (sandbox / "escape.inp").exists()
    detail = c.get("/api/workspaces/w").json()
    assert detail["source_name"] == Path(evil.replace("\\", "/")).name   # only the leaf name survives


def test_server_streams_uploads_to_disk_instead_of_holding_them_in_memory(sandbox, monkeypatch):
    """The server passes a Path to the service, not bytes (a 500 MB deck would otherwise
    be copied two or three times in memory)."""
    seen = []
    real = service.inspect

    def spy(filename, data):
        seen.append(type(data))
        return real(filename, data)

    monkeypatch.setattr("filefold.api.routes.inspect.service.inspect", spy)
    r = TestClient(app).post("/api/inspect", files={"file": ("t.inp", io.BytesIO(DECK))})
    assert r.status_code == 200 and seen and issubclass(seen[0], Path)


def test_optional_upload_size_cap(sandbox, monkeypatch):
    monkeypatch.setenv("FILEFOLD_MAX_UPLOAD_MB", "1")
    c = TestClient(app)
    big = b"*HEADING\n" + b"x" * (2 * 1024 * 1024)
    r = c.post("/api/inspect", files={"file": ("big.inp", io.BytesIO(big))})
    assert r.status_code == 413 and "1 MB" in r.json()["detail"]
    assert c.post("/api/inspect", files={"file": ("ok.inp", io.BytesIO(DECK))}).status_code == 200
    assert not [p for p in sandbox.rglob("*") if p.is_file()]   # the rejected upload was cleaned up
