"""Workspace CRUD and status."""
from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, File, Form, Request, UploadFile

from filefold import service

from ..uploads import staged_upload

router = APIRouter()


@router.get("/api/workspaces")
async def list_all_workspaces():
    return service.list_all_workspaces()


@router.post("/api/workspaces")
async def create_workspace(
    file: UploadFile = File(...),
    name: Annotated[str, Form()] = "",
    selections: Annotated[str, Form()] = "",  # JSON: [{"category":"mesh","filename":"mesh.inp"}]
):
    """Create a new workspace from an uploaded mother file."""
    sel_data = json.loads(selections) if selections else []
    async with staged_upload(file) as path:
        return service.create_workspace(name, file.filename or "upload.inp", path, sel_data)


@router.get("/api/workspaces/{name}")
async def get_workspace(name: str):
    """Return workspace status including per-file hash state."""
    return service.get_workspace(name)


@router.patch("/api/workspaces/{name}")
async def rename_workspace(name: str, request: Request):
    """Rename a workspace directory and update its manifest."""
    body = await request.json()
    return service.rename_workspace(name, body.get("name", ""))


@router.delete("/api/workspaces/{name}")
async def delete_workspace(name: str):
    return service.delete_workspace(name)
