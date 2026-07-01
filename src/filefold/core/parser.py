from __future__ import annotations

from pathlib import Path

from .block import Block
from .keywords import categorize
from .tokenizer import LineType, keyword_of, parse_params, tokenize

# Keywords that open a nesting scope
CONTAINER_KEYWORDS: frozenset[str] = frozenset({"STEP", "PART", "ASSEMBLY", "INSTANCE"})

# Maps each closing keyword to the container it closes
END_KEYWORD_MAP: dict[str, str] = {
    "END STEP": "STEP",
    "END PART": "PART",
    "END ASSEMBLY": "ASSEMBLY",
    "END INSTANCE": "INSTANCE",
}


def parse(path: Path) -> list[Block]:
    """Parse an Abaqus .inp file into a list of top-level Blocks.

    Nesting: *STEP ... *END STEP blocks carry their children in Block.children.
    All other blocks are flat. Comments, blanks, and data lines are stored
    verbatim in Block.raw_lines so round-trip is byte-exact.
    """
    top: list[Block] = []
    stack: list[Block] = []   # nesting stack; stack[-1] is the open container
    current: Block | None = None
    orphans: list[str] = []   # lines before the very first keyword

    def dest() -> list[Block]: 
        # looks for where the next block should be placed
        # dynamimc lookup, reflects where the parser is at time of call
        return stack[-1].children if stack else top

    def commit() -> None: # finalizes black and puts it in correct spot
        nonlocal current # makes current global
        if current is not None:
            dest().append(current)
            current = None

    for tok in tokenize(path):
        # if a new keyword arrives, commit what was in progress and start new block
        if tok.kind != LineType.KEYWORD: 
            if current is not None:
                # Trailing data/comment/blank on the in-progress block
                current.raw_lines.append(tok.text)
                current.line_end = tok.line_no
            elif stack:
                # Right after a container keyword and before its first child
                # (e.g. the step-title data line that follows *STEP)
                stack[-1].raw_lines.append(tok.text)
                stack[-1].line_end = tok.line_no
            else:
                orphans.append(tok.text)
            continue

        kw = keyword_of(tok.text)

        # if an end step arrives, commit the child and close container
        if kw in END_KEYWORD_MAP:
            commit()
            end_block = Block(
                keyword=kw,
                params=parse_params(tok.text),
                raw_lines=[tok.text],
                category=categorize(kw),
                line_start=tok.line_no,
                line_end=tok.line_no,
            )
            if stack:
                stack[-1].children.append(end_block)
                stack[-1].line_end = tok.line_no
                stack.pop()
            else:
                top.append(end_block)

        elif kw in CONTAINER_KEYWORDS:
            commit()
            leading = list(orphans)
            orphans.clear()
            container = Block(
                keyword=kw,
                params=parse_params(tok.text),
                raw_lines=leading + [tok.text],
                category=categorize(kw),
                line_start=tok.line_no,
                line_end=tok.line_no,
            )
            dest().append(container)
            stack.append(container)
            # current stays None; pre-first-child lines attach to container.raw_lines

        else:
            commit()
            leading = list(orphans)
            orphans.clear()
            current = Block(
                keyword=kw,
                params=parse_params(tok.text),
                raw_lines=leading + [tok.text],
                category=categorize(kw),
                line_start=tok.line_no,
                line_end=tok.line_no,
            )

    commit()
    return top


def emit_all(blocks: list[Block]) -> str:
    """Reconstruct the full file content from a list of top-level blocks."""
    from .block import emit
    parts: list[str] = []
    for block in blocks:
        parts.extend(emit(block))
    return "".join(parts)
