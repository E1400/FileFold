"""Sample decks shipped with the app: files, facts and the split options they advertise."""
import hashlib
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from filefold import service
from filefold.api.main import app

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "src" / "filefold" / "web" / "static" / "samples"
FIXTURES = Path(__file__).parent / "fixtures"
MANIFEST = SAMPLES / "manifest.json"

sys.path.insert(0, str(ROOT / "scripts"))
import build_samples_manifest as gen  # noqa: E402

IDS = ["Job-1", "mmxmn", "fempy_example"]


def manifest() -> list[dict]:
    return json.loads(MANIFEST.read_text())["samples"]


def test_three_samples_are_shipped():
    assert [s["id"] for s in manifest()] == IDS
    for s in manifest():
        assert (SAMPLES / s["file"]).is_file()


def test_manifest_is_up_to_date_with_the_decks():
    """Facts are computed from the decks, not typed. If a deck or the parser changes, rerun
    `python scripts/build_samples_manifest.py` and commit the result."""
    assert gen.build() == json.loads(MANIFEST.read_text())


@pytest.mark.parametrize("sample_id", IDS)
def test_sample_is_identical_to_the_test_fixture(sample_id):
    a = (SAMPLES / f"{sample_id}.inp").read_bytes()
    b = (FIXTURES / f"{sample_id}.inp").read_bytes()
    assert hashlib.sha256(a).digest() == hashlib.sha256(b).digest()


@pytest.mark.parametrize("sample_id", IDS)
def test_sample_is_served_by_the_app(sample_id):
    r = TestClient(app).get(f"/static/samples/{sample_id}.inp")
    assert r.status_code == 200 and r.content == (SAMPLES / f"{sample_id}.inp").read_bytes()


@pytest.mark.parametrize("sample", manifest() if MANIFEST.exists() else [], ids=lambda s: s["id"])
def test_every_split_a_sample_advertises_really_exists(sample):
    """The 'try' hints on each card must be options the deck actually offers."""
    info = service.inspect(sample["file"], (SAMPLES / sample["file"]).read_bytes())
    assert sample["try"], "a sample should suggest something to try"
    for hint in sample["try"]:
        category, _, key = hint.partition(":")
        offered = [o["sub_category"] for o in info["sub_options"].get(category, [])]
        assert key in offered or (key.endswith("*") and any(k.startswith(key[:-1]) for k in offered)), (sample["id"], hint, offered)


def test_each_sample_has_a_title_and_plain_language_blurb():
    for s in manifest():
        assert s["title"] and len(s["blurb"]) > 60 and s["facts"]["bytes"] > 0
