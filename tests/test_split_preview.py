"""The live split preview (core/preview.py) must equal what the splitter really writes."""
import itertools
import random
from pathlib import Path

import pytest

from filefold.core.keywords import Category
from filefold.core.parser import parse
from filefold.core.preview import split_plan, split_preview
from filefold.core.splitter import SplitSelection, SubSplitSelection, compute_split
from filefold.core.subsplits import covered_parents, discover

FIXTURES = Path(__file__).parent / "fixtures"
DECKS = ["Job-1.inp", "mmxmn.inp", "fempy_example.inp", "test_2.inp"]


def actual_lines(blocks, sels) -> dict[str, int]:
    mother, children = compute_split(blocks, sels)
    out = {name: len(text.splitlines()) for name, text in children.items()}
    out["mother"] = len(mother.splitlines())
    return out


def payload(sels) -> list[dict]:
    return [{"category": s.category.value, "filename": s.filename,
             "sub_selections": [{"sub_category": ss.sub_category, "filename": ss.filename}
                                for ss in s.sub_selections]} for s in sels]


@pytest.mark.parametrize("deck", DECKS)
def test_preview_matches_the_splitter_for_many_choices(deck):
    path = FIXTURES / deck
    full = parse(path)
    plan = split_plan(parse(path, keep_lines=False))        # the UI's plan comes from a light parse
    cats = [c for c in Category if any(b.category is c for b in full) and c.value not in ("model", "unknown")]
    rng = random.Random(deck)
    cases = 0
    for r in range(1, len(cats) + 1):
        for combo, _variant in itertools.product(itertools.islice(itertools.combinations(cats, r), 6), range(4)):
            sels = []
            for cat in combo:
                opts, claims = discover(cat, [b for b in full if b.category is cat])
                keys = [o.sub_category for o in opts]
                ticked = set(rng.sample(keys, rng.randint(0, len(keys)))) if keys else set()
                ticked -= covered_parents(claims, ticked)    # the UI never sends a covered parent
                sels.append(SplitSelection(cat, f"{cat.value}.inp",
                                           [SubSplitSelection(k, f"{k}.sub.inp") for k in sorted(ticked)]))
            assert split_preview(plan, payload(sels)) == actual_lines(full, sels), (deck, payload(sels))
            cases += 1
    assert cases >= 4


def test_preview_of_no_split_is_just_the_mother():
    path = FIXTURES / "Job-1.inp"
    plan = split_plan(parse(path, keep_lines=False))
    assert split_preview(plan, []) == {"mother": len(path.read_bytes().splitlines())}
