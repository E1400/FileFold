"""Download/export a workspace and read/write individual files."""
from __future__ import annotations

import io
import zipfile

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse

from ..server import child_path, workspace_path

router = APIRouter()


@router.get("/api/workspaces/{name}/export")
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

@router.get("/api/workspaces/{name}/files/{filename}")
async def get_file(name: str, filename: str):
    """Return the raw content of a workspace file (served inline as text/plain)."""
    # Starlette's router already refuses encoded slashes in a path param, but this
    # join must not depend on that: validate the segment here too.
    fpath = child_path(workspace_path(name), filename)
    if not fpath.exists():
        raise HTTPException(404, f"File '{filename}' not found in workspace '{name}'")
    return FileResponse(fpath, media_type="text/plain")


@router.put("/api/workspaces/{name}/files/{filename}")
async def save_file(name: str, filename: str, request: Request):
    """Overwrite a workspace file with edited content sent as plain-text body."""
    fpath = child_path(workspace_path(name), filename)
    if not fpath.exists():
        raise HTTPException(404, f"File '{filename}' not found in workspace '{name}'")
    content = (await request.body()).decode("utf-8", errors="surrogateescape")
    # newline="" so the editor round-trips a CRLF deck byte-for-byte instead of
    # rewriting its line endings on every save.
    with open(fpath, "w", encoding="utf-8", errors="surrogateescape", newline="") as fh:
        fh.write(content)
    return {"saved": filename, "bytes": len(content)}
