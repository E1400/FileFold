"""Stream request uploads to disk so a large deck is never held in memory."""
from __future__ import annotations

import os
import shutil
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import UploadFile

from filefold.service import ServiceError, safe_upload_name

_CHUNK = 1024 * 1024


def max_upload_bytes() -> int | None:
    """Optional cap from FILEFOLD_MAX_UPLOAD_MB (unset or 0 = unlimited)."""
    mb = float(os.environ.get("FILEFOLD_MAX_UPLOAD_MB", "0") or 0)
    return int(mb * 1024 * 1024) if mb > 0 else None


@asynccontextmanager
async def staged_upload(file: UploadFile):
    """Write the upload to <tmpdir>/<safe name> in chunks and yield that path.

    The directory is removed afterwards, including when the size cap is exceeded.
    """
    limit = max_upload_bytes()
    tmpdir = Path(tempfile.mkdtemp())
    try:
        path = tmpdir / safe_upload_name(file.filename or "")
        written = 0
        with open(path, "wb") as out:
            while chunk := await file.read(_CHUNK):
                written += len(chunk)
                if limit is not None and written > limit:
                    raise ServiceError(413, f"File is larger than the {limit // (1024 * 1024)} MB upload limit")
                out.write(chunk)
        yield path
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
