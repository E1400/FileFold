"""Stateless inspection: parse an uploaded deck, list sub-split options."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, File, UploadFile

from filefold.core.keywords import CATEGORY_SUB_KEYWORDS, CATEGORY_SUB_OPTIONS
from filefold.core.parser import parse

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
        return {
            "filename": file.filename,
            "blocks": _blocks_to_json(blocks),
            "sub_cats": _present_sub_cats(blocks),
        }
    finally:
        tmp_path.unlink(missing_ok=True)


def _present_sub_cats(blocks) -> dict[str, list[str]]:
    """Per extractable category, the sub-categories that actually occur in these blocks.

    The create menu must not offer a sub-split (e.g. "Ties") for a deck that has no
    such blocks: it would be a checkbox that creates nothing.
    """
    out: dict[str, list[str]] = {}
    for cat, kw_map in CATEGORY_SUB_KEYWORDS.items():
        found: set[str] = set()
        def scan(bs):
            # Only descend into blocks of this category (e.g. *PART for mesh). A
            # *BOUNDARY inside a *STEP travels with its step and can never be
            # sub-split, so it must not make "boundary" look available.
            for b in bs:
                if b.category == cat:
                    sc = kw_map.get(b.keyword)
                    if sc:
                        found.add(sc)
                    scan(b.children)
        scan(blocks)
        if found:
            out[cat.value] = sorted(found)
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
