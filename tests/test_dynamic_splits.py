"""Name-based sub-splits: by material, step, part, and element type."""
import re
from pathlib import Path

from filefold.core.keywords import Category
from filefold.core.parser import parse
from filefold.core.splitter import SplitSelection, SubSplitSelection, compute_split
from filefold.core.subsplits import discover_options, slug

DECK = (
    "*HEADING\nt\n"
    "*PART, NAME=Bracket\n"
    "*NODE\n1, 0, 0, 0\n"
    "*ELEMENT, TYPE=C3D8R, ELSET=a\n1, 1, 2, 3, 4, 5, 6, 7, 8\n"
    "*ELEMENT, TYPE=S4R\n2, 1, 2, 3, 4\n"
    "*END PART\n"
    "*PART, NAME=Plate\n*NODE\n1, 0, 0, 0\n*END PART\n"
    "*MATERIAL, NAME=Steel\n*ELASTIC\n210000., 0.3\n*FUTURE OPTION\n1.\n"
    "*MATERIAL, NAME=\"Alu 6061\"\n*ELASTIC\n70000., 0.33\n*DENSITY\n2.7e-9\n"
    "*STEP, NAME=Load\n*STATIC\n1., 1.\n*END STEP\n"
    "*STEP\n*STATIC\n1., 1.\n*END STEP\n"
)


def _blocks(tmp_path: Path):
    p = tmp_path / "m.inp"
    p.write_text(DECK)
    return parse(p)


def _expand(text: str, files: dict[str, str]) -> str:
    return re.sub(r"^\*INCLUDE, INPUT=(\S+)\n", lambda m: _expand(files[m.group(1)], files), text, flags=re.M)


def _split(blocks, cat, subs, parent="p.inp"):
    sel = SplitSelection(cat, parent, [SubSplitSelection(k, f"{k}.inp") for k in subs])
    mother, files = compute_split(blocks, [sel])
    return mother, files


def test_slug():
    assert slug('"Alu 6061"') == "alu_6061"
    assert slug("Part-1") == "part-1"


def test_discovery_lists_names_present_in_the_deck(tmp_path):
    b = _blocks(tmp_path)
    mats = [o.sub_category for o in discover_options(Category.MATERIAL, b)]
    assert mats == ["material.steel", "material.alu_6061"]
    assert discover_options(Category.MATERIAL, b)[1].label == "Material: Alu 6061"
    assert [o.sub_category for o in discover_options(Category.STEP, b)] == ["step.load", "step.2"]
    mesh = [o.sub_category for o in discover_options(Category.MESH, b)]
    assert {"part.bracket", "part.plate", "etype.c3d8r", "etype.s4r", "nodes", "elements"} <= set(mesh)
    assert mesh.index("nodes") < mesh.index("part.bracket")  # static options first


def test_discovery_ignores_blocks_nested_in_other_categories(tmp_path):
    b = _blocks(tmp_path)
    assert not any(o.sub_category == "boundary" for o in discover_options(Category.LOADS, b))


def test_material_split_keeps_each_materials_options_together(tmp_path):
    mother, files = _split(_blocks(tmp_path), Category.MATERIAL, ["material.steel"])
    steel = files["material.steel.inp"]
    assert "*FUTURE OPTION" in steel and "*ELASTIC\n210000" in steel
    assert "Alu" not in steel
    assert "Alu 6061" in files["p.inp"] and "*DENSITY" in files["p.inp"]
    assert files["p.inp"].count("*INCLUDE") == 1


def test_all_materials_split_and_roundtrip(tmp_path):
    b = _blocks(tmp_path)
    mother, files = _split(b, Category.MATERIAL, ["material.steel", "material.alu_6061"])
    assert "Steel" in files["material.steel.inp"] and "Alu" in files["material.alu_6061.inp"]
    assert _expand(mother, files) == DECK


def test_step_split_by_name_and_position(tmp_path):
    b = _blocks(tmp_path)
    mother, files = _split(b, Category.STEP, ["step.load", "step.2"])
    assert files["step.load.inp"].startswith("*STEP, NAME=Load") and "*END STEP" in files["step.load.inp"]
    assert files["step.2.inp"].startswith("*STEP\n")
    assert _expand(mother, files) == DECK


def test_part_split_moves_whole_container(tmp_path):
    b = _blocks(tmp_path)
    mother, files = _split(b, Category.MESH, ["part.bracket"])
    part = files["part.bracket.inp"]
    assert part.startswith("*PART, NAME=Bracket") and part.rstrip().endswith("*END PART")
    assert "TYPE=S4R" in part
    assert "NAME=Plate" in files["p.inp"] and "NAME=Bracket" not in files["p.inp"]
    assert _expand(mother, files) == DECK


def test_element_type_split_inside_a_part_and_precedence_over_static(tmp_path):
    b = _blocks(tmp_path)
    # etype.s4r wins over the static "elements" group for the S4R block; the C3D8R
    # block has no selected etype so falls back to "elements".
    mother, files = _split(b, Category.MESH, ["etype.s4r", "elements"])
    assert "TYPE=S4R" in files["etype.s4r.inp"] and "C3D8R" not in files["etype.s4r.inp"]
    assert "TYPE=C3D8R" in files["elements.inp"] and "S4R" not in files["elements.inp"]
    assert "*PART, NAME=Bracket" in files["p.inp"]  # container header stays in the parent
    assert _expand(mother, files) == DECK


def test_unselected_names_stay_in_parent(tmp_path):
    _, files = _split(_blocks(tmp_path), Category.STEP, ["step.load"])
    assert "step.2.inp" not in files
    assert files["p.inp"].count("*STEP") == 1


def test_default_filenames_do_not_repeat_the_axis_word():
    from filefold.core.subsplits import option_from_key
    assert option_from_key(Category.STEP, "step.step-1").default_filename == "step-1.inp"
    assert option_from_key(Category.STEP, "step.2").default_filename == "step-2.inp"
    assert option_from_key(Category.MATERIAL, "material.steel").default_filename == "material-steel.inp"
    assert option_from_key(Category.MESH, "part.part-1").default_filename == "part-1.inp"
    assert option_from_key(Category.MESH, "etype.c3d8r").default_filename == "elements-c3d8r.inp"
