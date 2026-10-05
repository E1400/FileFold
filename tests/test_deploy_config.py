"""The server deployment path (Docker image, Railway config) must stay ready to use.

The dev phase is served as a static site from GitHub Pages, but the FastAPI server,
Dockerfile and railway.toml are the production path and are checked here on every run so
they cannot rot while nobody is deploying them.
"""
import re
import subprocess
import sys
import tomllib
from pathlib import Path

from fastapi.testclient import TestClient
from typer.main import get_command

ROOT = Path(__file__).resolve().parent.parent
DOCKERFILE = (ROOT / "Dockerfile").read_text()


def test_railway_healthcheck_path_is_served():
    cfg = tomllib.loads((ROOT / "railway.toml").read_text())
    from filefold.api.main import app
    r = TestClient(app).get(cfg["deploy"]["healthcheckPath"])
    assert r.status_code == 200 and "FileFold" in r.text
    assert (ROOT / cfg["build"]["dockerfilePath"]).is_file()


def test_dockerfile_does_not_resync_dev_dependencies_at_start():
    cmd = DOCKERFILE.strip().splitlines()[-1]
    assert cmd.startswith("CMD") and "uv run" not in cmd and "filefold serve" in cmd
    assert "--no-dev" in DOCKERFILE and "--frozen" in DOCKERFILE


def test_dockerfile_copies_what_the_app_needs():
    assert re.search(r"COPY src/ \./src/", DOCKERFILE)
    ignore = (ROOT / ".dockerignore").read_text().splitlines()
    assert "src/" not in ignore and "src" not in ignore
    assert "FILEFOLD_WORKSPACE_DIR=/data/workspaces" in DOCKERFILE


def test_serve_command_honours_port_and_host_env_vars():
    serve = get_command(__import__("filefold.cli.main", fromlist=["app"]).app).commands["serve"]
    envvars = {p.name: p.envvar for p in serve.params}
    assert envvars["port"] == "PORT" and envvars["host"] == "FILEFOLD_HOST"


def test_workspace_dir_comes_from_the_environment(tmp_path):
    code = "from filefold.api import server; print(server.WORKSPACE_BASE)"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                         env={"FILEFOLD_WORKSPACE_DIR": str(tmp_path / "vol"), "PATH": ""})
    assert out.stdout.strip() == str(tmp_path / "vol"), out.stderr


def test_lockfile_matches_pyproject():
    """uv.lock must list every dependency pyproject declares, or `uv sync --frozen` breaks the image."""
    lock = (ROOT / "uv.lock").read_text()
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    for dep in project["dependencies"]:
        name = re.split(r"[<>=\[ ]", dep, maxsplit=1)[0]
        assert f'name = "{name}"' in lock, f"{name} missing from uv.lock; run `uv lock`"
