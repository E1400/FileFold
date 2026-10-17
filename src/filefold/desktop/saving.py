"""Desktop only: Export ZIP and single-file downloads through a native Save dialog.

In a browser the page opens a Save dialog itself (showSaveFilePicker). The desktop window
cannot, so the page asks this router instead, which the desktop app adds to its local server
before starting it (never on a hosted server, where "a folder on this computer" would be the
server's). Every save asks where to save, starting in the folder this workspace was last
saved to, so Enter saves to the same place again. The dialog confirms replacing a file.

Plain Python with the dialog passed in, so it is tested without a window.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

import anyio
from fastapi import APIRouter, Request

from filefold import service

# (title, suggested path) -> the path chosen, or None if canceled
AskSavePath = Callable[[str, Path], "Path | None"]


class SaveDirs:
    """Workspace name -> the folder it was last saved to, in a small JSON file."""

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


def make_router(ask_save_path: AskSavePath, dirs: SaveDirs, default_dir: Callable[[], Path]) -> APIRouter:
    router = APIRouter()

    @router.post("/api/desktop/workspaces/{name}/save")
    async def save(name: str, request: Request):
        """Body: {"filename": one file, or omitted for the whole workspace as <name>.zip}."""
        body = await request.json()
        filename = body.get("filename")
        # Read first: an unknown workspace or file fails before any dialog opens.
        if filename:
            data, leaf = service.read_file(name, filename), Path(filename).name
        else:
            data, leaf = service.export_zip(name), f"{name}.zip"
        start = (dirs.get(name) or default_dir()) / leaf
        # On a worker thread: waiting for the dialog must not block the server's event loop.
        target = await anyio.to_thread.run_sync(ask_save_path, f"Save {leaf}", start)
        if target is None:
            return {"saved": None, "canceled": True}
        target = Path(target)
        target.write_bytes(data)
        dirs.set(name, target.parent)
        return {"saved": str(target), "dir": str(target.parent)}

    return router
