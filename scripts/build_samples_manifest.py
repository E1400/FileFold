#!/usr/bin/env python3
"""Write src/filefold/web/static/samples/manifest.json for the sample decks.

The facts shown on each sample card (size, steps, materials, contact pairs, ...) are computed
from the decks with FileFold's own parser, so they cannot drift from the files. The prose
(title, blurb, what to try) is written here. tests/test_samples.py regenerates the manifest
and fails if the committed one differs, and checks that every suggested split really exists.

    python scripts/build_samples_manifest.py
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "src" / "filefold" / "web" / "static" / "samples"
MANIFEST = SAMPLES / "manifest.json"

import sys  # noqa: E402
sys.path.insert(0, str(ROOT / "src"))
from filefold.core.parser import parse  # noqa: E402

# Prose per sample. "try" entries are CATEGORY:KEY split options (a trailing * matches a family).
PROSE = {
    "Job-1": {
        "title": "Job-1: a small 2D model",
        "blurb": "A small plane-stress model with one steel material, two rigid bodies and a single "
                 "loading step. Small enough to try every feature in seconds, which makes it the best "
                 "place to start.",
        "try": ["mesh:nodes", "mesh:elements", "constraint:rigid", "material:material.steel", "step:step.step-1"],
    },
    "mmxmn": {
        "title": "mmxmn: a contact-heavy axisymmetric model",
        "blurb": "A 1.8 MB axisymmetric model with four named steps and six contact pairs, each with its "
                 "own interaction property and friction. Try splitting contact into pairs and interaction "
                 "properties, or pulling each step into its own file. The deck's own *INCLUDE line is left alone.",
        "try": ["contact:pairs", "contact:interactions", "step:step.mmxmn_1", "loads:amplitudes"],
    },
    "fempy_example": {
        "title": "fempy_example: a 5 MB 3D femur mesh",
        "blurb": "A large tetrahedral mesh exported from a bone-modelling tool: one part, thirty materials "
                 "and thirty matching sections. This is the one to try one-file-per-material on, and to see "
                 "how a part can be moved out whole.",
        "try": ["material:material.*", "mesh:part.femur", "mesh:nodes"],
    },
}


def _walk(blocks):
    for b in blocks:
        yield b
        yield from _walk(b.children)


def facts(path: Path) -> dict:
    data = path.read_bytes()
    top = parse(path, keep_lines=False)
    every = list(_walk(top))
    kw = Counter(b.keyword for b in every)
    return {
        "bytes": len(data),
        "lines": data.count(b"\n"),
        "line_endings": "windows" if b"\r\n" in data else "unix",
        "blocks": len(every),
        "steps": [b.params.get("NAME") or f"step {i}" for i, b in enumerate((b for b in every if b.keyword == "STEP"), 1)],
        "materials": kw["MATERIAL"],
        "parts": [b.params.get("NAME") for b in every if b.keyword == "PART"],
        "element_types": sorted({(b.params.get("TYPE") or "").upper() for b in every if b.keyword == "ELEMENT"} - {""}),
        "contact_pairs": kw["CONTACT PAIR"],
        "categories": dict(sorted(Counter(b.category.value for b in top).items())),
    }


def build() -> dict:
    return {
        "samples": [
            {"id": sample_id, "file": f"{sample_id}.inp", **prose, "facts": facts(SAMPLES / f"{sample_id}.inp")}
            for sample_id, prose in PROSE.items()
        ]
    }


def main() -> None:
    MANIFEST.write_text(json.dumps(build(), indent=2) + "\n", encoding="utf-8")
    print(f"wrote {MANIFEST}")


if __name__ == "__main__":
    main()
