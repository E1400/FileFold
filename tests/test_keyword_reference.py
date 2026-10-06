"""The keyword registry against the Abaqus Keywords Reference (core/keyword_reference.py)."""
from pathlib import Path

import pytest

from filefold.core import keywords as K
from filefold.core.keyword_reference import FACTS
from filefold.core.keywords import Category, categorize

FIXTURES = Path(__file__).parent / "fixtures"
RELEASE_NOTES = {
    l.strip() for l in (FIXTURES / "abaqus_release_notes_keywords.txt").read_text().splitlines()
    if l.strip() and not l.startswith("#")
}

# Reference keywords the rules cannot place (several levels at once, no documented parent).
# They fall back to inheriting the previous block's category. Keep this list short and
# justified; a new entry here should be a conscious decision.
LEFT_TO_INHERIT = {
    "ASSEMBLY", "END ASSEMBLY",  # structural, handled by the parser as containers
}


def test_reference_covers_the_whole_guide():
    assert len(FACTS) >= 500
    types, levels, parents = FACTS["ELGEN"]
    assert types == ("model",) and set(levels) == {"part", "part instance"}


def test_every_registered_keyword_exists_in_abaqus():
    """Catches invented or misspelled names (this found BUOYANCY, STEP CONTROLS, ...)."""
    unknown = sorted(k for k in K.KEYWORD_CATEGORIES if k not in FACTS and k not in RELEASE_NOTES)
    assert not unknown, unknown


@pytest.mark.parametrize("name", ["BUOYANCY", "STEP CONTROLS", "DYNAMIC EXPLICIT", "COUPLED TEMP-DISPLACEMENT"])
def test_names_that_are_not_keywords_are_gone(name):
    assert name not in K.KEYWORD_CATEGORIES


def test_corrected_entries():
    assert categorize("COUPLED TEMPERATURE-DISPLACEMENT") is Category.STEP
    assert categorize("FIELD") is Category.LOADS          # *FIELD is a step-level predefined field


def test_every_reference_keyword_gets_a_category():
    uncategorised = sorted(k for k in FACTS if categorize(k) is Category.UNKNOWN and k not in LEFT_TO_INHERIT)
    assert not uncategorised, uncategorised


def test_documented_option_follows_its_documented_parent():
    """An option the reference ties to a parent keyword lands in the parent's category."""
    checked = 0
    for name, (_t, _l, parents) in FACTS.items():
        if name in K.KEYWORD_CATEGORIES or not parents:
            continue
        parent_cats = {categorize(p) for p in parents} - {Category.UNKNOWN}
        if len(parent_cats) == 1 and name not in K._REFERENCE_OVERRIDE_NAMES:
            assert categorize(name) is next(iter(parent_cats)), (name, parents)
            checked += 1
    assert checked > 30


def test_history_only_step_keywords_are_step_level_things():
    for name, (types, levels, _p) in FACTS.items():
        if types == ("history",) and levels == ("step",) and name not in K.KEYWORD_CATEGORIES:
            assert categorize(name) in {Category.STEP, Category.OUTPUT, Category.LOADS, Category.CONTACT, Category.MODEL}, name


@pytest.mark.parametrize("kw,cat", [
    ("ACOUSTIC MEDIUM", Category.MATERIAL),          # documented option of *MATERIAL
    ("ANNEAL TEMPERATURE", Category.MATERIAL),
    ("CRUSHABLE FOAM", Category.MATERIAL),
    ("AXIAL", Category.SECTION),                     # option of *BEAM GENERAL SECTION
    ("BLOCKAGE", Category.CONTACT),                  # option of *SURFACE INTERACTION
    ("FASTENER PROPERTY", Category.CONSTRAINT),
    ("SLIDE LINE", Category.CONTACT),
    ("RIGID SURFACE", Category.MESH),
    ("USER ELEMENT", Category.SECTION),
    ("WIND", Category.LOADS),
    ("DSFLUX", Category.LOADS),
    ("FILE OUTPUT", Category.OUTPUT),
    ("SUBSTRUCTURE DIRECTORY", Category.MODEL),      # stays in the mother file
    ("MAP SOLUTION", Category.INITIAL),
])
def test_reference_keyword_categories(kw, cat):
    assert categorize(kw) is cat
