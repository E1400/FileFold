"""Server-side workspace storage and session management."""
from __future__ import annotations

import os
from pathlib import Path

# Workspaces live in a configurable base directory.
# Default: ~/.filefold/workspaces  (overridable via FILEFOLD_WORKSPACE_DIR env var)
_DEFAULT_BASE = Path.home() / ".filefold" / "workspaces"
WORKSPACE_BASE: Path = Path(os.environ.get("FILEFOLD_WORKSPACE_DIR", _DEFAULT_BASE))


class UnsafeName(ValueError):
    """A client-supplied workspace or file name that is missing or escapes its directory.

    Carries a machine-readable `code` and the form `field` it concerns, so the UI can
    highlight that field with its own wording instead of showing this message.
    """

    def __init__(self, detail: str, code: str = "invalid_name", field: str | None = None,
                 value: str | None = None):
        super().__init__(detail)
        self.code, self.field, self.value = code, field, value

    def payload(self) -> dict:
        out = {"detail": str(self), "code": self.code}
        if self.field:
            out["field"] = self.field
        if self.value is not None:
            out["value"] = self.value
        return out


def safe_segment(value: str, kind: str = "name") -> str:
    """Validate that a client-supplied string is a single, contained path segment.

    Names arrive from JSON bodies and form fields and are joined onto the workspace
    root, so '../..' or an absolute path would place files anywhere the process can
    write. Reject rather than silently sanitise — a caller that asked for
    '../evil.inp' should be told no, not handed a file with a different name.
    """
    cleaned = (value or "").strip()
    field = "name" if kind in ("workspace name", "name") else "filename"
    if not cleaned:
        raise UnsafeName(f"{kind} is required", "required", field)
    if cleaned in {".", ".."} or "/" in cleaned or "\\" in cleaned or "\x00" in cleaned:
        raise UnsafeName(f"Invalid {kind}: {value!r}", "invalid_name", field, value)
    if Path(cleaned).is_absolute() or Path(cleaned).name != cleaned:
        raise UnsafeName(f"Invalid {kind}: {value!r}", "invalid_name", field, value)
    return cleaned


def workspace_path(name: str) -> Path:
    return WORKSPACE_BASE / safe_segment(name, "workspace name")


def child_path(ws_dir: Path, filename: str) -> Path:
    """Resolve a file inside a workspace, refusing anything that escapes it."""
    return ws_dir / safe_segment(filename, "filename")


def list_workspaces() -> list[str]:
    if not WORKSPACE_BASE.exists():
        return []
    return sorted(
        p.name for p in WORKSPACE_BASE.iterdir()
        if p.is_dir() and (p / ".filefold" / "workspace.json").exists()
    )
