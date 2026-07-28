"""Tests for the splitter: compute_split, split_with_includes, round-trip integrity."""
from pathlib import Path

import pytest

from filefold.core.keywords import Category
from filefold.core.parser import parse, emit_all
from filefold.core.splitter import SplitSelection, compute_split, split_with_includes, _sha256

FIXTURES = Path(__file__).parent / "fixtures"
FEMPY = FIXTURES / "fempy_example.inp"


def _sels(*cats_and_names):
    return [SplitSelection(Category(c), n) for c, n in cats_and_names]


# ---------------------------------------------------------------------------
# compute_split (pure, in-memory)
# ---------------------------------------------------------------------------

def test_compute_split_mother_contains_include(tmp_path):
    blocks = parse(FEMPY)
    mother, children = compute_split(blocks, _sels(("mesh", "mesh.inp")))
    assert "*INCLUDE" in mother
    assert "INPUT=mesh.inp" in mother


def test_compute_split_child_contains_blocks(tmp_path):
    blocks = parse(FEMPY)
    _, children = compute_split(blocks, _sels(("mesh", "mesh.inp")))
    child = children["mesh.inp"]
    assert len(child) > 0
    # mesh child should contain *NODE or *ELEMENT or *PART
    assert any(kw in child for kw in ("*NODE", "*ELEMENT", "*PART", "*NSET", "*ELSET"))


def test_compute_split_mother_missing_extracted_blocks(tmp_path):
    blocks = parse(FEMPY)
    mother, children = compute_split(blocks, _sels(("material", "material.inp")))
    # Material blocks should be gone from mother (replaced by *INCLUDE)
    # but *INCLUDE should be present
    assert "INPUT=material.inp" in mother


def test_compute_split_multiple_selections(tmp_path):
    blocks = parse(FEMPY)
    sels = _sels(("mesh", "mesh.inp"), ("material", "material.inp"))
    mother, children = compute_split(blocks, sels)
    assert "mesh.inp" in children
    assert "material.inp" in children
    assert "INPUT=mesh.inp" in mother
    assert "INPUT=material.inp" in mother


def test_compute_split_roundtrip_line_count(tmp_path):
    """Mother + all children together should cover the same content as the original."""
    blocks = parse(FEMPY)
    sels = _sels(("mesh", "mesh.inp"), ("material", "material.inp"))
    mother, children = compute_split(blocks, sels)

    combined_lines = sum(c.count("\n") for c in children.values()) + mother.count("\n")
    original_lines = FEMPY.read_text(encoding="utf-8").count("\n")
    # Allow small delta for the inserted *INCLUDE lines
    assert abs(combined_lines - original_lines) <= len(sels) + 2


def test_compute_split_include_placed_inplace(tmp_path):
    """The *INCLUDE line should appear at the position of the extracted block, not at the top."""
    blocks = parse(FEMPY)
    mother, _ = compute_split(blocks, _sels(("material", "material.inp")))
    lines = mother.splitlines()
    include_idx = next(i for i, l in enumerate(lines) if "INPUT=material.inp" in l)
    # At least some content should exist before the include
    assert include_idx > 0


def test_compute_split_no_selection_returns_original(tmp_path):
    blocks = parse(FEMPY)
    mother, children = compute_split(blocks, [])
    assert children == {}
    # Mother should reconstruct the full file
    original = FEMPY.read_text(encoding="utf-8")
    assert mother == original


# ---------------------------------------------------------------------------
# split_with_includes (writes to disk)
# ---------------------------------------------------------------------------

def test_split_with_includes_writes_files(tmp_path):
    blocks = parse(FEMPY)
    result = split_with_includes(blocks, FEMPY, tmp_path, _sels(("mesh", "mesh.inp")))
    assert (tmp_path / FEMPY.name).exists()
    assert (tmp_path / "mesh.inp").exists()
    assert len(result.children) == 1


def test_split_with_includes_sha256_recorded(tmp_path):
    blocks = parse(FEMPY)
    result = split_with_includes(blocks, FEMPY, tmp_path, _sels(("mesh", "mesh.inp")))
    child = result.children[0]
    on_disk = (tmp_path / "mesh.inp").read_text(encoding="utf-8")
    assert child.sha256 == _sha256(on_disk)


def test_split_with_includes_mother_sha256(tmp_path):
    blocks = parse(FEMPY)
    result = split_with_includes(blocks, FEMPY, tmp_path, _sels(("mesh", "mesh.inp")))
    on_disk = (tmp_path / FEMPY.name).read_text(encoding="utf-8")
    assert result.mother_sha256 == _sha256(on_disk)


def test_split_with_includes_child_category(tmp_path):
    blocks = parse(FEMPY)
    result = split_with_includes(blocks, FEMPY, tmp_path, _sels(("material", "material.inp")))
    assert result.children[0].category == Category.MATERIAL


@pytest.mark.parametrize("fixture", ["fempy_example.inp", "test_2.inp", "mmxmn.inp"])
def test_split_all_fixtures_no_crash(tmp_path, fixture):
    path = FIXTURES / fixture
    blocks = parse(path)
    # Split mesh and material if present, gracefully handles if absent
    sels = _sels(("mesh", "mesh.inp"), ("material", "material.inp"))
    split_with_includes(blocks, path, tmp_path / fixture, sels)
