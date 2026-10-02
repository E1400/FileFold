"""Edit an existing workspace's splits: extract, re-split, rename, recombine."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from filefold.core.parser import parse
from filefold.core.splitter import SubSplitSelection, split_with_includes
from filefold.core.workspace import Workspace

from ..common import reject_non_extractable, selections_from_payload, validate_selection_filenames
from ..server import safe_segment, workspace_path

router = APIRouter()


@router.post("/api/workspaces/{name}/extract")
async def extract_splits(name: str, request: Request):
    """Extract new splits from the existing mother file without re-uploading it."""
    body = await request.json()
    sel_data = body.get("selections", [])
    if not sel_data:
        raise HTTPException(400, "selections is required")
    reject_non_extractable(sel_data)
    ws_dir = workspace_path(name)
    try:
        ws = Workspace.load(ws_dir)
    except FileNotFoundError:
        raise HTTPException(404, f"Workspace '{name}' not found")
    mother_path = ws_dir / ws.source_name
    if not mother_path.exists():
        raise HTTPException(404, f"Mother file '{ws.source_name}' not found")
    validate_selection_filenames(sel_data)
    new_sels = selections_from_payload(sel_data)
    blocks = parse(mother_path)
    result = split_with_includes(blocks, mother_path, ws_dir, new_sels)
    # Only add a selection to the manifest when blocks were actually written for it.
    # If the category was already extracted (mother has *INCLUDE), compute_split finds
    # no blocks and writes nothing — adding it again would create a stale duplicate entry.
    extracted_files = {child.filename for child in result.children}
    ws.selections.extend(s for s in new_sels if s.filename in extracted_files)
    ws._record_result(result)
    ws._save()
    return {"extracted": sorted(extracted_files), "workspace": name}


@router.post("/api/workspaces/{name}/resplit-child")
async def resplit_child(name: str, request: Request):
    """Modify sub-splits for an already-extracted category (recombine then re-extract)."""
    body = await request.json()
    category_str = body.get("category", "").strip()
    sub_sel_data = body.get("sub_selections", [])
    if not category_str:
        raise HTTPException(400, "category is required")
    ws_dir = workspace_path(name)
    try:
        ws = Workspace.load(ws_dir)
    except FileNotFoundError:
        raise HTTPException(404, f"Workspace '{name}' not found")
    # A sub-split writes straight to its filename. Without this check, naming a
    # sub-split after an existing child ("material.inp") silently overwrites that
    # child with mesh data.
    reserved = {ws.source_name} | {
        s.filename for s in ws.selections if s.category.value != category_str
    }
    seen: set[str] = set()
    for ss in sub_sel_data:
        fn = safe_segment(ss.get("filename", ""), "filename")
        if fn in reserved:
            raise HTTPException(400, f"'{fn}' is already used by another file in this workspace")
        if fn in seen:
            raise HTTPException(400, f"Duplicate sub-split filename: '{fn}'")
        seen.add(fn)

    new_sub = [SubSplitSelection(ss["sub_category"], ss["filename"]) for ss in sub_sel_data]
    try:
        ws.resplit_child(category_str, new_sub)
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(400, str(e))
    return {"category": category_str, "sub_extracted": [ss["filename"] for ss in sub_sel_data], "workspace": name}


@router.post("/api/workspaces/{name}/rename-file")
async def rename_file(name: str, request: Request):
    """Rename a child or grandchild file without re-extracting it."""
    body = await request.json()
    old_filename = safe_segment(body.get("old_filename", ""), "old_filename")
    new_filename = safe_segment(body.get("new_filename", ""), "new_filename")
    if old_filename == new_filename:
        return {"renamed": old_filename, "workspace": name}
    ws_dir = workspace_path(name)
    try:
        ws = Workspace.load(ws_dir)
    except FileNotFoundError:
        raise HTTPException(404, f"Workspace '{name}' not found")
    try:
        ws.rename_child(old_filename, new_filename)
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(400, str(e))
    return {"renamed": new_filename, "workspace": name}


@router.post("/api/workspaces/{name}/recombine")
async def recombine_files(name: str, request: Request):
    """Fold listed child/sub-child files back into their parent (reverse of split)."""
    body = await request.json()
    filenames = body.get("filenames", [])
    if not filenames:
        raise HTTPException(400, "filenames is required")
    filenames = [safe_segment(f, "filename") for f in filenames]
    ws_dir = workspace_path(name)
    try:
        ws = Workspace.load(ws_dir)
    except FileNotFoundError:
        raise HTTPException(404, f"Workspace '{name}' not found")

    # recombine() ignores names it doesn't recognise, so a typo or a stale UI would
    # report success while folding nothing back. Fail loudly instead.
    known = {s.filename for s in ws.selections} | {
        ss.filename for s in ws.selections for ss in s.sub_selections
    }
    unknown = [f for f in filenames if f not in known]
    if unknown:
        raise HTTPException(400, f"Not an extracted file in this workspace: {unknown[0]!r}")

    try:
        ws.recombine(filenames)
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(400, str(e))
    return {"recombined": filenames, "workspace": name}
