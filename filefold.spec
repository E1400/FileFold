# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for FileFold desktop app.

Build commands
--------------
macOS:
    pyinstaller filefold.spec          → dist/FileFold.app
    # or via uv:
    uv run pyinstaller filefold.spec

Windows:
    pyinstaller filefold.spec          → dist/FileFold/FileFold.exe
"""

import sys
import tomllib
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

VERSION = tomllib.loads(Path("pyproject.toml").read_text())["project"]["version"]

# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

a = Analysis(
    ["src/filefold/desktop/app.py"],
    pathex=[str(Path(".").resolve() / "src")],
    binaries=[],
    datas=[
        # Web assets — must mirror the relative path compute_split uses
        ("src/filefold/web/index.html", "filefold/web"),
        ("src/filefold/web/static", "filefold/web/static"),
    ],
    # Every FileFold and uvicorn module, found automatically, so new modules are never missed
    # (a hand-written list here had silently gone stale).
    hiddenimports=collect_submodules("filefold") + collect_submodules("uvicorn") + [
        "anyio._backends._asyncio",
        "multipart",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Keep bundle lean — not needed at runtime
        "pytest",
        "httpx",
        "tkinter",
        "matplotlib",
        "numpy",
        "pandas",
        "IPython",
        "playwright",
        "PyInstaller",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

# ---------------------------------------------------------------------------
# Executable
# ---------------------------------------------------------------------------

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="FileFold",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,        # UPX can break Qt binaries; keep off
    console=False,    # No terminal window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file="build/entitlements.plist" if sys.platform == "darwin" else None,
    icon="build/icon.icns" if sys.platform == "darwin" else "build/icon.ico",
)

# ---------------------------------------------------------------------------
# Collect (directory bundle — faster startup than --onefile)
# ---------------------------------------------------------------------------

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="FileFold",
)

# ---------------------------------------------------------------------------
# macOS .app bundle
# ---------------------------------------------------------------------------

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="FileFold.app",
        icon="build/icon.icns",
        bundle_identifier="com.filefold.desktop",
        info_plist={
            "CFBundleName": "FileFold",
            "CFBundleDisplayName": "FileFold",
            "CFBundleVersion": VERSION,
            "CFBundleShortVersionString": VERSION,
            "CFBundleExecutable": "FileFold",
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "12.0",
            "NSRequiresAquaSystemAppearance": False,  # supports dark mode
            # WebEngine needs this on macOS to render properly
            "NSAppTransportSecurity": {"NSAllowsLocalNetworking": True},
        },
    )
