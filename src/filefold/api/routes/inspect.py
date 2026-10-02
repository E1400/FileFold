"""Stateless inspection: parse an uploaded deck, list sub-split options."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, File, UploadFile

from filefold.core.keywords import CATEGORY_SUB_OPTIONS, Category
from filefold.core.parser import parse
from filefold.core.subsplits import discover_options

router = APIRouter()


@router.post("/api/inspect")
async def inspect_file(file: UploadFile = File(...)):
    """Parse an uploaded .inp file and return its block tree."""
    import tempfile
    suffix = Path(file.filename or "upload.inp").suffix
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(await file.read())
        tmp_path = Path(tmp.name)

    try:
        blocks = parse(tmp_path)
        opts = _sub_options_json(blocks)
        return {
            "filename": file.filename,
            "blocks": _blocks_to_json(blocks),
            "sub_options": opts,
            "sub_cats": {c: [o["sub_category"] for o in os_] for c, os_ in opts.items()},
        }
    finally:
        tmp_path.unlink(missing_ok=True)


def _sub_options_json(blocks) -> dict[str, list[dict[str, str]]]:
    """Per category, the sub-split options that would actually produce a file.

    The create menu must not offer a sub-split (e.g. "Ties", or a material that is not
    in the deck) that would create nothing. Includes name-based options such as one
    per material, step, part and element type.
    """
    out: dict[str, list[dict[str, str]]] = {}
    for cat in Category:
        opts = discover_options(cat, blocks)
        if opts:
            out[cat.value] = [o.as_dict() for o in opts]
    return out


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

@router.get("/api/sub-options")
async def get_sub_options():
    """Return available sub-split options per category."""
    return {
        cat.value: opts
        for cat, opts in CATEGORY_SUB_OPTIONS.items()
    }
