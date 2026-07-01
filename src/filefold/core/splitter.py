from __future__ import annotations

import re
import shutil
from collections import defaultdict
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
