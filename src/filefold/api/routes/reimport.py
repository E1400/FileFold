"""Re-import an updated mother file into a workspace."""
from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, File, Form, UploadFile

from filefold import service

router = APIRouter()


@router.post("/api/workspaces/{name}/reimport/preview")
async def reimport_preview(name: str, file: UploadFile = File(...)):
    """Upload a new mother file and get a preview of what would change."""
    return service.reimport_preview(name, file.filename or "upload.inp", await file.read())


@router.post("/api/workspaces/{name}/reimport/apply")
async def reimport_apply(
    name: str,
    file: UploadFile = File(...),
    filenames: Annotated[str, Form()] = "",         # JSON list of existing child filenames to update
    added_selections: Annotated[str, Form()] = "",  # JSON: [{"category":"step","filename":"step.inp"}]
):
    """Apply a reimport: update approved children, add new selections, refresh mother."""
    return service.reimport_apply(
        name, file.filename or "upload.inp", await file.read(),
        json.loads(filenames) if filenames else [],
        json.loads(added_selections) if added_selections else [],
    )
