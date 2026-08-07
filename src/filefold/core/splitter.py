from __future__ import annotations

import hashlib
import re
import shutil
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from .block import Block, emit
from .keywords import CATEGORY_SUB_KEYWORDS, Category
from .parser import CONTAINER_KEYWORDS

# Maps category -> output filename for non-STEP top-level blocks
CATEGORY_FILES: dict[Category, str] = {
    Category.MODEL: "model.inp",
    Category.MESH: "mesh.inp",
    Category.SECTION: "sections.inp",
    Category.MATERIAL: "materials.inp",
    Category.CONTACT: "contact.inp",
    Category.LOADS: "loads.inp",
    Category.OUTPUT: "output.inp",
    Category.STEP: "steps_misc.inp",  # top-level step-type keywords outside a STEP container
    Category.UNKNOWN: "unknown.inp",
}


def _step_filename(index: int, block: Block) -> str:
    name = block.params.get("NAME", "").strip()
    safe = re.sub(r"[^\w]+", "_", name).strip("_") if name else ""
    return f"step_{index:02d}_{safe}.inp" if safe else f"step_{index:02d}.inp"


def _write(path: Path, blocks: list[Block]) -> None:
    path.write_text(
        "".join(line for block in blocks for line in emit(block)),
        encoding="utf-8",
        errors="surrogateescape",
    )


def split(blocks: list[Block], source: Path, output_dir: Path) -> list[Path]:
    """Write split output files into output_dir. Returns list of files written."""
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    # 1. Copy original verbatim
    dest_original = output_dir / source.name
    shutil.copy2(source, dest_original)
    written.append(dest_original)

    # 2. Separate STEP containers from everything else
    step_blocks: list[Block] = []
    other_blocks: list[Block] = []
    for block in blocks:
        if block.keyword == "STEP":
            step_blocks.append(block)
        else:
            other_blocks.append(block)

    # 3. Group non-STEP blocks by category -> filename
    groups: dict[str, list[Block]] = defaultdict(list)
    for block in other_blocks:
        groups[CATEGORY_FILES[block.category]].append(block)

    for filename, file_blocks in groups.items():
        path = output_dir / filename
        _write(path, file_blocks)
        written.append(path)

    # 4. Write each STEP block to its own file under steps/
    if step_blocks:
        steps_dir = output_dir / "steps"
        steps_dir.mkdir(exist_ok=True)
        for i, step in enumerate(step_blocks, start=1):
            path = steps_dir / _step_filename(i, step)
            _write(path, [step])
            written.append(path)

    return written


# ---------------------------------------------------------------------------
# Include-split: partial split with *INCLUDE pointers in the mother file
# ---------------------------------------------------------------------------

@dataclass
class SubSplitSelection:
    """One sub-category to extract from a child, mapped to its own filename."""
    sub_category: str   # e.g. "nodes", "elements", "nsets", "elsets", "surfaces"
    filename: str       # e.g. "mesh-nodes.inp"


@dataclass
class SplitSelection:
    """One category to extract, mapped to a child filename."""
    category: Category
    filename: str  # e.g. "mesh.inp" — no path, always same folder as mother
    sub_selections: list[SubSplitSelection] = field(default_factory=list)


@dataclass
class ChildFile:
    filename: str
    path: Path
    category: Category | None
    sha256: str  # hash of written content, used for change detection on re-import
    parent: str | None = None  # parent child filename if this is a sub-child


@dataclass
class SplitResult:
    mother_path: Path          # modified mother file with *INCLUDE lines
    mother_sha256: str
    children: list[ChildFile] = field(default_factory=list)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="surrogateescape")).hexdigest()


def _include_line(filename: str) -> str:
    return f"*INCLUDE, INPUT={filename}\n"


def compute_split(
    blocks: list[Block],
    selections: list[SplitSelection],
) -> tuple[str, dict[str, str]]:
    """Compute split content in memory without writing any files.

    Returns:
        mother_content: the modified mother file text (with *INCLUDE lines)
        child_contents: {filename: content} for each child and sub-child that has blocks
    """
    sel_map: dict[Category, SplitSelection] = {s.category: s for s in selections}
    mother_lines: list[str] = []
    child_lines: dict[str, list[str]] = {}   # filename -> line list
    cat_inserted: set[Category] = set()       # categories already *INCLUDEd in mother
    sub_inserted: dict[str, set[str]] = {}    # parent_filename -> set of sub_cats inserted

    def _route_sub(block: Block, sel: SplitSelection) -> None:
        """Route one block into sel's child file or its sub-files.

        Recurses into *PART/*ASSEMBLY containers so that NODE/ELEMENT blocks
        nested inside a *PART scope are routed to the correct sub-split file.
        The container header (*PART…) and footer (*END PART) stay in the
        parent child file; only the inner keyword blocks are re-routed.
        """
        sub_map = {ss.sub_category: ss for ss in sel.sub_selections}
        kw_map = CATEGORY_SUB_KEYWORDS.get(sel.category, {})
        block_sub_cat = kw_map.get(block.keyword)

        if block_sub_cat and block_sub_cat in sub_map:
            ss = sub_map[block_sub_cat]
            child_lines.setdefault(ss.filename, []).extend(emit(block))
            parent_inserts = sub_inserted.setdefault(sel.filename, set())
            if block_sub_cat not in parent_inserts:
                child_lines.setdefault(sel.filename, []).append(_include_line(ss.filename))
                parent_inserts.add(block_sub_cat)
        elif block.keyword in CONTAINER_KEYWORDS and block.children:
            # Container block (e.g. *PART): emit only its header line(s) to the child
            # file, then recurse into its children so nested keyword blocks get routed.
            child_lines.setdefault(sel.filename, []).extend(block.raw_lines)
            for child in block.children:
                _route_sub(child, sel)
        else:
            child_lines.setdefault(sel.filename, []).extend(emit(block))

    for block in blocks:
        cat = block.category
        if cat not in sel_map:
            mother_lines.extend(emit(block))
            continue

        sel = sel_map[cat]

        # Insert *INCLUDE in mother at first block of this category
        if cat not in cat_inserted:
            mother_lines.append(_include_line(sel.filename))
            cat_inserted.add(cat)

        if not sel.sub_selections:
            # No sub-splits: block goes directly to the child file
            child_lines.setdefault(sel.filename, []).extend(emit(block))
        else:
            _route_sub(block, sel)

    return "".join(mother_lines), {f: "".join(ls) for f, ls in child_lines.items() if ls}


def split_with_includes(
    blocks: list[Block],
    source: Path,
    output_dir: Path,
    selections: list[SplitSelection],
) -> SplitResult:
    """Partial split: extract selected categories into child files, insert
    *INCLUDE lines in the mother at each category's first occurrence.

    All output files are written flat into output_dir (no subdirectories)
    so *INCLUDE paths are always just the filename.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    mother_text, child_contents = compute_split(blocks, selections)

    mother_path = output_dir / source.name
    mother_path.write_text(mother_text, encoding="utf-8", errors="surrogateescape")

    # Build lookup: filename -> (category, parent_filename)
    file_meta: dict[str, tuple[Category | None, str | None]] = {}
    for sel in selections:
        file_meta[sel.filename] = (sel.category, None)
        for ss in sel.sub_selections:
            file_meta[ss.filename] = (sel.category, sel.filename)

    result = SplitResult(mother_path=mother_path, mother_sha256=_sha256(mother_text))
    for filename, text in child_contents.items():
        child_path = output_dir / filename
        child_path.write_text(text, encoding="utf-8", errors="surrogateescape")
        cat, parent = file_meta.get(filename, (None, None))
        result.children.append(ChildFile(
            filename=filename,
            path=child_path,
            category=cat,
            sha256=_sha256(text),
            parent=parent,
        ))

    return result
