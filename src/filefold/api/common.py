"""Helpers shared by the API route modules."""
from __future__ import annotations

from fastapi import HTTPException

from filefold.core.keywords import Category
from filefold.core.splitter import SplitSelection, SubSplitSelection

from .server import UnsafeName, safe_segment

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
        raise HTTPException(400, f"Unknown category: {value!r}")

# Categories that must never be extracted into their own file.
# "model" owns *INCLUDE (see CATEGORY_MAP), so extracting it pulls FileFold's own
# generated include lines out of the mother and re-parents every other child under
# model.inp — which also reorders the deck. "unknown" has no meaningful boundary.
NON_EXTRACTABLE = {"unknown", "model"}


def reject_non_extractable(sel_data: list[dict]) -> None:
    """400 if a selection payload names a category that must stay in the mother file."""
    blocked = sorted({s.get("category") for s in sel_data} & NON_EXTRACTABLE)
    if blocked:
        raise HTTPException(
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
