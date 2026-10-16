"""Exact preview of a split: which files a set of choices makes, and how many lines each.

The UI shows this live while the user ticks categories and finer splits, so it must be
cheap and must not need the deck's text. `route_plan` records, once, how the splitter
(`compute_split` / `_route_sub`) walks each category's blocks: the candidate keys of every
block, its line count, and for containers their own lines and children. `split_preview`
then applies a set of choices to that plan. A property test holds it to `compute_split` on
every fixture; the browser has a line-for-line JavaScript mirror (`previewSplit` in core.js).
"""
from __future__ import annotations

from .block import Block, line_count
from .keywords import Category
from .parser import CONTAINER_KEYWORDS
from .subsplits import KeyState, candidate_keys


def route_plan(category: Category, blocks: list[Block]) -> list[dict]:
    """The splitter's routing tree for one category's top-level blocks.

    Each node: {"keys": [...most specific first], "lines": N} and, for a container with
    children, "own": its own lines and "children": [...]. Mirrors _route_sub's walk (keys are
    computed in file order with one KeyState, descending into every container).
    """
    state = KeyState()

    def node(b: Block) -> dict:
        n = {"keys": candidate_keys(category, b, state), "lines": line_count(b)}
        if b.keyword in CONTAINER_KEYWORDS and b.children:
            n["own"] = b.n_own
            n["children"] = [node(c) for c in b.children]
        return n

    return [node(b) for b in blocks if b.category is category]


def split_plan(blocks: list[Block]) -> dict:
    """Everything the preview needs for one deck: total lines and a plan per category."""
    cats = []
    for b in blocks:
        if b.category not in cats:
            cats.append(b.category)
    return {"total_lines": sum(line_count(b) for b in blocks),
            "categories": {c.value: route_plan(c, blocks) for c in cats}}


def category_lines(nodes: list[dict]) -> int:
    return sum(n["lines"] for n in nodes)


def split_category(nodes: list[dict], filename: str, subs: dict[str, str]) -> dict[str, int]:
    """Lines per file for one extracted category. subs: sub key -> filename (effective keys).

    The category file gets every block no ticked key claims (a container keeps its own
    lines and hands its children on) plus one *INCLUDE line per sub-file that receives a
    block; files that receive nothing are not made (and not listed).
    """
    out: dict[str, int] = {filename: 0}

    def route(n: dict) -> None:
        key = next((k for k in n["keys"] if k in subs), None)
        if key is not None:
            target = subs[key]
            if target not in out:
                out[target] = 0
                out[filename] += 1                      # its *INCLUDE line in the category file
            out[target] += n["lines"]
        elif "children" in n:
            out[filename] += n["own"]
            for c in n["children"]:
                route(c)
        else:
            out[filename] += n["lines"]

    if subs:
        for n in nodes:
            route(n)
    else:
        out[filename] = category_lines(nodes)
    return {f: k for f, k in out.items() if k}


def split_preview(plan: dict, selections: list[dict], mother: str = "mother") -> dict[str, int]:
    """Lines per file (mother included under `mother`) for create-style selections:
    [{"category", "filename", "sub_selections": [{"sub_category", "filename"}]}]."""
    files: dict[str, int] = {}
    moved = 0
    for sel in selections:
        nodes = plan["categories"].get(sel["category"], [])
        if not nodes:
            continue
        subs = {ss["sub_category"]: ss["filename"] for ss in sel.get("sub_selections", [])}
        files.update(split_category(nodes, sel["filename"], subs))
        moved += category_lines(nodes) - 1                   # one *INCLUDE stays behind
    files[mother] = plan["total_lines"] - moved
    return files
