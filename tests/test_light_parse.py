"""parse(keep_lines=False): same block structure, without holding the deck's lines in memory."""
import hashlib
from pathlib import Path

import pytest

from filefold import service
from filefold.core.parser import parse
from filefold.core.splitter import _sha256, read_raw

FIXTURES = Path(__file__).parent / "fixtures"
DECKS = sorted(p.name for p in FIXTURES.glob("*.inp"))


def _shape(blocks):
    return [(b.keyword, b.category, b.params, b.line_start, b.line_end, b.inherited, b.context,
             _shape(b.children)) for b in blocks]


@pytest.mark.parametrize("deck", DECKS)
def test_light_parse_has_identical_structure(deck):
    assert _shape(parse(FIXTURES / deck, keep_lines=False)) == _shape(parse(FIXTURES / deck))


@pytest.mark.parametrize("deck", DECKS)
def test_light_parse_keeps_only_keyword_lines(deck):
    def walk(bs):
        for b in bs:
            yield b
            yield from walk(b.children)
    for b in walk(parse(FIXTURES / deck, keep_lines=False)):
        assert len(b.raw_lines) <= 3, (b.keyword, len(b.raw_lines))   # keyword line(s), never the data


@pytest.mark.parametrize("deck", DECKS)
def test_streamed_file_stats_match_the_in_memory_ones(deck):
    path = FIXTURES / deck
    sha, lines = service._file_stats(path)
    text = read_raw(path)
    assert sha == _sha256(text)
    assert lines == len(text.splitlines())


def test_file_stats_handle_crlf_and_missing_final_newline(tmp_path):
    p = tmp_path / "a.inp"
    p.write_bytes(b"*NODE\r\n1,0,0,0\r\n2,1,0,0")
    sha, lines = service._file_stats(p)
    assert lines == 3 and sha == hashlib.sha256(p.read_bytes()).hexdigest()
