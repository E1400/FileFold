"""Application logic, independent of any web framework.

Two front ends call these functions with plain Python values and get plain values
back: the FastAPI routes in `filefold.api.routes` (server and desktop app) and the
in-browser dispatcher in `filefold.browser` (static GitHub Pages build, running under
Pyodide). Keeping one implementation is what makes the two builds behave identically.

Errors are raised as ServiceError(status, detail); a rejected path segment raises
UnsafeName (a client error, status 400).
"""
from __future__ import annotations

import hashlib
import io
import re
import shutil
import tempfile
import zipfile
from contextlib import contextmanager
from pathlib import Path

from filefold.api.server import UnsafeName, child_path, list_workspaces, safe_segment, workspace_path
from filefold.core.keywords import CATEGORY_SUB_OPTIONS, Category
from filefold.core.parser import parse
from filefold.core.splitter import (
    SplitSelection, SubSplitSelection, read_raw, split_with_includes,
)
from filefold.core.subsplits import discover
from filefold.core.workspace import Workspace

__all__ = ["ServiceError", "UnsafeName", "NON_EXTRACTABLE"]

# Categories that must never be extracted into their own file.
# "model" owns *INCLUDE (see CATEGORY_MAP), so extracting it pulls FileFold's own
# generated include lines out of the mother and re-parents every other child under
# model.inp — which also reorders the deck. "unknown" has no meaningful boundary.
NON_EXTRACTABLE = {"unknown", "model"}


class ServiceError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


# ---------------------------------------------------------------------------
# Shared validation / helpers
# ---------------------------------------------------------------------------

def validate_selection_filenames(sel_data: list[dict]) -> None:
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


def parse_category(value: str) -> Category:
    """Turn a client-supplied category string into a Category, or a 400."""
    try:
        return Category(value)
    except ValueError:
        raise ServiceError(400, f"Unknown category: {value!r}")


def reject_non_extractable(sel_data: list[dict]) -> None:
    blocked = sorted({s.get("category") for s in sel_data} & NON_EXTRACTABLE)
    if blocked:
        raise ServiceError(
            400,
            f"Category '{blocked[0]}' cannot be extracted into its own file. "
            f"It owns the *INCLUDE directives that hold the workspace together.",
        )


def selections_from_payload(sel_data: list[dict]) -> list[SplitSelection]:
    """Build SplitSelections (with sub-selections) from a client JSON payload."""
    return [
        SplitSelection(
            parse_category(s["category"]),
            s["filename"],
            sub_selections=[
                SubSplitSelection(ss["sub_category"], ss["filename"])
                for ss in s.get("sub_selections", [])
            ],
        )
        for s in sel_data
    ]


def _load(name: str) -> tuple[Path, Workspace]:
    ws_dir = workspace_path(name)
    try:
        return ws_dir, Workspace.load(ws_dir)
    except FileNotFoundError:
        raise ServiceError(404, f"Workspace '{name}' not found")


def safe_upload_name(filename: str) -> str:
    """The leaf of a client-supplied filename. Uploads are staged as <tmpdir>/<name>, so a
    name like '../../x.inp' must never be able to leave the temp directory."""
    leaf = (filename or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
    return leaf if leaf not in ("", ".", "..") else "upload.inp"


@contextmanager
def _staged(filename: str, data: bytes | Path):
    """Yield a path to the uploaded deck (the parser reads from a path).

    `data` is either bytes (the browser build) or a Path already on disk under the
    right name (the server, which streams uploads to disk instead of holding a
    500 MB deck in memory two or three times over).
    """
    if isinstance(data, Path):
        yield data
        return
    tmpdir = Path(tempfile.mkdtemp())
    try:
        path = tmpdir / safe_upload_name(filename)
        path.write_bytes(data)
        yield path
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _file_stats(path: Path) -> tuple[str, int]:
    """(sha256, line count) of a workspace file, streamed so memory does not scale with it.

    The hash is over the raw bytes, which equals filefold.core.splitter._sha256 of the
    text because every read in FileFold round-trips bytes exactly (surrogateescape).
    """
    digest = hashlib.sha256()
    lines = 0
    with open(path, "rb") as fh:
        while chunk := fh.read(1024 * 1024):
            digest.update(chunk)
    with open(path, encoding="utf-8", errors="surrogateescape", newline="") as fh:
        for _ in fh:
            lines += 1
    return digest.hexdigest(), lines


def blocks_to_json(blocks) -> list[dict]:
    return [
        {
            "keyword": b.keyword,
            "category": b.category.value,
            "line_start": b.line_start,
            "line_end": b.line_end,
            "params": b.params,
            "children": blocks_to_json(b.children),
        }
        for b in blocks
    ]


def sub_split_info(blocks) -> tuple[dict[str, list[dict[str, str]]], dict[str, list[list[str]]]]:
    """Per category: the sub-split options that exist in the deck, and their block claims.

    The create menu must not offer a sub-split (e.g. "Ties", or a material that is not
    in the deck) that would create nothing, and the UI uses the claims to disable options
    whose blocks are already taken by another selected option. Includes name-based
    options such as one per material, step, part and element type.
    """
    options: dict[str, list[dict[str, str]]] = {}
    claims: dict[str, list[list[str]]] = {}
    for cat in Category:
        opts, cl = discover(cat, blocks)
        if opts:
            options[cat.value] = [o.as_dict() for o in opts]
            claims[cat.value] = cl
    return options, claims


# ---------------------------------------------------------------------------
# Inspect
# ---------------------------------------------------------------------------

def inspect(filename: str, data: bytes | Path) -> dict:
    """Parse an uploaded .inp file and return its block tree."""
    with _staged(filename, data) as tmp_path:
        blocks = parse(tmp_path, keep_lines=False)
        opts, claims = sub_split_info(blocks)
        return {
            "filename": filename,
            "blocks": blocks_to_json(blocks),
            "sub_options": opts,
            "sub_claims": claims,
            "sub_cats": {c: [o["sub_category"] for o in os_] for c, os_ in opts.items()},
        }


def static_sub_options() -> dict:
    """The fixed (keyword-group) sub-split table, independent of any deck."""
    return {cat.value: opts for cat, opts in CATEGORY_SUB_OPTIONS.items()}


# ---------------------------------------------------------------------------
# Workspaces
# ---------------------------------------------------------------------------

def list_all_workspaces() -> dict:
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
            try:
                return (ws_dir / fn).stat().st_size
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


def create_workspace(name: str, filename: str, data: bytes | Path, sel_data: list[dict]) -> dict:
    """Create a new workspace from an uploaded mother file."""
    ws_name = safe_segment(name.strip() or Path(filename or "model").stem, "workspace name")
    ws_dir = workspace_path(ws_name)
    if ws_dir.exists():
        raise ServiceError(400, f"Workspace '{ws_name}' already exists")

    reject_non_extractable(sel_data)
    validate_selection_filenames(sel_data)
    sel_list = selections_from_payload(sel_data)

    # Write to a temp dir using the original filename so Workspace.create
    # records the right source_name in the manifest from the start.
    with _staged(filename, data) as tmp_path:
        ws = Workspace.create(ws_dir, tmp_path, sel_list)
    return {"workspace": ws_name, "files": list(ws.file_records.keys())}


def get_workspace(name: str) -> dict:
    """Return workspace status including per-file hash state."""
    ws_dir, ws = _load(name)

    files = []
    for fname, rec in ws.file_records.items():
        fpath = ws_dir / fname
        if fpath.exists():
            current_sha, line_count = _file_stats(fpath)
            edited = bool(rec.sha256) and current_sha != rec.sha256
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

    # Categories that actually exist in this workspace:
    # (a) categories of already-extracted child files, from file_records
    # (b) top-level categories still present in the current mother file
    # Only top-level blocks matter — blocks nested inside *STEP/*PART containers
    # (e.g. *BOUNDARY inside *STEP) cannot be independently extracted.
    available_cats: set[str] = set()
    for rec in ws.file_records.values():
        if rec.role == "child" and rec.category and rec.category not in NON_EXTRACTABLE:
            available_cats.add(rec.category)
    mother_path = ws_dir / ws.source_name
    mother_blocks = parse(mother_path, keep_lines=False) if mother_path.exists() else []
    for b in mother_blocks:
        if b.category.value not in NON_EXTRACTABLE:
            available_cats.add(b.category.value)

    # Sub-split options per category, from what is actually in the deck.
    # Already extracted: scan the child with its sub-files folded back in, which is exactly
    # what "Apply changes" re-splits (recombine, then split again). Still in the mother:
    # scan only that category's top-level blocks.
    sub_options: dict[str, list[dict[str, str]]] = {}
    sub_claims: dict[str, list[list[str]]] = {}
    sel_by_cat = {s.category.value: s for s in ws.selections}
    for cat_str in sorted(available_cats):
        try:
            cat_enum = Category(cat_str)
        except ValueError:
            continue
        sel = sel_by_cat.get(cat_str)
        if sel and (ws_dir / sel.filename).exists():
            blocks = _blocks_with_subfiles_folded_back(ws_dir, sel)
        else:
            blocks = [b for b in mother_blocks if b.category == cat_enum]
        opts, claims = discover(cat_enum, blocks)
        if opts:
            sub_options[cat_str] = [o.as_dict() for o in opts]
            sub_claims[cat_str] = claims

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
        "available_sub_cats": {c: [o["sub_category"] for o in os_] for c, os_ in sub_options.items()},
        "sub_options": sub_options,
        "sub_claims": sub_claims,
    }


def _blocks_with_subfiles_folded_back(ws_dir: Path, sel: SplitSelection):
    """Parse a child file as it would look after recombining its sub-files."""
    sub_files = {ss.filename for ss in sel.sub_selections}

    def expand(path: Path) -> str:
        text = read_raw(path)

        def inline(m: re.Match) -> str:
            name = m.group(1)
            target = ws_dir / name
            if name not in sub_files or not target.is_file():
                return m.group(0)
            body = expand(target)
            return body if body.endswith("\n") else body + "\n"

        return re.sub(r"^\*INCLUDE,[ \t]*INPUT=(\S+?)[ \t]*\r?\n", inline, text, flags=re.M | re.I)

    tmpdir = Path(tempfile.mkdtemp())
    try:
        folded = tmpdir / sel.filename
        folded.write_text(expand(ws_dir / sel.filename), encoding="utf-8", errors="surrogateescape", newline="")
        return parse(folded, keep_lines=False)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def rename_workspace(name: str, new_name: str) -> dict:
    new_name = (new_name or "").strip()
    if not new_name:
        raise ServiceError(400, "name is required")
    old_dir = workspace_path(name)
    new_dir = workspace_path(new_name)
    if not old_dir.exists():
        raise ServiceError(404, f"Workspace '{name}' not found")
    if new_dir.exists():
        raise ServiceError(400, f"Workspace '{new_name}' already exists")
    ws = Workspace.load(old_dir)
    ws.name = new_name
    ws._save()
    old_dir.rename(new_dir)
    return {"workspace": new_name}


def delete_workspace(name: str) -> dict:
    ws_dir = workspace_path(name)
    if not ws_dir.exists():
        raise ServiceError(404, f"Workspace '{name}' not found")
    shutil.rmtree(ws_dir)
    return {"deleted": name}


# ---------------------------------------------------------------------------
# Editing a workspace's splits
# ---------------------------------------------------------------------------

def extract_splits(name: str, sel_data: list[dict]) -> dict:
    """Extract new splits from the existing mother file without re-uploading it."""
    if not sel_data:
        raise ServiceError(400, "selections is required")
    reject_non_extractable(sel_data)
    ws_dir, ws = _load(name)
    mother_path = ws_dir / ws.source_name
    if not mother_path.exists():
        raise ServiceError(404, f"Mother file '{ws.source_name}' not found")
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


def resplit_child(name: str, category_str: str, sub_sel_data: list[dict]) -> dict:
    """Modify sub-splits for an already-extracted category (recombine then re-extract)."""
    category_str = (category_str or "").strip()
    if not category_str:
        raise ServiceError(400, "category is required")
    _, ws = _load(name)
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
            raise ServiceError(400, f"'{fn}' is already used by another file in this workspace")
        if fn in seen:
            raise ServiceError(400, f"Duplicate sub-split filename: '{fn}'")
        seen.add(fn)

    new_sub = [SubSplitSelection(ss["sub_category"], ss["filename"]) for ss in sub_sel_data]
    try:
        ws.resplit_child(category_str, new_sub)
    except (ValueError, FileNotFoundError) as e:
        raise ServiceError(400, str(e))
    return {"category": category_str, "sub_extracted": [ss["filename"] for ss in sub_sel_data], "workspace": name}


def rename_file(name: str, old_filename: str, new_filename: str) -> dict:
    """Rename a child or grandchild file without re-extracting it."""
    old_filename = safe_segment(old_filename, "old_filename")
    new_filename = safe_segment(new_filename, "new_filename")
    if old_filename == new_filename:
        return {"renamed": old_filename, "workspace": name}
    _, ws = _load(name)
    try:
        ws.rename_child(old_filename, new_filename)
    except (ValueError, FileNotFoundError) as e:
        raise ServiceError(400, str(e))
    return {"renamed": new_filename, "workspace": name}


def recombine(name: str, filenames: list[str]) -> dict:
    """Fold listed child/sub-child files back into their parent (reverse of split)."""
    if not filenames:
        raise ServiceError(400, "filenames is required")
    filenames = [safe_segment(f, "filename") for f in filenames]
    _, ws = _load(name)

    # recombine() ignores names it doesn't recognise, so a typo or a stale UI would
    # report success while folding nothing back. Fail loudly instead.
    known = {s.filename for s in ws.selections} | {
        ss.filename for s in ws.selections for ss in s.sub_selections
    }
    unknown = [f for f in filenames if f not in known]
    if unknown:
        raise ServiceError(400, f"Not an extracted file in this workspace: {unknown[0]!r}")
    try:
        ws.recombine(filenames)
    except (ValueError, FileNotFoundError) as e:
        raise ServiceError(400, str(e))
    return {"recombined": filenames, "workspace": name}


# ---------------------------------------------------------------------------
# Re-import
# ---------------------------------------------------------------------------

def _status_json(s) -> dict:
    return {
        "filename": s.filename,
        "category": s.category.value,
        "changed_in_new_mother": s.changed_in_new_mother,
        "manually_edited": s.manually_edited,
    }


def reimport_preview(name: str, filename: str, data: bytes | Path) -> dict:
    """Upload a new mother file and get a preview of what would change."""
    _, ws = _load(name)
    with _staged(filename, data) as tmp_path:
        blocks = parse(tmp_path, keep_lines=False)
        preview = ws.reimport_preview(tmp_path)
        return {
            "filename": filename or "upload.inp",
            "blocks": blocks_to_json(blocks),
            "safe_to_update": [_status_json(s) for s in preview.safe_to_update],
            "needs_attention": [_status_json(s) for s in preview.needs_attention],
            "unchanged": [_status_json(s) for s in preview.unchanged],
        }


def reimport_apply(name: str, filename: str, data: bytes | Path, to_update: list[str], added_data: list[dict]) -> dict:
    """Apply a reimport: update approved children, add new selections, refresh mother."""
    _, ws = _load(name)
    update_set = set(to_update)
    added: list[SplitSelection] | None = None
    if added_data:
        reject_non_extractable(added_data)
        validate_selection_filenames(added_data)
        added = [SplitSelection(parse_category(s["category"]), s["filename"]) for s in added_data]

    with _staged(filename, data) as tmp_path:
        preview = ws.reimport_preview(tmp_path)
        ws.reimport_apply(tmp_path, preview, update_set, added_selections=added)
    return {"updated": list(update_set), "workspace": ws.name}


# ---------------------------------------------------------------------------
# Export and file access
# ---------------------------------------------------------------------------

def export_zip(name: str) -> bytes:
    """All workspace files as a zip (hidden manifest files excluded)."""
    ws_dir = workspace_path(name)
    if not ws_dir.exists():
        raise ServiceError(404, f"Workspace '{name}' not found")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in ws_dir.iterdir():
            if f.is_file() and not f.name.startswith("."):
                zf.write(f, f.name)
    return buf.getvalue()


def file_path(name: str, filename: str) -> Path:
    """Validated path of an existing workspace file (lets the server stream it from disk)."""
    fpath = child_path(workspace_path(name), filename)
    if not fpath.exists():
        raise ServiceError(404, f"File '{filename}' not found in workspace '{name}'")
    return fpath


def read_file(name: str, filename: str) -> bytes:
    """Raw content of a workspace file."""
    return file_path(name, filename).read_bytes()


def write_file(name: str, filename: str, body: bytes) -> dict:
    """Overwrite a workspace file with edited content."""
    fpath = child_path(workspace_path(name), filename)
    if not fpath.exists():
        raise ServiceError(404, f"File '{filename}' not found in workspace '{name}'")
    content = body.decode("utf-8", errors="surrogateescape")
    # newline="" so the editor round-trips a CRLF deck byte-for-byte instead of
    # rewriting its line endings on every save.
    with open(fpath, "w", encoding="utf-8", errors="surrogateescape", newline="") as fh:
        fh.write(content)
    return {"saved": filename, "bytes": len(content)}
