"""No line may be lost or duplicated when a real deck is split by every option it offers."""
import io
import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from filefold.api.main import NON_EXTRACTABLE, app

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr("filefold.api.server.WORKSPACE_BASE", tmp_path)
    return TestClient(app), tmp_path


def _expand(path: Path, root: Path) -> str:
    """Inline *INCLUDEs of files that FileFold wrote; leave a deck's own includes alone."""
    text = path.read_bytes().decode("utf-8", errors="surrogateescape")

    def sub(m: re.Match) -> str:
        target = root / m.group(1)
        return _expand(target, root) if target.is_file() else m.group(0)

    return re.sub(r"^\*INCLUDE,[ \t]*INPUT=(\S+?)[ \t]*\r?\n", sub, text, flags=re.M | re.I)


@pytest.mark.parametrize("name", sorted(p.name for p in FIXTURES.glob("*.inp")))
def test_splitting_by_every_offered_option_loses_no_lines(client, name):
    c, root = client
    data = (FIXTURES / name).read_bytes()
    info = c.post("/api/inspect", files={"file": (name, io.BytesIO(data))}).json()
    selections = [
        {"category": cat, "filename": f"{cat}.inp",
         "sub_selections": [{"sub_category": o["sub_category"], "filename": o["default_filename"]} for o in opts]}
        for cat, opts in info["sub_options"].items() if cat not in NON_EXTRACTABLE
    ]
    # also extract categories that have no sub-options at all
    have = {s["category"] for s in selections}
    for b in info["blocks"]:
        if b["category"] not in NON_EXTRACTABLE and b["category"] not in have:
            selections.append({"category": b["category"], "filename": f"{b['category']}.inp", "sub_selections": []})
            have.add(b["category"])
    r = c.post("/api/workspaces", files={"file": (name, io.BytesIO(data))},
               data={"name": "w", "selections": json.dumps(selections)})
    assert r.status_code == 200, r.text
    expanded = _expand(root / "w" / name, root / "w")
    original = data.decode("utf-8", errors="surrogateescape")
    assert sorted(expanded.splitlines()) == sorted(original.splitlines())
