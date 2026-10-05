"""Keyword registry, option inheritance, continuation lines, and context tracking."""
from pathlib import Path

import pytest

from filefold.core.keywords import Category, categorize
from filefold.core.parser import emit_all, parse
from filefold.core.splitter import SplitSelection, compute_split, read_raw
from filefold.core.tokenizer import keyword_of, parse_params

FIXTURES = Path(__file__).parent / "fixtures"


def _parse_text(tmp_path: Path, text: str):
    p = tmp_path / "m.inp"
    p.write_text(text, newline="")
    blocks = parse(p)
    assert emit_all(blocks) == text  # every case below must round-trip byte-exact
    return blocks


def _walk(blocks):
    for b in blocks:
        yield b
        yield from _walk(b.children)


# --- registry -------------------------------------------------------------

@pytest.mark.parametrize("kw,cat", [
    ("*elastic", Category.MATERIAL),
    ("Rigid  Body", Category.CONSTRAINT),
    ("TIE", Category.CONSTRAINT),
    ("INITIAL CONDITIONS", Category.INITIAL),
    ("CONTACT", Category.CONTACT),
    ("SURFACE BEHAVIOR", Category.CONTACT),
    ("HYPERFOAM", Category.MATERIAL),          # prefix rule
    ("CONNECTOR ELASTICITY", Category.SECTION),  # prefix rule
    ("CONTACT OUTPUT", Category.OUTPUT),         # explicit entry beats the CONTACT prefix
    ("MADE UP KEYWORD", Category.UNKNOWN),
])
def test_categorize(kw, cat):
    assert categorize(kw) is cat


def test_fixtures_have_no_unknown_blocks():
    for path in FIXTURES.glob("*.inp"):
        unknown = {b.keyword for b in _walk(parse(path)) if b.category is Category.UNKNOWN}
        assert not unknown, f"{path.name}: {unknown}"


# --- option inheritance ---------------------------------------------------

DECK_WITH_UNREGISTERED_OPTION = (
    "*NODE\n1, 0, 0, 0\n"
    "*MATERIAL, NAME=steel\n"
    "*ELASTIC\n210000., 0.3\n"
    "*FUTURE MATERIAL OPTION, X=1\n1., 2.\n"
    "*MATERIAL, NAME=alu\n"
    "*ELASTIC\n70000., 0.33\n"
    "*BOUNDARY\n1, 1, 3\n"
)


def test_unregistered_keyword_inherits_previous_category(tmp_path):
    blocks = _parse_text(tmp_path, DECK_WITH_UNREGISTERED_OPTION)
    opt = next(b for b in blocks if b.keyword == "FUTURE MATERIAL OPTION")
    assert opt.category is Category.MATERIAL
    assert opt.inherited is True
    assert not any(b.inherited for b in blocks if b.keyword != "FUTURE MATERIAL OPTION")


def test_unregistered_option_stays_next_to_parent_in_split(tmp_path):
    """The bug this guards: an unmapped option used to stay in the mother file while
    its *MATERIAL moved to the child, so the option ended up under the wrong material."""
    blocks = _parse_text(tmp_path, DECK_WITH_UNREGISTERED_OPTION)
    mother, children = compute_split(
        blocks, [SplitSelection(Category.MATERIAL, "materials.inp")]
    )
    assert "FUTURE MATERIAL OPTION" not in mother
    steel, _, alu = children["materials.inp"].partition("*MATERIAL, NAME=alu")
    assert "FUTURE MATERIAL OPTION" in steel and "FUTURE MATERIAL OPTION" not in alu


def test_leading_unknown_keyword_stays_unknown(tmp_path):
    blocks = _parse_text(tmp_path, "*MADE UP\n1\n*NODE\n1,0,0,0\n")
    assert blocks[0].category is Category.UNKNOWN and not blocks[0].inherited


# --- keyword-line parsing -------------------------------------------------

def test_keyword_whitespace_normalised():
    assert keyword_of("*solid   section , elset=a") == "SOLID SECTION"


def test_quoted_param_with_comma():
    assert parse_params('*STEP, NAME="a, b", NLGEOM') == {"NAME": '"a, b"', "NLGEOM": None}


def test_continuation_lines_merge_params(tmp_path):
    text = (
        "*ELEMENT, TYPE=C3D8R,\n"
        "   ELSET=bricks,\n"
        "   INPUT=extra.inp\n"
        "1, 1, 2, 3, 4, 5, 6, 7, 8\n"
        "*NSET, NSET=all\n1, 2\n"
    )
    blocks = _parse_text(tmp_path, text)
    assert blocks[0].params == {"TYPE": "C3D8R", "ELSET": "bricks", "INPUT": "extra.inp"}
    assert blocks[1].params == {"NSET": "all"}  # continuation must not leak into the next block


def test_step_name_on_continuation_line(tmp_path):
    text = "*STEP,\n  NAME=load, NLGEOM\n*STATIC\n1., 1.\n*END STEP\n"
    blocks = _parse_text(tmp_path, text)
    assert blocks[0].params["NAME"] == "load"
    assert [c.keyword for c in blocks[0].children] == ["STATIC", "END STEP"]


# --- context --------------------------------------------------------------

def test_block_context_tracks_containers(tmp_path):
    text = (
        "*PART, NAME=p1\n*NODE\n1,0,0,0\n*END PART\n"
        "*ASSEMBLY, NAME=a\n*INSTANCE, NAME=i, PART=p1\n*END INSTANCE\n*END ASSEMBLY\n"
        "*MATERIAL, NAME=m\n"
    )
    blocks = _parse_text(tmp_path, text)
    by_kw = {b.keyword: b for b in _walk(blocks)}
    assert by_kw["NODE"].context == ("PART",)
    assert by_kw["INSTANCE"].context == ("ASSEMBLY",)
    assert by_kw["MATERIAL"].context == ()


# --- the full-file fixtures still round-trip with the new parser ----------

@pytest.mark.parametrize("path", list(FIXTURES.glob("*.inp")), ids=lambda p: p.name)
def test_fixture_roundtrip_with_registry(path):
    assert emit_all(parse(path)) == read_raw(path)


# --- keywords named in the Abaqus Release Notes -----------------------------

def test_every_keyword_from_the_release_notes_is_recognised():
    lines = (FIXTURES / "abaqus_release_notes_keywords.txt").read_text().splitlines()
    names = [l for l in lines if l and not l.startswith("#")]
    assert len(names) > 100
    still_unknown = [n for n in names if categorize(n) is Category.UNKNOWN]
    assert not still_unknown, still_unknown


@pytest.mark.parametrize("kw,cat", [
    ("PAPERBOARD HARDENING", Category.MATERIAL),
    ("CURE KINETICS", Category.MATERIAL),
    ("SUBMODEL CUT", Category.LOADS),
    ("COUPLED TEMPERATURE-DISPLACEMENT", Category.STEP),
    ("SURFACE PROPERTY ASSIGNMENT", Category.CONTACT),
    ("CONTOUR INTEGRAL", Category.OUTPUT),
])
def test_release_notes_keyword_categories(kw, cat):
    assert categorize(kw) is cat
