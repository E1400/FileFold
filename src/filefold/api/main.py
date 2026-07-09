"""FastAPI application — REST API + static web frontend."""
from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse

from filefold.core.keywords import Category
from filefold.core.parser import parse
from filefold.core.splitter import SplitSelection
from filefold.core.workspace import Workspace

from .server import WORKSPACE_BASE, list_workspaces, workspace_path

app = FastAPI(title="FileFold", version="0.1.0")

# Serve the web frontend
_WEB_DIR = Path(__file__).parent.parent / "web"


@app.get("/", response_class=HTMLResponse)
async def index():
    return (_WEB_DIR / "index.html").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Inspect
# ---------------------------------------------------------------------------

@app.post("/api/inspect")
async def inspect_file(file: UploadFile = File(...)):
    """Parse an uploaded .inp file and return its block tree."""
    import tempfile, os
    suffix = Path(file.filename or "upload.inp").suffix
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(await file.read())
        tmp_path = Path(tmp.name)

    try:
        blocks = parse(tmp_path)
        return {"filename": file.filename, "blocks": _blocks_to_json(blocks)}
    finally:
        tmp_path.unlink(missing_ok=True)


def _blocks_to_json(blocks) -> list[dict]:
    return [
        {
            "keyword": b.keyword,
            "category": b.category.value,
            "line_start": b.line_start,
            "line_end": b.line_end,
            "params": b.params,
            "children": _blocks_to_json(b.children),
        }
        for b in blocks
    ]


# ---------------------------------------------------------------------------
# Workspace CRUD
# ---------------------------------------------------------------------------

@app.get("/api/workspaces")
async def list_all_workspaces():
    return {"workspaces": list_workspaces()}


@app.post("/api/workspaces")
async def create_workspace(
    file: UploadFile = File(...),
    name: Annotated[str, Form()] = "",
    selections: Annotated[str, Form()] = "",  # JSON: [{"category":"mesh","filename":"mesh.inp"}]
):
    """Create a new workspace from an uploaded mother file."""
    import json, shutil, tempfile

    ws_name = name.strip() or Path(file.filename or "model").stem
    ws_dir = workspace_path(ws_name)
    if ws_dir.exists():
        raise HTTPException(400, f"Workspace '{ws_name}' already exists")

    sel_data = json.loads(selections) if selections else []
    sel_list = [
        SplitSelection(Category(s["category"]), s["filename"])
        for s in sel_data
    ]

    # Write to a temp dir using the original filename so Workspace.create
    # records the right source_name in the manifest from the start.
    original_name = file.filename or "upload.inp"
    tmpdir = Path(tempfile.mkdtemp())
    tmp_path = tmpdir / original_name

    try:
        tmp_path.write_bytes(await file.read())
        ws = Workspace.create(ws_dir, tmp_path, sel_list)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    return {"workspace": ws_name, "files": list(ws.file_records.keys())}


@app.get("/api/workspaces/{name}")
async def get_workspace(name: str):
    """Return workspace status including per-file hash state."""
    ws_dir = workspace_path(name)
    try:
        ws = Workspace.load(ws_dir)
    except FileNotFoundError:
        raise HTTPException(404, f"Workspace '{name}' not found")

    files = []
    for fname, rec in ws.file_records.items():
        fpath = ws_dir / fname
        if fpath.exists():
            from filefold.core.splitter import _sha256
            current = _sha256(fpath.read_text(encoding="utf-8", errors="surrogateescape"))
            edited = (bool(rec.sha256) and current != rec.sha256)
        else:
            edited = False
        files.append({
            "filename": fname,
            "role": rec.role,
            "category": rec.category,
            "manually_edited": edited,
            "exists": fpath.exists(),
        })

    return {
        "name": ws.name,
        "source_name": ws.source_name,
        "selections": [{"category": s.category.value, "filename": s.filename} for s in ws.selections],
        "updated_at": ws.updated_at,
        "files": files,
    }


@app.delete("/api/workspaces/{name}")
async def delete_workspace(name: str):
    import shutil
    ws_dir = workspace_path(name)
    if not ws_dir.exists():
        raise HTTPException(404, f"Workspace '{name}' not found")
    shutil.rmtree(ws_dir)
    return {"deleted": name}


# ---------------------------------------------------------------------------
# Reimport
# ---------------------------------------------------------------------------

@app.post("/api/workspaces/{name}/reimport/preview")
async def reimport_preview(name: str, file: UploadFile = File(...)):
    """Upload a new mother file and get a preview of what would change."""
    import shutil, tempfile
    ws_dir = workspace_path(name)
    try:
        ws = Workspace.load(ws_dir)
    except FileNotFoundError:
        raise HTTPException(404, f"Workspace '{name}' not found")

    original_name = file.filename or "upload.inp"
    tmpdir = Path(tempfile.mkdtemp())
    tmp_path = tmpdir / original_name

    try:
        tmp_path.write_bytes(await file.read())
        blocks = parse(tmp_path)
        preview = ws.reimport_preview(tmp_path)
        return {
            "filename": original_name,
            "blocks": _blocks_to_json(blocks),
            "safe_to_update": [_status_json(s) for s in preview.safe_to_update],
            "needs_attention": [_status_json(s) for s in preview.needs_attention],
            "unchanged": [_status_json(s) for s in preview.unchanged],
        }
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _status_json(s) -> dict:
    return {
        "filename": s.filename,
        "category": s.category.value,
        "changed_in_new_mother": s.changed_in_new_mother,
        "manually_edited": s.manually_edited,
    }


@app.post("/api/workspaces/{name}/reimport/apply")
async def reimport_apply(
    name: str,
    file: UploadFile = File(...),
    filenames: Annotated[str, Form()] = "",         # JSON list of existing child filenames to update
    added_selections: Annotated[str, Form()] = "",  # JSON: [{"category":"step","filename":"step.inp"}]
):
    """Apply a reimport: update approved children, add new selections, refresh mother."""
    import json, shutil, tempfile
    ws_dir = workspace_path(name)
    try:
        ws = Workspace.load(ws_dir)
    except FileNotFoundError:
        raise HTTPException(404, f"Workspace '{name}' not found")

    to_update: set[str] = set(json.loads(filenames)) if filenames else set()
    added: list[SplitSelection] | None = None
    if added_selections:
        added = [
            SplitSelection(Category(s["category"]), s["filename"])
            for s in json.loads(added_selections)
        ]

    original_name = file.filename or "upload.inp"
    tmpdir = Path(tempfile.mkdtemp())
    tmp_path = tmpdir / original_name

    try:
        tmp_path.write_bytes(await file.read())
        preview = ws.reimport_preview(tmp_path)
        ws.reimport_apply(tmp_path, preview, to_update, added_selections=added)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    return {"updated": list(to_update), "workspace": ws.name}


# ---------------------------------------------------------------------------
# Export workspace as zip
# ---------------------------------------------------------------------------

@app.get("/api/workspaces/{name}/export")
async def export_workspace(name: str):
    """Download all workspace files as a zip."""
    ws_dir = workspace_path(name)
    if not ws_dir.exists():
        raise HTTPException(404, f"Workspace '{name}' not found")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in ws_dir.iterdir():
            if f.is_file() and not f.name.startswith("."):
                zf.write(f, f.name)
    buf.seek(0)

    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{name}.zip"'},
    )


# ---------------------------------------------------------------------------
# Get / save individual file content
# ---------------------------------------------------------------------------

@app.get("/api/workspaces/{name}/files/{filename}")
async def get_file(name: str, filename: str):
    """Return the raw content of a workspace file (served inline as text/plain)."""
    fpath = workspace_path(name) / filename
    if not fpath.exists():
        raise HTTPException(404, f"File '{filename}' not found in workspace '{name}'")
    return FileResponse(fpath, media_type="text/plain")


@app.put("/api/workspaces/{name}/files/{filename}")
async def save_file(name: str, filename: str, request: Request):
    """Overwrite a workspace file with edited content sent as plain-text body."""
    fpath = workspace_path(name) / filename
    if not fpath.exists():
        raise HTTPException(404, f"File '{filename}' not found in workspace '{name}'")
    content = (await request.body()).decode("utf-8", errors="surrogateescape")
    fpath.write_text(content, encoding="utf-8", errors="surrogateescape")
    return {"saved": filename, "bytes": len(content)}
