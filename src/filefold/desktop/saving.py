"""Desktop only: save exports and single files straight into a folder chosen per workspace.

In a browser the page asks for a folder itself (File System Access API). The desktop window
cannot, so the page asks this router instead, which the desktop app adds to its local server
before starting it (never on a hosted server, where "a folder on this computer" would be the
server's). The first save of a workspace asks for a folder with a native dialog; later saves
go to the same folder without asking, until the person picks another.

Plain Python with the dialog passed in, so it is tested without a window.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

import anyio
from fastapi import APIRouter, Request

from filefold import service

# (workspace name, folder to start in or None) -> the chosen folder, or None if canceled
ChooseDir = Callable[[str, "Path | None"], "Path | None"]


class SaveDirs:
    """Workspace name -> folder, kept in a small JSON file next to the window's other data."""

    def __init__(self, store: Path) -> None:
        self.store = Path(store)

    def _read(self) -> dict[str, str]:
        try:
            data = json.loads(self.store.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def get(self, name: str) -> Path | None:
        found = self._read().get(name)
        return Path(found) if found and Path(found).is_dir() else None

    def set(self, name: str, folder: Path) -> None:
        data = self._read()
        data[name] = str(folder)
        self.store.parent.mkdir(parents=True, exist_ok=True)
        self.store.write_text(json.dumps(data, indent=2), encoding="utf-8")


def make_router(choose_dir: ChooseDir, dirs: SaveDirs) -> APIRouter:
    router = APIRouter()

    @router.get("/api/desktop/workspaces/{name}/save-dir")
    def get_save_dir(name: str):
        folder = dirs.get(name)
        return {"dir": str(folder) if folder else None}

    # Plain `def`: FastAPI runs it on a worker thread, so waiting for the dialog never
    # blocks the server's event loop.
    @router.post("/api/desktop/workspaces/{name}/save-dir")
    def choose_save_dir(name: str):
        if not service.workspace_path(name).is_dir():
            raise service.ServiceError(404, f"Workspace '{name}' not found", "workspace_not_found")
        folder = choose_dir(name, dirs.get(name))
        if folder is None:
            return {"dir": None, "canceled": True}
        dirs.set(name, folder)
        return {"dir": str(folder)}

    @router.post("/api/desktop/workspaces/{name}/save")
    async def save(name: str, request: Request):
        """Body: {"filename": one file, or omitted for the whole workspace as <name>.zip;
        "replace": true to overwrite a file of that name already in the folder}."""
        body = await request.json()
        filename = body.get("filename")
        # Read first: an unknown workspace or file fails before any dialog opens.
        if filename:
            data, leaf = service.read_file(name, filename), Path(filename).name
        else:
            data, leaf = service.export_zip(name), f"{name}.zip"
        folder = dirs.get(name)
        if folder is None:
            folder = await anyio.to_thread.run_sync(choose_dir, name, None)
            if folder is None:
                return {"saved": None, "canceled": True}
            dirs.set(name, folder)
        target = folder / leaf
        # Never replace a file without asking: the folder may be the person's project folder,
        # holding their original deck under the same name.
        if target.exists() and not body.get("replace"):
            return {"saved": None, "exists": True, "path": str(target), "dir": str(folder)}
        target.write_bytes(data)
        return {"saved": str(target), "dir": str(folder)}

    return router
