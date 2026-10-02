"""The in-browser dispatcher must expose exactly the FastAPI API, and behave identically."""
import io
import json
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from filefold import browser
from filefold.api.main import app

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture()
def clients(tmp_path, monkeypatch):
    monkeypatch.setattr("filefold.api.server.WORKSPACE_BASE", tmp_path)
    return TestClient(app)


def test_route_table_matches_fastapi_routes():
    # The OpenAPI schema lists every route regardless of how routers are nested.
    fastapi_routes = {
        (method.upper(), path)
        for path, ops in app.openapi()["paths"].items() if path.startswith("/api")
        for method in ops
    }
    assert fastapi_routes, "found no /api routes in the OpenAPI schema"
    assert browser.route_signatures() == fastapi_routes


def _strip_times(value):
    """Drop timestamps (they differ by microseconds between two separate runs)."""
    if isinstance(value, dict):
        return {k: _strip_times(v) for k, v in value.items() if k != "updated_at"}
    if isinstance(value, list):
        return [_strip_times(v) for v in value]
    return value


def _both(client, method, path, **kw):
    """Same request through FastAPI and through the dispatcher; return both results."""
    http = client.request(method, path, **kw.get("http", {}))
    status, ctype, headers, body = browser.handle(method, path, **kw.get("browser", {}))
    return http, (status, ctype, headers, body)


def test_unknown_route_and_wrong_method(clients):
    assert browser.handle("GET", "/api/nope")[0] == 404
    assert browser.handle("DELETE", "/api/inspect")[0] == 405


def test_full_lifecycle_gives_identical_json_through_both_front_ends(tmp_path, monkeypatch, clients):
    name = "mmxmn.inp"
    data = (FIXTURES / name).read_bytes()
    sels = [{"category": "contact", "filename": "contact.inp",
             "sub_selections": [{"sub_category": "pairs", "filename": "contact-pairs.inp"}]}]

    # inspect: stateless, so compare directly
    http = clients.post("/api/inspect", files={"file": (name, io.BytesIO(data))})
    st, ct, _, body = browser.handle("POST", "/api/inspect", file_name=name, file_bytes=data)
    assert st == 200 and json.loads(body) == http.json()

    # create the same workspace once per front end, in separate directories
    http_dir, br_dir = tmp_path / "http", tmp_path / "browser"
    http_dir.mkdir(); br_dir.mkdir()
    monkeypatch.setattr("filefold.api.server.WORKSPACE_BASE", http_dir)
    r = clients.post("/api/workspaces", files={"file": (name, io.BytesIO(data))},
                     data={"name": "w", "selections": json.dumps(sels)})
    monkeypatch.setattr("filefold.api.server.WORKSPACE_BASE", br_dir)
    st, _, _, body = browser.handle("POST", "/api/workspaces", fields={"name": "w", "selections": json.dumps(sels)},
                                    file_name=name, file_bytes=data)
    assert st == 200 and r.status_code == 200
    assert json.loads(body) == r.json()

    def through_http(method, path, **kw):
        monkeypatch.setattr("filefold.api.server.WORKSPACE_BASE", http_dir)
        return clients.request(method, path, **kw)

    def through_browser(method, path, **kw):
        monkeypatch.setattr("filefold.api.server.WORKSPACE_BASE", br_dir)
        return browser.handle(method, path, **kw)

    def same_json(method, path, http_kw=None, br_kw=None):
        h = through_http(method, path, **(http_kw or {}))
        s, _, _, b = through_browser(method, path, **(br_kw or {}))
        assert s == h.status_code, (path, s, h.status_code, b[:200])
        got, want = json.loads(b), h.json()
        assert _strip_times(got) == _strip_times(want), path

    same_json("GET", "/api/workspaces/w")
    same_json("GET", "/api/workspaces")
    same_json("POST", "/api/workspaces/w/extract",
              {"json": {"selections": [{"category": "loads", "filename": "loads.inp"}]}},
              {"json_body": {"selections": [{"category": "loads", "filename": "loads.inp"}]}})
    same_json("GET", "/api/workspaces/w")
    same_json("POST", "/api/workspaces/w/rename-file",
              {"json": {"old_filename": "loads.inp", "new_filename": "bcs.inp"}},
              {"json_body": {"old_filename": "loads.inp", "new_filename": "bcs.inp"}})
    same_json("POST", "/api/workspaces/w/recombine",
              {"json": {"filenames": ["bcs.inp"]}}, {"json_body": {"filenames": ["bcs.inp"]}})
    same_json("GET", "/api/workspaces/w")

    # errors map to the same status and message
    same_json("GET", "/api/workspaces/missing")
    same_json("POST", "/api/workspaces/w/recombine",
              {"json": {"filenames": ["nope.inp"]}}, {"json_body": {"filenames": ["nope.inp"]}})

    # file bytes and zip export
    h = through_http("GET", "/api/workspaces/w/files/contact-pairs.inp")
    s, ct, _, b = through_browser("GET", "/api/workspaces/w/files/contact-pairs.inp")
    assert s == 200 and ct == "text/plain" and b == h.content
    s, ct, hdr, b = through_browser("GET", "/api/workspaces/w/export")
    assert ct == "application/zip" and "w.zip" in hdr["Content-Disposition"]
    assert sorted(zipfile.ZipFile(io.BytesIO(b)).namelist()) == sorted(
        zipfile.ZipFile(io.BytesIO(through_http("GET", "/api/workspaces/w/export").content)).namelist())

    # editing a file and re-reading it, CRLF preserved
    s, _, _, b = through_browser("PUT", "/api/workspaces/w/files/contact.inp", body=b"a\r\nb\r\n")
    assert s == 200 and through_browser("GET", "/api/workspaces/w/files/contact.inp")[3] == b"a\r\nb\r\n"


def test_path_segments_are_url_decoded_and_traversal_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr("filefold.api.server.WORKSPACE_BASE", tmp_path)
    data = (FIXTURES / "test_2.inp").read_bytes()
    st, *_ = browser.handle("POST", "/api/workspaces", fields={"name": "my model"}, file_name="a.inp", file_bytes=data)
    assert st == 200
    assert browser.handle("GET", "/api/workspaces/my%20model")[0] == 200
    st, _, _, body = browser.handle("POST", "/api/workspaces", fields={"name": "../evil"}, file_name="a.inp", file_bytes=data)
    assert st == 400
