"""Sub-splits for contact, constraint and loads categories."""
from pathlib import Path

from filefold.core.keywords import CATEGORY_SUB_KEYWORDS, CATEGORY_SUB_OPTIONS, Category
from filefold.core.parser import parse
from filefold.core.splitter import SplitSelection, SubSplitSelection, compute_split

DECK = (
    "*SURFACE INTERACTION, NAME=fric\n1.,\n"
    "*FRICTION\n0.3,\n"
    "*NEW CONTACT OPTION\n9.\n"
    "*CONTACT PAIR, INTERACTION=fric\nslave, master\n"
    "*TIE, NAME=t1\nsa, sb\n"
    "*RIGID BODY, REF NODE=1, ELSET=e\n"
    "*AMPLITUDE, NAME=ramp\n0., 0., 1., 1.\n"
    "*BOUNDARY\n1, 1, 3\n"
    "*CLOAD\n2, 1, 5.\n"
)


def _parse(tmp_path: Path):
    p = tmp_path / "m.inp"
    p.write_text(DECK)
    return parse(p)


def test_every_sub_option_has_keywords_and_vice_versa():
    for cat, opts in CATEGORY_SUB_OPTIONS.items():
        mapped = set(CATEGORY_SUB_KEYWORDS[cat].values())
        assert {o["sub_category"] for o in opts} == mapped, cat


def test_contact_sub_split_keeps_options_with_parent(tmp_path):
    sel = SplitSelection(Category.CONTACT, "contact.inp", [
        SubSplitSelection("interactions", "contact-interactions.inp"),
        SubSplitSelection("pairs", "contact-pairs.inp"),
    ])
    mother, files = compute_split(_parse(tmp_path), [sel])
    inter = files["contact-interactions.inp"]
    assert "*FRICTION" in inter and "*NEW CONTACT OPTION" in inter  # inherited option follows parent
    assert "*NEW CONTACT OPTION" not in files["contact-pairs.inp"]
    assert "*CONTACT PAIR" in files["contact-pairs.inp"]
    assert files["contact.inp"].count("*INCLUDE") == 2
    assert "*SURFACE INTERACTION" not in mother


def test_constraints_and_loads_split_into_own_files(tmp_path):
    sels = [
        SplitSelection(Category.CONSTRAINT, "constraints.inp",
                       [SubSplitSelection("ties", "c-ties.inp")]),
        SplitSelection(Category.LOADS, "loads.inp", [
            SubSplitSelection("amplitudes", "l-amp.inp"),
            SubSplitSelection("boundary", "l-bc.inp"),
        ]),
    ]
    _, files = compute_split(_parse(tmp_path), sels)
    assert "*TIE" in files["c-ties.inp"] and "*RIGID BODY" in files["constraints.inp"]
    assert "*AMPLITUDE" in files["l-amp.inp"] and "*BOUNDARY" in files["l-bc.inp"]
    assert "*CLOAD" in files["loads.inp"]  # sub-category not selected stays in the parent child
