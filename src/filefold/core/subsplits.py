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

# Axes the splitter still understands (so existing workspaces keep working) but that the
# menus do not offer: element type is finer than most people want to manage.
HIDDEN_AXES = frozenset({"etype"})

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


def discover(category: Category, blocks: list[Block]) -> tuple[list[SubOption], list[list[str]]]:
    """Sub-split options for these blocks, and which options claim which blocks.

    options: the options that exist in the deck. Static groups first (in UI order), then
             name-based ones in file order.
    claims:  one entry per distinct kind of block: the keys that could receive it, in the
             order the splitter tries them (an enclosing container's key first, then the
             block's own name-based key, then its static group). Whichever of these keys
             is ticked first gets the block, so an option that is first for no block
             under the current ticks would produce an empty file. The UI uses this to
             disable such options instead of offering a checkbox that creates nothing.

    Only descends into containers of the same category (e.g. *PART for mesh): blocks
    nested in a *STEP travel with the step and can never be split on their own.
    """
    state = KeyState()
    static_found: set[str] = set()
    dynamic: dict[str, SubOption] = {}
    claims: dict[tuple[str, ...], None] = {}

    def walk(bs: list[Block], ancestors: tuple[str, ...]) -> None:
        for b in bs:
            if b.category is not category:
                continue
            keys = candidate_keys(category, b, state)
            for key in keys:
                if "." in key:
                    dynamic.setdefault(key, option_from_key(category, key, _display_name(key, b)))
                else:
                    static_found.add(key)
            if keys:
                claims.setdefault(ancestors + tuple(keys), None)
            walk(b.children, ancestors + tuple(keys))

    walk(blocks, ())
    ordered = [option_from_key(category, o["sub_category"])
               for o in CATEGORY_SUB_OPTIONS.get(category, []) if o["sub_category"] in static_found]
    offered = [o for o in dynamic.values() if o.sub_category.partition(".")[0] not in HIDDEN_AXES]
    return ordered + offered, [list(c) for c in claims]


def discover_options(category: Category, blocks: list[Block]) -> list[SubOption]:
    """Just the options (see `discover`)."""
    return discover(category, blocks)[0]


def can_tick(claims: list[list[str]], ticked: set[str], key: str) -> bool:
    """May `key` be ticked on top of `ticked` without emptying anything?

    True when ticking it gives it at least one block and leaves every already-ticked option
    with at least one block. The UI uses this so a choice is never silently unticked: the
    first choice stays, and the option that would conflict with it is disabled instead.
    Mirrors the JavaScript `refreshSubAvailability`.
    """
    after = ticked | {key}
    return after <= live_keys(claims, after)


def live_keys(claims: list[list[str]], ticked: set[str]) -> set[str]:
    """Keys that would receive at least one block if exactly `ticked` were selected.

    Mirrors the splitter's rule (first ticked key among a block's candidates wins) and
    the JavaScript `liveSubKeys` used by the UI; a test keeps the two in agreement.
    """
    live: set[str] = set()
    for pattern in claims:
        owner = next((k for k in pattern if k in ticked), None)
        if owner:
            live.add(owner)
    return live
