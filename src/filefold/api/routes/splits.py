"""Edit an existing workspace's splits: extract, re-split, rename, recombine."""
from __future__ import annotations

from fastapi import APIRouter, Request

from filefold import service

router = APIRouter()


@router.post("/api/workspaces/{name}/extract")
async def extract_splits(name: str, request: Request):
    """Extract new splits from the existing mother file without re-uploading it."""
    body = await request.json()
    return service.extract_splits(name, body.get("selections", []))


@router.post("/api/workspaces/{name}/resplit-child")
async def resplit_child(name: str, request: Request):
    """Modify sub-splits for an already-extracted category (recombine then re-extract)."""
    body = await request.json()
    return service.resplit_child(name, body.get("category", ""), body.get("sub_selections", []))


@router.post("/api/workspaces/{name}/rename-file")
async def rename_file(name: str, request: Request):
    """Rename a child or grandchild file without re-extracting it."""
    body = await request.json()
    return service.rename_file(name, body.get("old_filename", ""), body.get("new_filename", ""))


@router.post("/api/workspaces/{name}/recombine")
async def recombine_files(name: str, request: Request):
    """Fold listed child/sub-child files back into their parent (reverse of split)."""
    body = await request.json()
    return service.recombine(name, body.get("filenames", []))
