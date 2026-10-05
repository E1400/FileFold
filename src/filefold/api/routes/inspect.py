"""Stateless inspection: parse an uploaded deck, list sub-split options."""
from __future__ import annotations

from fastapi import APIRouter, File, UploadFile

from filefold import service

from ..uploads import staged_upload

router = APIRouter()


@router.post("/api/inspect")
async def inspect_file(file: UploadFile = File(...)):
    """Parse an uploaded .inp file and return its block tree."""
    async with staged_upload(file) as path:
        return service.inspect(file.filename or "upload.inp", path)


@router.get("/api/sub-options")
async def get_sub_options():
    """Return the fixed sub-split options per category."""
    return service.static_sub_options()
