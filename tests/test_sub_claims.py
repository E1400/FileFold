"""An option is offered only if it would produce a file: claims vs the real splitter."""
import itertools
from pathlib import Path

import pytest

from filefold.core.keywords import Category
from filefold.core.parser import parse
from filefold.core.splitter import SplitSelection, SubSplitSelection, compute_split
from filefold.core.subsplits import discover, live_keys

FIXTURES = Path(__file__).parent / "fixtures"


def test_live_keys_follows_the_splitters_precedence():
    claims = [["etype.a", "elements"], ["etype.b", "elements"], ["nodes"]]
    assert live_keys(claims, {"elements"}) == {"elements"}
    assert live_keys(claims, {"etype.a", "elements"}) == {"etype.a", "elements"}  # b still falls to elements
    assert live_keys(claims, {"etype.a", "etype.b", "elements"}) == {"etype.a", "etype.b"}  # elements empty
    assert live_keys([["part.x", "nodes"]], {"part.x", "nodes"}) == {"part.x"}


def _subsets(keys: list[str]):
    yield set()
    for k in keys:
        yield {k}
    yield set(keys)
    for pair in itertools.islice(itertools.combinations(keys, 2), 25):
        yield set(pair)
    for k in keys:                       # everything except one
        yield set(keys) - {k}


@pytest.mark.parametrize("deck", ["Job-1.inp", "test_2.inp", "mmxmn.inp", "fempy_example.inp"])
def test_live_keys_match_the_files_the_splitter_actually_writes(deck):
    blocks = parse(FIXTURES / deck)
    checked = 0
    for cat in Category:
        options, claims = discover(cat, [b for b in blocks if b.category is cat])
        if not options:
            continue
        keys = [o.sub_category for o in options]
        filename = {k: f"{k}.out" for k in keys}
        for ticked in _subsets(keys):
            sel = SplitSelection(cat, "parent.out", [SubSplitSelection(k, filename[k]) for k in sorted(ticked)])
            _, files = compute_split(blocks, [sel])
            produced = {k for k in keys if filename[k] in files}
            assert produced == live_keys(claims, ticked), (deck, cat.value, sorted(ticked))
            checked += 1
    assert checked > 5
