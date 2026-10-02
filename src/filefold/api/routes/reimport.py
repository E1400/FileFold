"""Re-import an updated mother file into a workspace."""
from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from filefold.core.parser import parse
from filefold.core.splitter import SplitSelection
from filefold.core.workspace import Workspace

from ..common import parse_category, reject_non_extractable, validate_selection_filenames
from ..server import workspace_path
from .inspect import _blocks_to_json

router = APIRouter()


@router.post("/api/workspaces/{name}/reimport/preview")
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


@router.post("/api/workspaces/{name}/reimport/apply")
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
        added_data = json.loads(added_selections)
        reject_non_extractable(added_data)
        validate_selection_filenames(added_data)
        added = [
            SplitSelection(parse_category(s["category"]), s["filename"])
            for s in added_data
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
