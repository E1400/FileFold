from __future__ import annotations

from dataclasses import dataclass, field

from .keywords import Category


@dataclass
class Block:
    # Normalized keyword: uppercase, no leading asterisk (e.g. "SOLID SECTION")
    keyword: str

    # Params parsed from the keyword line: keys uppercase, value None for bare flags
    # e.g. "*step,inc=100,nlgeom" -> {"STEP": None, "INC": "100", "NLGEOM": None}
    params: dict[str, str | None]

    # Verbatim lines that belong directly to this block: the keyword line plus its
    # own data lines. Children's lines are NOT included here — see children below.
    # Lines include their original line endings so round-trip is byte-exact.
    raw_lines: list[str]

    category: Category

    # Nested blocks (only STEP carries children; flat blocks leave this empty).
    # *END STEP is stored as the final child so the tree is self-contained.
    children: list[Block] = field(default_factory=list)

    # 1-indexed line numbers in the source file (inclusive on both ends).
    # For container blocks (STEP), line_end covers the last line of the last child.
    line_start: int = 0
    line_end: int = 0


def emit(block: Block) -> list[str]:
    """Return all verbatim lines for a block and its children, in order."""
    lines = list(block.raw_lines) # start with this block's own lines
    for child in block.children:
        lines.extend(emit(child)) # recursively append each child's lines
    return lines
