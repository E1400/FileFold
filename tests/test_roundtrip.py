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
