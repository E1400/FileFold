from pathlib import Path

import pytest

from filefold.core.parser import emit_all, parse
from filefold.core.splitter import read_raw

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.parametrize("path", list(FIXTURES.glob("*.inp")), ids=lambda p: p.name)
def test_roundtrip(path: Path):
    # read_raw, not read_text: the parser preserves CRLF, so a universal-newline
    # read would compare LF-normalised text against CRLF output and always fail.
    original = read_raw(path)
    blocks = parse(path)
    reconstructed = emit_all(blocks)
    assert reconstructed == original


def test_block_line_counts_are_exact_even_without_the_text():
    """Block.n_own (kept also when keep_lines=False) gives exact per-block line counts;
    the split preview depends on it. line_start/line_end are not enough (leading comment
    lines of a block sit before its keyword line)."""
    from filefold.core.block import emit, line_count
    from filefold.core.parser import parse
    fixtures = Path(__file__).parent / "fixtures"
    for path in sorted(fixtures.glob("*.inp")):
        full, light = parse(path), parse(path, keep_lines=False)

        def walk(fb, lb):
            for f, l in zip(fb, lb, strict=True):
                assert len(f.raw_lines) == f.n_own == l.n_own, (path.name, f.keyword, f.line_start)
                assert line_count(l) == len(emit(f))
                walk(f.children, l.children)
        walk(full, light)
        assert sum(line_count(b) for b in light) == len(path.read_bytes().splitlines()), path.name
