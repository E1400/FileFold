from __future__ import annotations

import hashlib
import re
import shutil
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from .block import Block, emit
from .keywords import Category

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
class SplitSelection:
    """One category to extract, mapped to a child filename."""
    category: Category
    filename: str  # e.g. "mesh.inp" — no path, always same folder as mother


@dataclass
class ChildFile:
    filename: str
    path: Path
    category: Category
    sha256: str  # hash of written content, used for change detection on re-import


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
        child_contents: {filename: content} for each selection that has blocks
    """
    selection_map: dict[Category, str] = {s.category: s.filename for s in selections}
    mother_lines: list[str] = []
    child_lines: dict[Category, list[str]] = {s.category: [] for s in selections}
    include_inserted: set[Category] = set()

    for block in blocks:
        cat = block.category
        if cat in selection_map:
            child_lines[cat].extend(emit(block))
            if cat not in include_inserted:
                mother_lines.append(_include_line(selection_map[cat]))
                include_inserted.add(cat)
        else:
            mother_lines.extend(emit(block))

    child_contents = {
        s.filename: "".join(child_lines[s.category])
        for s in selections
        if "".join(child_lines[s.category])  # skip empty
    }
    return "".join(mother_lines), child_contents


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

    sel_map = {s.filename: s for s in selections}
    result = SplitResult(mother_path=mother_path, mother_sha256=_sha256(mother_text))
    for filename, text in child_contents.items():
        child_path = output_dir / filename
        child_path.write_text(text, encoding="utf-8", errors="surrogateescape")
        result.children.append(ChildFile(
            filename=filename,
            path=child_path,
            category=sel_map[filename].category,
            sha256=_sha256(text),
        ))

    return result
