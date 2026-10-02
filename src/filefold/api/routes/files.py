"""Download/export a workspace and read/write individual files."""
from __future__ import annotations

import io

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, StreamingResponse

from filefold import service

router = APIRouter()


@router.get("/api/workspaces/{name}/export")
async def export_workspace(name: str):
    """Download all workspace files as a zip."""
    return StreamingResponse(
        io.BytesIO(service.export_zip(name)),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{name}.zip"'},
    )


@router.get("/api/workspaces/{name}/files/{filename}")
async def get_file(name: str, filename: str):
    """Return the raw content of a workspace file (served inline as text/plain)."""
    # Streamed from disk: a mesh deck can be large. file_path validates the segment.
    return FileResponse(service.file_path(name, filename), media_type="text/plain")


@router.put("/api/workspaces/{name}/files/{filename}")
async def save_file(name: str, filename: str, request: Request):
    """Overwrite a workspace file with edited content sent as plain-text body."""
    return service.write_file(name, filename, await request.body())
