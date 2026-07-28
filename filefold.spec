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
from pathlib import Path

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
    ],
    hiddenimports=[
        # uvicorn dynamic imports
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.loops.asyncio",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.http.h11_impl",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        "uvicorn.lifespan.off",
        # fastapi / starlette internals loaded at runtime
        "fastapi",
        "fastapi.routing",
        "fastapi.responses",
        "starlette.routing",
        "starlette.responses",
        "starlette.middleware",
        "starlette.middleware.base",
        "starlette.staticfiles",
        # anyio asyncio backend
        "anyio",
        "anyio._backends._asyncio",
        # multipart (file uploads)
        "multipart",
        # filefold packages — explicit so nothing is missed
        "filefold.api.main",
        "filefold.api.server",
        "filefold.core.keywords",
        "filefold.core.block",
        "filefold.core.parser",
        "filefold.core.tokenizer",
        "filefold.core.splitter",
        "filefold.core.workspace",
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
            "CFBundleVersion": "0.1.0",
            "CFBundleShortVersionString": "0.1.0",
            "CFBundleExecutable": "FileFold",
            "NSHighResolutionCapable": True,
            "NSRequiresAquaSystemAppearance": False,  # supports dark mode
            # WebEngine needs this on macOS to render properly
            "NSAppTransportSecurity": {"NSAllowsLocalNetworking": True},
        },
    )
