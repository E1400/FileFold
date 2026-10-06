"""The command line exposes everything the app does (it is a thin layer over filefold.service)."""
import io
import json
import re
import zipfile
from pathlib import Path

import pytest
from typer.main import get_command
from typer.testing import CliRunner

from filefold import service
from filefold.cli.main import OPERATION_COMMANDS, app

FIXTURES = Path(__file__).parent / "fixtures"
JOB1 = str(FIXTURES / "Job-1.inp")          # CRLF deck
MMXMN = str(FIXTURES / "mmxmn.inp")
runner = CliRunner()


@pytest.fixture()
def ws(tmp_path, monkeypatch):
    base = tmp_path / "workspaces"
    monkeypatch.setattr("filefold.api.server.WORKSPACE_BASE", base)   # restored after the test
    def run(*args, ok=True):
        result = runner.invoke(app, ["--workspaces", str(base), *args])
        if ok:
            assert result.exit_code == 0, result.output
        return result
    run.base = base
    return run


def files_of(ws, name):
    return {f["filename"]: f for f in service.get_workspace(name)["files"]}


# --- parity ----------------------------------------------------------------------------

def _commands():
    root = get_command(app)
    found = set(root.commands) - {"workspace"}
    found |= {f"workspace {c}" for c in root.commands["workspace"].commands}
    return found


def test_every_service_operation_has_a_cli_command():
    assert set(service.OPERATIONS) == set(OPERATION_COMMANDS), "map every service operation to a command"
    missing = {op: cmd for op, cmd in OPERATION_COMMANDS.items() if cmd not in _commands()}
    assert not missing, missing


# --- inspect ---------------------------------------------------------------------------

def test_inspect_lists_blocks_and_the_split_options_that_exist(ws):
    out = ws("inspect", JOB1, "--options").output
    assert "ELEMENT" in out and "mesh" in out
    assert "mesh:nodes" in out and "material:material.steel" in out and "step:step.step-1" in out
    assert "constraint:rigid" in out
    assert "etype" not in out                       # element-type splits are not offered
    assert "constraint:ties" not in out             # nothing in Job-1 to tie


# --- split-partial (directory, no workspace) ------------------------------------------------

def test_split_partial_with_sub_splits_and_custom_filenames(ws, tmp_path):
    out_dir = tmp_path / "out"
    ws("split-partial", JOB1, str(out_dir), "-e", "mesh=geometry.inp", "-s", "mesh:nodes", "-e", "material")
    names = {p.name for p in out_dir.iterdir()}
    assert {"Job-1.inp", "geometry.inp", "mesh-nodes.inp", "material.inp"} <= names
    assert "*Node" in (out_dir / "mesh-nodes.inp").read_text()


def test_a_sub_split_implies_its_category(ws, tmp_path):
    out_dir = tmp_path / "out"
    ws("split-partial", JOB1, str(out_dir), "-s", "mesh:nodes")
    assert {"mesh.inp", "mesh-nodes.inp"} <= {p.name for p in out_dir.iterdir()}


def test_unknown_category_and_unknown_sub_split_are_explained(ws, tmp_path):
    bad = ws("split-partial", JOB1, str(tmp_path / "o"), "-e", "nonsense", ok=False)
    assert bad.exit_code == 1 and "mesh" in bad.output and "constraint" in bad.output
    bad = ws("split-partial", JOB1, str(tmp_path / "o2"), "-s", "mesh:wings", ok=False)
    assert bad.exit_code == 1 and "mesh:nodes" in bad.output


# --- workspaces ---------------------------------------------------------------------------

def test_create_list_status_and_the_crlf_edit_false_positive(ws):
    ws("workspace", "create", "demo", JOB1, "-e", "mesh", "-e", "constraint")
    assert "demo" in ws("workspace", "list").output
    status = ws("workspace", "status", "demo").output
    assert "mesh.inp" in status and "constraint.inp" in status
    assert "edited" not in status.replace("manually edited: 0", "")   # a CRLF deck must not look edited
    assert files_of(ws, "demo")["mesh.inp"]["manually_edited"] is False


def test_legacy_directory_form_still_works(ws, tmp_path):
    target = tmp_path / "elsewhere" / "legacy"
    ws("workspace", "create", str(target), JOB1, "-e", "mesh")
    assert (target / "mesh.inp").exists()
    assert "mesh.inp" in ws("workspace", "status", str(target)).output


def test_extract_options_resplit_and_recombine(ws):
    ws("workspace", "create", "demo", JOB1, "-e", "mesh")
    options = ws("workspace", "options", "demo").output
    assert "mesh:nodes" in options and "material:material.steel" in options
    ws("workspace", "extract", "demo", "-e", "material", "-s", "material:material.steel")
    assert "material-steel.inp" in files_of(ws, "demo")
    ws("workspace", "resplit", "demo", "mesh", "-s", "mesh:nodes", "-s", "mesh:elements")
    names = set(files_of(ws, "demo"))
    assert {"mesh-nodes.inp", "mesh-elements.inp"} <= names
    ws("workspace", "resplit", "demo", "mesh")                  # no -s: fold every sub-file back
    assert "mesh-nodes.inp" not in files_of(ws, "demo")
    ws("workspace", "recombine", "demo", "material-steel.inp")
    assert "material-steel.inp" not in files_of(ws, "demo")


def test_rename_file_rename_workspace_cat_put_and_export(ws, tmp_path):
    ws("workspace", "create", "demo", JOB1, "-e", "mesh")
    ws("workspace", "rename-file", "demo", "mesh.inp", "geometry.inp")
    assert "geometry.inp" in files_of(ws, "demo")
    assert "*Node" in ws("workspace", "cat", "demo", "geometry.inp").output

    edited = tmp_path / "edited.inp"
    edited.write_bytes(b"** replaced\r\n*NODE\r\n1,0,0,0\r\n")
    ws("workspace", "put", "demo", "geometry.inp", str(edited))
    assert files_of(ws, "demo")["geometry.inp"]["manually_edited"] is True
    assert service.read_file("demo", "geometry.inp") == edited.read_bytes()   # CRLF preserved

    zpath = tmp_path / "demo.zip"
    ws("workspace", "export", "demo", "-o", str(zpath))
    assert "geometry.inp" in zipfile.ZipFile(zpath).namelist()

    ws("workspace", "rename", "demo", "renamed")
    assert "renamed" in ws("workspace", "list").output and "demo" not in ws("workspace", "list").output.split()


def test_delete_needs_confirmation(ws):
    ws("workspace", "create", "demo", JOB1, "-e", "mesh")
    refused = runner.invoke(app, ["--workspaces", str(ws.base), "workspace", "delete", "demo"], input="n\n")
    assert refused.exit_code != 0 and "demo" in service.list_all_workspaces()["workspaces"]
    ws("workspace", "delete", "demo", "--yes")
    assert "demo" not in service.list_all_workspaces()["workspaces"]


def test_missing_workspace_is_a_clean_error(ws):
    bad = ws("workspace", "status", "ghost", ok=False)
    assert bad.exit_code == 1 and "not found" in bad.output.lower()


def test_reimport_updates_children_and_reports_conflicts(ws, tmp_path):
    ws("workspace", "create", "demo", JOB1, "-e", "mesh")
    new = tmp_path / "Job-1.inp"
    new.write_bytes(Path(JOB1).read_bytes().replace(b"*Node", b"*Node ** upstream", 1))
    out = ws("workspace", "reimport", "demo", str(new)).output
    assert "mesh.inp" in out and "update" in out.lower()
    # now edit mesh.inp locally and re-import a different upstream: conflict, skipped without --force
    service.write_file("demo", "mesh.inp", b"** mine\r\n")
    new.write_bytes(Path(JOB1).read_bytes().replace(b"*Node", b"*Node ** second upstream", 1))
    out = ws("workspace", "reimport", "demo", str(new)).output
    assert "manually edited" in out and "--force" in out
    assert service.read_file("demo", "mesh.inp") == b"** mine\r\n"
    ws("workspace", "reimport", "demo", str(new), "--force")
    assert b"second upstream" in service.read_file("demo", "mesh.inp")


def test_reimport_can_extract_a_new_category(ws, tmp_path):
    ws("workspace", "create", "demo", JOB1, "-e", "mesh")
    ws("workspace", "reimport", "demo", JOB1, "-e", "material")
    assert "material.inp" in files_of(ws, "demo")
