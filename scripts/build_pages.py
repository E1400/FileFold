#!/usr/bin/env python3
"""Build the static GitHub Pages site into ./site (or --out).

    site/index.html            landing page (docs/index.html), "Try it online" -> app/
    site/app/index.html        the web UI with the in-browser Python shim injected
    site/app/static/           CSS + JS (including pyodide-worker.js, static-mode.js)
    site/app/pyodide/          Pyodide runtime (downloaded once, cached in build/)
    site/app/filefold-py.zip   FileFold's Python sources: core, service, browser (no FastAPI)

Usage: python scripts/build_pages.py [--out site] [--python-zip-only PATH]
"""
from __future__ import annotations

import argparse
import shutil
import tarfile
import time
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "filefold"
PYODIDE_VERSION = "314.0.7"
PYODIDE_URL = f"https://github.com/pyodide/pyodide/releases/download/{PYODIDE_VERSION}/pyodide-core-{PYODIDE_VERSION}.tar.bz2"
CACHE = ROOT / "build" / "pyodide-cache"
# The only runtime files a module-worker + stdlib-only app needs.
PYODIDE_FILES = ["pyodide.mjs", "pyodide.asm.mjs", "pyodide.asm.wasm", "python_stdlib.zip", "pyodide-lock.json"]

# Python the browser needs. Deliberately excludes api/routes, cli, desktop (FastAPI, Qt).
PY_FILES = ["__init__.py", "service.py", "browser.py", "api/__init__.py", "api/server.py"]


def build_python_zip(dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        for rel in PY_FILES:
            z.write(SRC / rel, f"filefold/{rel}")
        for path in sorted((SRC / "core").glob("*.py")):
            z.write(path, f"filefold/core/{path.name}")


def fetch_pyodide() -> Path:
    """Return the cached Pyodide runtime directory, downloading it on first use."""
    runtime = CACHE / PYODIDE_VERSION / "pyodide"
    if all((runtime / f).exists() for f in PYODIDE_FILES):
        return runtime
    CACHE.mkdir(parents=True, exist_ok=True)
    archive = CACHE / f"pyodide-core-{PYODIDE_VERSION}.tar.bz2"
    for attempt in range(1, 6):
        try:
            print(f"downloading Pyodide {PYODIDE_VERSION} (attempt {attempt})…")
            with urllib.request.urlopen(PYODIDE_URL, timeout=60) as resp, open(archive, "wb") as fh:
                shutil.copyfileobj(resp, fh)
            break
        except OSError as exc:
            if attempt == 5:
                raise
            print(f"  failed ({exc}); retrying")
            time.sleep(3 * attempt)
    with tarfile.open(archive) as tar:
        tar.extractall(CACHE / PYODIDE_VERSION, filter="data")
    return runtime


def build(out: Path) -> Path:
    if out.exists():
        shutil.rmtree(out)
    app = out / "app"
    app.mkdir(parents=True)

    # --- the app ---------------------------------------------------------------
    shutil.copytree(SRC / "web" / "static", app / "static")
    html = (SRC / "web" / "index.html").read_text(encoding="utf-8")
    marker = '<script src="static/core.js"></script>'
    assert marker in html, "index.html no longer loads static/core.js first"
    html = html.replace(marker, '<script src="static/static-mode.js"></script>\n' + marker, 1)
    (app / "index.html").write_text(html, encoding="utf-8")

    build_python_zip(app / "filefold-py.zip")
    runtime = fetch_pyodide()
    (app / "pyodide").mkdir()
    for name in PYODIDE_FILES:
        shutil.copy2(runtime / name, app / "pyodide" / name)

    # --- landing page ----------------------------------------------------------
    shutil.copy2(ROOT / "docs" / "index.html", out / "index.html")
    (out / ".nojekyll").write_text("")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=ROOT / "site")
    ap.add_argument("--python-zip-only", type=Path, help="write only the Python sources zip to this path")
    args = ap.parse_args()
    if args.python_zip_only:
        build_python_zip(args.python_zip_only)
        return
    out = build(args.out)
    total = sum(f.stat().st_size for f in out.rglob("*") if f.is_file())
    print(f"built {out} ({total / 1048576:.1f} MB)")


if __name__ == "__main__":
    main()
