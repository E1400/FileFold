"""Workspace CRUD and status."""
from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from filefold.core.keywords import CATEGORY_SUB_KEYWORDS, Category
from filefold.core.parser import parse
from filefold.core.splitter import read_raw
from filefold.core.workspace import Workspace

from ..common import (
    NON_EXTRACTABLE, reject_non_extractable, selections_from_payload,
    validate_selection_filenames,
)
from ..server import list_workspaces, safe_segment, workspace_path

router = APIRouter()


@router.get("/api/workspaces")
async def list_all_workspaces():
    """Workspace names plus a cheap summary for the registry cards.

    Everything here comes from the manifest and os.stat — never from reading file
    contents. A mesh deck can run to six figures of lines, and the home screen
    must not pay that cost on every load just to show a size.
    """
    names = list_workspaces()
    summaries = []
    for name in names:
        ws_dir = workspace_path(name)
        try:
            ws = Workspace.load(ws_dir)
        except (FileNotFoundError, KeyError, ValueError):
            summaries.append({"name": name, "broken": True})
            continue

        def _size(fn: str) -> int:
            p = ws_dir / fn
            try:
                return p.stat().st_size
            except OSError:
                return 0

        by_cat: dict[str, int] = {}
        sub_count = 0
        for sel in ws.selections:
            by_cat[sel.category.value] = by_cat.get(sel.category.value, 0) + _size(sel.filename)
            for ss in sel.sub_selections:
                if (ws_dir / ss.filename).exists():
                    sub_count += 1
                    by_cat[sel.category.value] = by_cat.get(sel.category.value, 0) + _size(ss.filename)

        present = [fn for fn in ws.file_records if (ws_dir / fn).exists()]
        summaries.append({
            "name": name,
            "source_name": ws.source_name,
            "updated_at": ws.updated_at,
            "file_count": len(present),
            "split_count": len(ws.selections),
            "sub_count": sub_count,
            "bytes": sum(_size(fn) for fn in present),
            "categories": [
                {"category": c, "bytes": b}
                for c, b in sorted(by_cat.items(), key=lambda kv: -kv[1])
            ],
        })
    return {"workspaces": names, "summaries": summaries}


@router.post("/api/workspaces")
async def create_workspace(
    file: UploadFile = File(...),
    name: Annotated[str, Form()] = "",
    selections: Annotated[str, Form()] = "",  # JSON: [{"category":"mesh","filename":"mesh.inp"}]
):
    """Create a new workspace from an uploaded mother file."""
    import json, shutil, tempfile

    ws_name = safe_segment(name.strip() or Path(file.filename or "model").stem, "workspace name")
    ws_dir = workspace_path(ws_name)
    if ws_dir.exists():
        raise HTTPException(400, f"Workspace '{ws_name}' already exists")

    sel_data = json.loads(selections) if selections else []
    reject_non_extractable(sel_data)
    validate_selection_filenames(sel_data)
    sel_list = selections_from_payload(sel_data)

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


@router.get("/api/workspaces/{name}")
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
            text = read_raw(fpath)
            current = _sha256(text)
            edited = (bool(rec.sha256) and current != rec.sha256)
            line_count = len(text.splitlines())
        else:
            edited = False
            line_count = None
        files.append({
            "filename": fname,
            "role": rec.role,
            "category": rec.category,
            "parent": rec.parent,
            "manually_edited": edited,
            "exists": fpath.exists(),
            "line_count": line_count,
        })

    # Compute which categories actually exist in this workspace:
    # (a) categories of already-extracted child files, from file_records
    # (b) top-level categories still present in the current mother file
    # Only top-level blocks matter — blocks nested inside *STEP/*PART containers
    # (e.g. *BOUNDARY inside *STEP) cannot be independently extracted.
    _SKIP = NON_EXTRACTABLE
    available_cats: set[str] = set()
    for rec in ws.file_records.values():
        if rec.role == "child" and rec.category and rec.category not in _SKIP:
            available_cats.add(rec.category)
    mother_path = ws_dir / ws.source_name
    mother_blocks = parse(mother_path) if mother_path.exists() else []
    for b in mother_blocks:
        v = b.category.value
        if v not in _SKIP:
            available_cats.add(v)

    # Compute which sub-categories exist per category.
    # If the category is already extracted, scan the child file (handles *PART nesting).
    # If still in the mother, scan only the top-level blocks of that category.
    def _scan_sub_cats(blocks, kw_map, found):
        for b in blocks:
            sc = kw_map.get(b.keyword)
            if sc:
                found.add(sc)
            _scan_sub_cats(b.children, kw_map, found)

    available_sub_cats: dict[str, list[str]] = {}
    sel_by_cat = {s.category.value: s for s in ws.selections}
    for cat_str in available_cats:
        try:
            cat_enum = Category(cat_str)
        except ValueError:
            continue
        kw_map = CATEGORY_SUB_KEYWORDS.get(cat_enum)
        if not kw_map:
            continue
        found: set[str] = set()
        sel = sel_by_cat.get(cat_str)
        if sel and (ws_dir / sel.filename).exists():
            _scan_sub_cats(parse(ws_dir / sel.filename), kw_map, found)
            # A sub-category that has already been extracted no longer appears in
            # the child file (its blocks live in the grandchild), so the scan above
            # cannot see it. Seed it from the recorded sub-selections — same rule
            # as case (a) for available_cats — otherwise the UI drops the row and
            # the user can neither uncheck it nor keep it across an apply.
            for ss in sel.sub_selections:
                if (ws_dir / ss.filename).exists():
                    found.add(ss.sub_category)
        else:
            for b in mother_blocks:
                if b.category == cat_enum:
                    _scan_sub_cats([b], kw_map, found)
        if found:
            available_sub_cats[cat_str] = sorted(found)

    return {
        "name": ws.name,
        "source_name": ws.source_name,
        "selections": [
            {
                "category": s.category.value,
                "filename": s.filename,
                "sub_selections": [{"sub_category": ss.sub_category, "filename": ss.filename} for ss in s.sub_selections],
            }
            for s in ws.selections
        ],
        "updated_at": ws.updated_at,
        "files": files,
        "available_categories": sorted(available_cats),
        "available_sub_cats": available_sub_cats,
    }


@router.patch("/api/workspaces/{name}")
async def rename_workspace(name: str, request: Request):
    """Rename a workspace directory and update its manifest."""
    body = await request.json()
    new_name = body.get("name", "").strip()
    if not new_name:
        raise HTTPException(400, "name is required")
    old_dir = workspace_path(name)
    new_dir = workspace_path(new_name)
    if not old_dir.exists():
        raise HTTPException(404, f"Workspace '{name}' not found")
    if new_dir.exists():
        raise HTTPException(400, f"Workspace '{new_name}' already exists")
    ws = Workspace.load(old_dir)
    ws.name = new_name
    ws._save()
    old_dir.rename(new_dir)
    return {"workspace": new_name}


@router.delete("/api/workspaces/{name}")
async def delete_workspace(name: str):
    import shutil
    ws_dir = workspace_path(name)
    if not ws_dir.exists():
        raise HTTPException(404, f"Workspace '{name}' not found")
    shutil.rmtree(ws_dir)
    return {"deleted": name}
