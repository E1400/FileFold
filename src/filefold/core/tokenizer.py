from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import Iterator


class LineType(Enum): # all possible contents of .inp file
    KEYWORD = auto()  # single * line: *NODE, *STEP, *SOLID SECTION, ...
    COMMENT = auto()  # double ** line
    BLANK = auto()    # empty or whitespace only
    DATA = auto()     # node coords, element connectivity, set members, etc.


@dataclass
class TokenizedLine: # value/positons of LineType
    line_no: int  # 1-indexed
    text: str     # verbatim, including original line ending
    kind: LineType


def classify(line: str) -> LineType: # determines LineType
    s = line.lstrip()
    if not s:
        return LineType.BLANK # BLANK if LineType is a line skip (important for byte-preservation)
    if s.startswith("**"):
        return LineType.COMMENT
    if s.startswith("*"):
        return LineType.KEYWORD
    return LineType.DATA


def tokenize(path: Path) -> Iterator[TokenizedLine]:
    """Yield one TokenizedLine per line, preserving exact text and line endings."""
    with open(path, newline="") as fh:
        for line_no, text in enumerate(fh, start=1):
            yield TokenizedLine(line_no=line_no, text=text, kind=classify(text))


def keyword_of(line: str) -> str:
    """Extract normalized keyword name from a keyword line.

    '*solid section,elset=box' -> 'SOLID SECTION'
    """
    return line.lstrip().lstrip("*").partition(",")[0].strip().upper() # Assigns keywords and handles commas


def parse_params(line: str) -> dict[str, str | None]:
    """Parse key=value pairs after the keyword name on a keyword line.

    '*step,inc=100,nlgeom,name=foo' -> {'INC': '100', 'NLGEOM': None, 'NAME': 'foo'}

    Bare flags (no =) get None as their value.
    """
    parts = line.strip().split(",")
    params: dict[str, str | None] = {}
    for part in parts[1:]:  # parts[0] is the *KEYWORD itself, parts[1:] are parameters
        part = part.strip()
        if not part:
            continue
        if "=" in part:
            key, _, val = part.partition("=")
            params[key.strip().upper()] = val.strip()
        else:
            params[part.upper()] = None
    return params
