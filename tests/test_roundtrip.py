from pathlib import Path

import pytest

from filefold.core.parser import emit_all, parse

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.parametrize("path", list(FIXTURES.glob("*.inp")), ids=lambda p: p.name)
def test_roundtrip(path: Path):
    original = path.read_text(encoding="utf-8", errors="surrogateescape")
    blocks = parse(path)
    reconstructed = emit_all(blocks)
    assert reconstructed == original
