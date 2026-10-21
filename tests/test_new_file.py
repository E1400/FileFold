"""New files: an empty child the mother *INCLUDEs before the first step, kept by re-import,
moved like any child, folded back without a trace."""
from pathlib import Path

import pytest

from filefold import service
from filefold.core.keywords import Category
from filefold.core.splitter import SplitSelection, read_raw
from filefold.core.workspace import Workspace, history_start, insert_include

FIXTURES = Path(__file__).parent / "fixtures"
JOB1 = FIXTURES / "Job-1.inp"


def make(tmp_path, source: Path = JOB1, cats=("mesh", "material", "step")) -> Workspace:
    sels = [SplitSelection(Category(c), f"{c}.inp") for c in cats]
    return Workspace.create(tmp_path / "ws", source, sels)


def lines(ws: Workspace) -> list[str]:
    return read_raw(ws.path / ws.source_name).splitlines()


# --- where the *INCLUDE goes ---------------------------------------------------------

def test_history_start_skips_back_over_the_step_header_comments():
    text = "*NODE\n1,0\n** ----\n**\n** STEP: Step-1\n**\n*Step, name=Step-1\n*Static\n*End Step\n"
    assert text[history_start(text):].startswith("** ----")


def test_history_start_finds_an_extracted_step_file_and_a_deck_without_steps():
    text = "*NODE\n1,0\n*INCLUDE, INPUT=step.inp\n"
    assert text[history_start(text, {"step.inp"}):] == "*INCLUDE, INPUT=step.inp\n"
    assert history_start("*NODE\n1,0\n") == len("*NODE\n1,0\n")
    # a keyword that only starts with STEP is not a step
    assert history_start("*STEADY STATE DYNAMICS\n") == len("*STEADY STATE DYNAMICS\n")


def test_insert_include_uses_the_files_line_ending_and_ends_an_unterminated_last_line():
    assert insert_include("*A\r\n*B\r\n", "x.inp", 4) == "*A\r\n*INCLUDE, INPUT=x.inp\r\n*B\r\n"
    assert insert_include("*A", "x.inp", 2) == "*A\n*INCLUDE, INPUT=x.inp\n"


def test_new_file_is_empty_included_before_the_step_and_marked_added(tmp_path):
    ws = make(tmp_path)
    ws.add_file("extra.inp")
    assert read_raw(ws.path / "extra.inp") == ""
    assert ws.include_order() == ["mesh.inp", "material.inp", "extra.inp", "step.inp"]
    assert ws.added_files() == ["extra.inp"]
    rec = ws.file_records["extra.inp"]
    assert (rec.role, rec.category, rec.parent) == ("child", None, None)
    # only one line was added to the mother, and the change is FileFold's, not an edit
    assert len(lines(ws)) == len(lines(make(tmp_path / "b"))) + 1
    data = service_status(ws)
    assert not data["Job-1.inp"]["manually_edited"]
    assert data["extra.inp"]["added"] and not data["extra.inp"]["manually_edited"]


def service_status(ws: Workspace) -> dict:
    import filefold.api.server as server
    old = server.WORKSPACE_BASE
    server.WORKSPACE_BASE = ws.path.parent
    try:
        return {f["filename"]: f for f in service.get_workspace(ws.path.name)["files"]}
    finally:
        server.WORKSPACE_BASE = old


def test_new_file_in_a_deck_whose_step_is_still_in_the_mother(tmp_path):
    ws = make(tmp_path, cats=("mesh",))
    ws.add_file("extra.inp")
    text = lines(ws)
    i = text.index("*INCLUDE, INPUT=extra.inp")
    assert text[i + 1].startswith("**") and any(l.lower().startswith("*step") for l in text[i:])
    assert not any(l.lower().startswith("*step") for l in text[:i])


def lf_only(raw: bytes) -> int:
    return raw.count(b"\n") - raw.count(b"\r\n")


def crlf_job1(tmp_path) -> Path:
    crlf = tmp_path / "crlf.inp"
    crlf.write_bytes(JOB1.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    return crlf


def test_new_file_keeps_a_crlf_mother_crlf(tmp_path):
    ws = make(tmp_path, source=crlf_job1(tmp_path))
    before = (ws.path / ws.source_name).read_bytes()
    ws.add_file("extra.inp")
    raw = (ws.path / ws.source_name).read_bytes()
    assert b"*INCLUDE, INPUT=extra.inp\r\n" in raw
    assert lf_only(raw) == lf_only(before)          # no LF-only line added


# --- living with the other operations --------------------------------------------------

def test_reimport_keeps_the_added_file_and_its_place(tmp_path):
    ws = make(tmp_path)
    ws.add_file("extra.inp")
    (ws.path / "extra.inp").write_text("*AMPLITUDE, NAME=A1\n0., 0., 1., 1.\n")
    ws.reorder_children(["extra.inp", "mesh.inp"])     # now first
    before = ws.include_order()
    preview = ws.reimport_preview(JOB1)
    assert "*INCLUDE, INPUT=extra.inp" in preview.new_mother_content
    assert "extra.inp" not in {s.filename for s in preview.statuses}   # nothing to review: it is yours
    ws.reimport_apply(JOB1, preview, set())
    assert ws.include_order() == before
    assert read_raw(ws.path / "extra.inp").startswith("*AMPLITUDE")


def test_reimport_with_a_new_category_keeps_the_added_file(tmp_path):
    ws = make(tmp_path, cats=("mesh", "step"))
    ws.add_file("extra.inp")
    preview = ws.reimport_preview(JOB1)
    ws.reimport_apply(JOB1, preview, set(), [SplitSelection(Category.MATERIAL, "material.inp")])
    order = ws.include_order()
    assert "extra.inp" in order and "material.inp" in order
    assert order.index("extra.inp") < order.index("step.inp")


def test_folding_an_empty_added_file_gives_back_the_mother_byte_for_byte(tmp_path):
    ws = make(tmp_path)
    before = read_raw(ws.path / ws.source_name)
    ws.add_file("extra.inp")
    ws.recombine(["extra.inp"])
    assert read_raw(ws.path / ws.source_name) == before
    assert not (ws.path / "extra.inp").exists() and "extra.inp" not in ws.file_records


def test_folding_a_written_added_file_puts_its_lines_where_the_include_was(tmp_path):
    """The added *INCLUDE ends in \\r\\n in a CRLF mother; folding must still find it."""
    ws = make(tmp_path, source=crlf_job1(tmp_path))
    before = (ws.path / ws.source_name).read_bytes()
    ws.add_file("extra.inp")
    (ws.path / "extra.inp").write_bytes(b"*AMPLITUDE, NAME=A1\r\n0., 0., 1., 1.\r\n")
    ws.recombine(["extra.inp"])
    raw = (ws.path / ws.source_name).read_bytes()
    assert b"*AMPLITUDE, NAME=A1\r\n0., 0., 1., 1.\r\n*INCLUDE, INPUT=step.inp" in raw
    assert lf_only(raw) == lf_only(before)


def test_folding_an_empty_added_file_out_of_a_crlf_mother_restores_it(tmp_path):
    ws = make(tmp_path, source=crlf_job1(tmp_path))
    before = (ws.path / ws.source_name).read_bytes()
    ws.add_file("extra.inp")
    ws.recombine(["extra.inp"])
    assert (ws.path / ws.source_name).read_bytes() == before


def test_folding_back_finds_an_include_line_that_ends_in_crlf(tmp_path):
    """Pre-existing gap fixed alongside: an *INCLUDE line ending in \\r\\n (hand-written, or
    added as above) did not match, so the fold silently did nothing."""
    ws = make(tmp_path)
    mother = ws.path / ws.source_name
    mother.write_bytes(mother.read_bytes().replace(b"INPUT=material.inp\n", b"INPUT=material.inp\r\n"))
    ws.recombine(["material.inp"])
    raw = mother.read_bytes()
    assert b"INPUT=material.inp" not in raw and b"*Material" in raw


# --- service rules ----------------------------------------------------------------------

@pytest.fixture()
def svc_ws(tmp_path, monkeypatch):
    import filefold.api.server as server
    monkeypatch.setattr(server, "WORKSPACE_BASE", tmp_path)
    service.create_workspace("J", "Job-1.inp", JOB1.read_bytes(),
                             [{"category": "mesh", "filename": "mesh.inp"}, {"category": "step", "filename": "step.inp"}])
    return "J"


def test_service_adds_inp_when_the_name_has_no_extension(svc_ws):
    out = service.add_file(svc_ws, "extra-loads")
    assert out["added"] == "extra-loads.inp"
    assert out["order"] == ["mesh.inp", "extra-loads.inp", "step.inp"]


@pytest.mark.parametrize("name, code", [
    ("mesh.inp", "filename_taken"), ("MESH.INP", "filename_taken"), ("Job-1.inp", "filename_taken"),
    ("my file.inp", "invalid_include_name"), ("a,b.inp", "invalid_include_name"), (".hidden", "invalid_include_name"),
    ("../x.inp", "invalid_name"), ("", "required"),
])
def test_service_refuses_names_that_clash_or_break_an_include(svc_ws, name, code):
    with pytest.raises((service.ServiceError, service.UnsafeName)) as e:
        service.add_file(svc_ws, name)
    assert e.value.code == code


def test_service_folds_an_added_file_back(svc_ws):
    service.add_file(svc_ws, "extra.inp")
    assert service.recombine(svc_ws, ["extra.inp"])["recombined"] == ["extra.inp"]
    assert "extra.inp" not in service.get_workspace(svc_ws)["include_order"]
