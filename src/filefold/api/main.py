"""FastAPI application — REST API + static web frontend."""
from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse

from filefold.core.keywords import CATEGORY_SUB_OPTIONS, CATEGORY_SUB_KEYWORDS, Category
from filefold.core.parser import parse
from filefold.core.splitter import SplitSelection, SubSplitSelection, split_with_includes
from filefold.core.workspace import Workspace

from .server import UnsafeName, WORKSPACE_BASE, list_workspaces, safe_segment, workspace_path

app = FastAPI(title="FileFold", version="0.1.0")


@app.exception_handler(UnsafeName)
async def _unsafe_name_handler(request: Request, exc: UnsafeName) -> JSONResponse:
    """A rejected name is a client error, not a crash."""
    return JSONResponse(status_code=400, content={"detail": str(exc)})


def _validate_selection_filenames(sel_data: list[dict]) -> None:
    """Reject traversal in every filename a selection payload can carry.

    Selections nest sub-selections, and both levels name files that get written
    into the workspace directory.
    """
    seen: set[str] = set()
    for s in sel_data:
        fn = safe_segment(s.get("filename", ""), "filename")
        if fn in seen:
            raise UnsafeName(f"Duplicate filename in selections: {fn!r}")
        seen.add(fn)
        for ss in s.get("sub_selections", []):
            sub_fn = safe_segment(ss.get("filename", ""), "filename")
            if sub_fn in seen:
                raise UnsafeName(f"Duplicate filename in selections: {sub_fn!r}")
            seen.add(sub_fn)


def _parse_category(value: str) -> Category:
    """Turn a client-supplied category string into a Category, or a 400."""
    try:
        return Category(value)
    except ValueError:
        raise HTTPException(400, f"Unknown category: {value!r}")

# Categories that must never be extracted into their own file.
# "model" owns *INCLUDE (see CATEGORY_MAP), so extracting it pulls FileFold's own
# generated include lines out of the mother and re-parents every other child under
# model.inp — which also reorders the deck. "unknown" has no meaningful boundary.
NON_EXTRACTABLE = {"unknown", "model"}

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

@app.get("/api/sub-options")
async def get_sub_options():
    """Return available sub-split options per category."""
    return {
        cat.value: opts
        for cat, opts in CATEGORY_SUB_OPTIONS.items()
    }


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

    ws_name = safe_segment(name.strip() or Path(file.filename or "model").stem, "workspace name")
    ws_dir = workspace_path(ws_name)
    if ws_dir.exists():
        raise HTTPException(400, f"Workspace '{ws_name}' already exists")

    sel_data = json.loads(selections) if selections else []
    blocked = sorted({s.get("category") for s in sel_data} & NON_EXTRACTABLE)
    if blocked:
        raise HTTPException(
            400,
            f"Category '{blocked[0]}' cannot be extracted into its own file. "
            f"It owns the *INCLUDE directives that hold the workspace together.",
        )
    _validate_selection_filenames(sel_data)
    sel_list = [
        SplitSelection(
            _parse_category(s["category"]),
            s["filename"],
            sub_selections=[
                SubSplitSelection(ss["sub_category"], ss["filename"])
                for ss in s.get("sub_selections", [])
            ],
        )
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
            text = fpath.read_text(encoding="utf-8", errors="surrogateescape")
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


@app.patch("/api/workspaces/{name}")
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

@app.post("/api/workspaces/{name}/extract")
async def extract_splits(name: str, request: Request):
    """Extract new splits from the existing mother file without re-uploading it."""
    body = await request.json()
    sel_data = body.get("selections", [])
    if not sel_data:
        raise HTTPException(400, "selections is required")
    blocked = sorted({s.get("category") for s in sel_data} & NON_EXTRACTABLE)
    if blocked:
        raise HTTPException(
            400,
            f"Category '{blocked[0]}' cannot be extracted into its own file. "
            f"It owns the *INCLUDE directives that hold the workspace together.",
        )
    ws_dir = workspace_path(name)
    try:
        ws = Workspace.load(ws_dir)
    except FileNotFoundError:
        raise HTTPException(404, f"Workspace '{name}' not found")
    mother_path = ws_dir / ws.source_name
    if not mother_path.exists():
        raise HTTPException(404, f"Mother file '{ws.source_name}' not found")
    _validate_selection_filenames(sel_data)
    new_sels = [
        SplitSelection(
            _parse_category(s["category"]),
            s["filename"],
            sub_selections=[
                SubSplitSelection(ss["sub_category"], ss["filename"])
                for ss in s.get("sub_selections", [])
            ],
        )
        for s in sel_data
    ]
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


@app.post("/api/workspaces/{name}/resplit-child")
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


@app.post("/api/workspaces/{name}/rename-file")
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


@app.post("/api/workspaces/{name}/recombine")
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
        added_data = json.loads(added_selections)
        blocked = sorted({s.get("category") for s in added_data} & NON_EXTRACTABLE)
        if blocked:
            raise HTTPException(
                400,
                f"Category '{blocked[0]}' cannot be extracted into its own file. "
                f"It owns the *INCLUDE directives that hold the workspace together.",
            )
        _validate_selection_filenames(added_data)
        added = [
            SplitSelection(_parse_category(s["category"]), s["filename"])
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
