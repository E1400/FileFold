"""Sub-split keys: which sub-file inside a category a block belongs to.

Two kinds of key share one namespace (they are stored in the manifest and used in
HTML ids, so every key is made of [a-z0-9_.-] only):

* static  — a fixed keyword group from CATEGORY_SUB_KEYWORDS: "nodes", "pairs", ...
* dynamic — one per name found in the deck: "material.steel", "step.load",
            "part.part-1", "etype.c3d8r"

A block can have several candidate keys (an *ELEMENT is both "etype.c3d8r" and
"elements"); the splitter takes the first one the user selected, so the more specific
dynamic key wins.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from .block import Block
from .keywords import CATEGORY_SUB_KEYWORDS, CATEGORY_SUB_OPTIONS, Category

_AXIS_LABEL = {"material": "Material", "step": "Step", "part": "Part", "etype": "Element type"}
_AXIS_FILE = {"material": "material", "step": "step", "part": "part", "etype": "elements"}


def slug(text: str) -> str:
    """Lowercase, filename- and id-safe form of a name taken from the deck."""
    return re.sub(r"[^A-Za-z0-9_-]+", "_", text.strip().strip('"')).strip("_").lower()


def _param(block: Block, key: str) -> str:
    value = block.params.get(key)
    return value.strip().strip('"') if value else ""


@dataclass
class KeyState:
    """Mutable routing state while walking one category's blocks in file order."""
    last_static: str | None = None     # static key of the previous block (for inherited options)
    last_material: str | None = None   # key of the most recent *MATERIAL (its options follow it)
    step_count: int = 0                # unnamed steps are keyed by position


def candidate_keys(category: Category, block: Block, state: KeyState) -> list[str]:
    """Keys `block` could be routed under, most specific first. Updates `state`.

    Call exactly once per block, in file order.
    """
    keys: list[str] = []

    if category is Category.MATERIAL:
        if block.keyword == "MATERIAL":
            name = slug(_param(block, "NAME"))
            state.last_material = f"material.{name}" if name else None
        if state.last_material:        # the head itself and every option after it
            keys.append(state.last_material)

    elif category is Category.STEP and block.keyword == "STEP":
        state.step_count += 1
        name = slug(_param(block, "NAME")) or str(state.step_count)
        keys.append(f"step.{name}")

    elif category is Category.MESH:
        if block.keyword == "PART":
            name = slug(_param(block, "NAME"))
            if name:
                keys.append(f"part.{name}")
        elif block.keyword == "ELEMENT":
            etype = slug(_param(block, "TYPE"))
            if etype:
                keys.append(f"etype.{etype}")

    static = CATEGORY_SUB_KEYWORDS.get(category, {}).get(block.keyword)
    if static is None and block.inherited:
        static = state.last_static     # unregistered option: goes where its parent went
    state.last_static = static
    if static:
        keys.append(static)
    return keys


@dataclass
class SubOption:
    sub_category: str
    label: str
    default_filename: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


def option_from_key(category: Category, key: str, name: str | None = None) -> SubOption:
    """Build the UI option for a key. `name` is the original (unslugged) name if known."""
    for opt in CATEGORY_SUB_OPTIONS.get(category, []):
        if opt["sub_category"] == key:
            return SubOption(key, opt["label"], opt["default_filename"])
    axis, _, tail = key.partition(".")
    shown = name or tail
    prefix = _AXIS_FILE.get(axis, axis)
    stem = tail if tail.startswith(prefix) else f"{prefix}-{tail}"   # "step-1", not "step-step-1"
    return SubOption(key, f"{_AXIS_LABEL.get(axis, axis.title())}: {shown}", f"{stem}.inp")


def _display_name(key: str, block: Block) -> str | None:
    axis = key.partition(".")[0]
    if axis == "etype":
        return _param(block, "TYPE")
    if axis in ("material", "part", "step"):
        return _param(block, "NAME") or None
    return None


def discover_options(category: Category, blocks: list[Block]) -> list[SubOption]:
    """Sub-split options that would actually produce a file for these blocks.

    Static groups come first (in UI order), then name-based ones in file order.
    Only descends into containers of the same category (e.g. *PART for mesh): blocks
    nested in a *STEP travel with the step and can never be split on their own.
    """
    state = KeyState()
    static_found: set[str] = set()
    dynamic: dict[str, SubOption] = {}

    def walk(bs: list[Block]) -> None:
        for b in bs:
            if b.category is not category:
                continue
            for key in candidate_keys(category, b, state):
                if "." in key:
                    dynamic.setdefault(key, option_from_key(category, key, _display_name(key, b)))
                else:
                    static_found.add(key)
            walk(b.children)

    walk(blocks)
    ordered = [option_from_key(category, o["sub_category"])
               for o in CATEGORY_SUB_OPTIONS.get(category, []) if o["sub_category"] in static_found]
    return ordered + list(dynamic.values())
