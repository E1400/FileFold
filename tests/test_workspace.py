"""Workspace create, status, and reimport tests."""
from pathlib import Path

import pytest

from filefold.core.keywords import Category
from filefold.core.splitter import SplitSelection
from filefold.core.workspace import Workspace

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture()
def fempy_workspace(tmp_path: Path) -> Workspace:
    return Workspace.create(
        directory=tmp_path / "fempy_ws",
        source=FIXTURES / "fempy_example.inp",
        selections=[
            SplitSelection(Category.MESH, "mesh.inp"),
            SplitSelection(Category.MATERIAL, "material.inp"),
        ],
    )


def test_create_writes_files(fempy_workspace: Workspace, tmp_path: Path) -> None:
    ws = fempy_workspace
    assert (ws.path / "fempy_example.inp").exists()
    assert (ws.path / "mesh.inp").exists()
    assert (ws.path / "material.inp").exists()
    assert ws.manifest_path.exists()
    assert "mesh.inp" in ws.file_records
    assert "material.inp" in ws.file_records


def test_load_roundtrips_manifest(fempy_workspace: Workspace) -> None:
    ws2 = Workspace.load(fempy_workspace.path)
    assert ws2.source_name == fempy_workspace.source_name
    assert ws2.file_records.keys() == fempy_workspace.file_records.keys()
    assert ws2.selections[0].category == Category.MESH


def test_reimport_no_change(fempy_workspace: Workspace) -> None:
    """Re-importing the same file should show nothing to update."""
    preview = fempy_workspace.reimport_preview(FIXTURES / "fempy_example.inp")
    assert not preview.safe_to_update
    assert not preview.needs_attention
    assert len(preview.unchanged) == 2


def test_reimport_detects_manual_edit(fempy_workspace: Workspace) -> None:
    """Manually editing a child that also changed in the new mother triggers a warning."""
    ws = fempy_workspace

    # Manually edit material.inp on disk
    mat_path = ws.path / "material.inp"
    mat_path.write_text(mat_path.read_text() + "** engineer edit\n", encoding="utf-8")

    # Simulate a new mother where material content is different
    original = (FIXTURES / "fempy_example.inp").read_text(encoding="utf-8")
    new_mother = original.replace("*MATERIAL", "** changed\n*MATERIAL", 1)
    new_source = ws.path / "fempy_v2.inp"
    new_source.write_text(new_mother, encoding="utf-8")

    preview = ws.reimport_preview(new_source)

    # material changed in new mother AND was manually edited → needs attention
    assert any(s.filename == "material.inp" for s in preview.needs_attention)
    # mesh unchanged in new mother
    assert any(s.filename == "mesh.inp" for s in preview.unchanged)


def test_reimport_apply_skips_edited(fempy_workspace: Workspace) -> None:
    """apply with empty update set leaves manually edited file intact."""
    ws = fempy_workspace
    mat_path = ws.path / "material.inp"
    mat_path.write_text(mat_path.read_text() + "** engineer edit\n", encoding="utf-8")
    edited_content = mat_path.read_text(encoding="utf-8")

    original = (FIXTURES / "fempy_example.inp").read_text(encoding="utf-8")
    new_mother = original.replace("*MATERIAL", "** changed\n*MATERIAL", 1)
    new_source = ws.path / "fempy_v2.inp"
    new_source.write_text(new_mother, encoding="utf-8")

    preview = ws.reimport_preview(new_source)
    # Apply with no filenames to update (engineer chose to skip)
    ws.reimport_apply(new_source, preview, filenames_to_update=set())

    # Manual edit must be preserved
    assert mat_path.read_text(encoding="utf-8") == edited_content


def test_reimport_apply_force_overwrites(fempy_workspace: Workspace) -> None:
    """apply with the filename included overwrites even a manually edited file."""
    ws = fempy_workspace
    mat_path = ws.path / "material.inp"
    mat_path.write_text(mat_path.read_text() + "** engineer edit\n", encoding="utf-8")

    original = (FIXTURES / "fempy_example.inp").read_text(encoding="utf-8")
    new_mother = original.replace("*MATERIAL", "** changed\n*MATERIAL", 1)
    new_source = ws.path / "fempy_v2.inp"
    new_source.write_text(new_mother, encoding="utf-8")

    preview = ws.reimport_preview(new_source)
    ws.reimport_apply(new_source, preview, filenames_to_update={"material.inp"})

    # File should now contain the new content (not the engineer's edit)
    assert "** engineer edit" not in mat_path.read_text(encoding="utf-8")
    assert "** changed" in mat_path.read_text(encoding="utf-8")
