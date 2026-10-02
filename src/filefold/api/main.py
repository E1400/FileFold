"""FastAPI application — REST API + static web frontend.

Routes live in api/routes/, one module per topic; shared helpers in api/common.py.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .common import NON_EXTRACTABLE  # noqa: F401  (re-exported; tests and the UI mirror it)
from .routes import files, inspect, reimport, splits, workspaces
from .server import UnsafeName

app = FastAPI(title="FileFold", version="0.1.0")


@app.exception_handler(UnsafeName)
async def _unsafe_name_handler(request: Request, exc: UnsafeName) -> JSONResponse:
    """A rejected name is a client error, not a crash."""
    return JSONResponse(status_code=400, content={"detail": str(exc)})


# Serve the web frontend: one HTML page plus CSS/JS under /static
_WEB_DIR = Path(__file__).parent.parent / "web"
app.mount("/static", StaticFiles(directory=_WEB_DIR / "static"), name="static")


@app.get("/", response_class=HTMLResponse)
async def index():
    return (_WEB_DIR / "index.html").read_text(encoding="utf-8")


for _module in (inspect, workspaces, splits, reimport, files):
    app.include_router(_module.router)
