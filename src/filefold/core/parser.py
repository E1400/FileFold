from __future__ import annotations

from pathlib import Path

from .block import Block
from .keywords import Category, categorize
from .tokenizer import LineType, ends_with_continuation, keyword_of, parse_params, tokenize

# Keywords that open a nesting scope
CONTAINER_KEYWORDS: frozenset[str] = frozenset({"STEP", "PART", "ASSEMBLY", "INSTANCE"})

# Maps each closing keyword to the container it closes
END_KEYWORD_MAP: dict[str, str] = {
    "END STEP": "STEP",
    "END PART": "PART",
    "END ASSEMBLY": "ASSEMBLY",
    "END INSTANCE": "INSTANCE",
}


def parse(path: Path, keep_lines: bool = True) -> list[Block]:
    """Parse an Abaqus .inp file into a list of top-level Blocks.

    Nesting: *STEP ... *END STEP blocks carry their children in Block.children.
    All other blocks are flat. Comments, blanks, and data lines are stored
    verbatim in Block.raw_lines so round-trip is byte-exact.

    A keyword the registry does not know inherits the category of the block before
    it (Block.inherited=True): in Abaqus an unrecognised keyword is almost always an
    option of the keyword above it, so it must travel with its parent when split.
    A keyword line ending in a comma continues onto the following line(s); their
    parameters are merged into Block.params.

    keep_lines=False is for read-only inspection of very large decks: it keeps the
    structure (keywords, params, categories, line ranges, context) but drops the data
    lines, so memory no longer scales with the file. Such blocks cannot be emitted.
    """
    top: list[Block] = []
    stack: list[Block] = []   # nesting stack; stack[-1] is the open container
    current: Block | None = None
    orphans: list[str] = []   # lines before the very first keyword
    last_category = Category.UNKNOWN          # category of the most recent block
    cont_block: Block | None = None           # keyword line still being continued
    cont_text = ""                            # its keyword line text so far

    def resolve(kw: str) -> tuple[Category, bool]:
        """Category for kw, inheriting from the previous block if unregistered."""
        cat = categorize(kw)
        if cat is Category.UNKNOWN and last_category is not Category.UNKNOWN:
            return last_category, True
        return cat, False

    def context() -> tuple[str, ...]:
        return tuple(c.keyword for c in stack)

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
        if cont_block is not None:
            if tok.kind == LineType.DATA:
                # Continuation of a wrapped keyword line: it is stored like any other
                # trailing line below; here we only fold its parameters in.
                cont_text += tok.text
                cont_block.params = parse_params(cont_text)
                if not ends_with_continuation(tok.text):
                    cont_block = None
            elif tok.kind == LineType.KEYWORD:
                cont_block = None

        # if a new keyword arrives, commit what was in progress and start new block
        if tok.kind != LineType.KEYWORD: 
            if current is not None:
                # Trailing data/comment/blank on the in-progress block
                if keep_lines:
                    current.raw_lines.append(tok.text)
                current.line_end = tok.line_no
            elif stack:
                container = stack[-1]
                if not container.children:
                    # Before first child — safe to attach to container's own lines
                    # (e.g. the step-title data line right after *STEP)
                    if keep_lines:
                        container.raw_lines.append(tok.text)
                    container.line_end = tok.line_no
                else:
                    # After a child container was closed (e.g. after *END INSTANCE).
                    # Attach to the deepest last child so emit() outputs it in the
                    # correct position — after the closed child, not before it.
                    last = container.children[-1]
                    while last.children:
                        last = last.children[-1]
                    if keep_lines:
                        last.raw_lines.append(tok.text)
                    last.line_end = tok.line_no
            else:
                if keep_lines:
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
                context=context(),
            )
            last_category = end_block.category
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
                context=context(),
            )
            last_category = container.category
            if ends_with_continuation(tok.text):
                cont_block, cont_text = container, tok.text
            dest().append(container)
            stack.append(container)
            # current stays None; pre-first-child lines attach to container.raw_lines

        else:
            commit()
            leading = list(orphans)
            orphans.clear()
            cat, inherited = resolve(kw)
            current = Block(
                keyword=kw,
                params=parse_params(tok.text),
                raw_lines=leading + [tok.text],
                category=cat,
                line_start=tok.line_no,
                line_end=tok.line_no,
                inherited=inherited,
                context=context(),
            )
            last_category = cat
            if ends_with_continuation(tok.text):
                cont_block, cont_text = current, tok.text

    commit()
    return top


def emit_all(blocks: list[Block]) -> str:
    """Reconstruct the full file content from a list of top-level blocks."""
    from .block import emit
    parts: list[str] = []
    for block in blocks:
        parts.extend(emit(block))
    return "".join(parts)
