"""Optional shared-password gate (FILEFOLD_BASIC_AUTH=user:password) for a hosted server."""
import base64

from fastapi.testclient import TestClient

from filefold.api.main import app


def _auth(user, password):
    return {"Authorization": "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()}


def test_open_when_no_password_configured(monkeypatch):
    monkeypatch.delenv("FILEFOLD_BASIC_AUTH", raising=False)
    assert TestClient(app).get("/").status_code == 200


def test_everything_requires_the_password_when_configured(monkeypatch):
    monkeypatch.setenv("FILEFOLD_BASIC_AUTH", "lab:s3cret")
    c = TestClient(app)
    for path in ("/", "/api/workspaces", "/static/app.css", "/api/sub-options"):
        r = c.get(path)
        assert r.status_code == 401 and "Basic" in r.headers["www-authenticate"], path
    assert c.get("/api/workspaces", headers=_auth("lab", "wrong")).status_code == 401
    assert c.get("/api/workspaces", headers=_auth("other", "s3cret")).status_code == 401
    assert c.get("/api/workspaces", headers=_auth("lab", "s3cret")).status_code == 200
    assert c.get("/", headers=_auth("lab", "s3cret")).status_code == 200


def test_password_may_contain_a_colon(monkeypatch):
    monkeypatch.setenv("FILEFOLD_BASIC_AUTH", "lab:pa:ss")
    assert TestClient(app).get("/", headers=_auth("lab", "pa:ss")).status_code == 200
