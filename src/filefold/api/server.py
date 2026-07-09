"""Server-side workspace storage and session management."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

# Workspaces live in a configurable base directory.
# Default: ~/.filefold/workspaces  (overridable via FILEFOLD_WORKSPACE_DIR env var)
_DEFAULT_BASE = Path.home() / ".filefold" / "workspaces"
WORKSPACE_BASE: Path = Path(os.environ.get("FILEFOLD_WORKSPACE_DIR", _DEFAULT_BASE))


def workspace_path(name: str) -> Path:
    return WORKSPACE_BASE / name


def list_workspaces() -> list[str]:
    if not WORKSPACE_BASE.exists():
        return []
    return sorted(
        p.name for p in WORKSPACE_BASE.iterdir()
        if p.is_dir() and (p / ".filefold" / "workspace.json").exists()
    )
