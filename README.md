# FileFold

Workspace manager for Abaqus `.inp` files. Split large FEA models by category, track edits, detect reimport conflicts, and export clean archives — all from a browser or native desktop app.

---

## Links

| | |
|---|---|
| **Web app** | https://filefold-production.up.railway.app |
| **Landing page** | https://e1400.github.io/FileFold |
| **Desktop downloads** | https://github.com/E1400/FileFold/releases |

---

## What it does

Abaqus `.inp` files grow large and become difficult to manage — mesh, materials, boundary conditions, and step definitions all living in one file. FileFold splits a mother file into category-specific child files using `*INCLUDE` directives, so Abaqus reads the model identically but engineers can work on each section independently.

**Core workflow:**

1. Upload a mother `.inp` file
2. Choose which categories to extract (`MESH`, `MATERIAL`, `STEP`, `LOADS`, `CONTACT`, `OUTPUT`, etc.)
3. FileFold produces a workspace: a mother file with `*INCLUDE` pointers + individual child files
4. Edit child files directly; reimport an updated mother when the source changes
5. Export the full workspace as a ZIP when ready

**What makes it reliable:**

- **Byte-exact round-trips** — the reassembled model is character-for-character identical to the original
- **Container-aware parsing** — `*PART`, `*ASSEMBLY`, `*STEP` blocks are understood as containers; nested blocks follow their parent, never misclassified
- **SHA-256 change detection** — reimport shows exactly which files changed in the new source, which were manually edited, and which conflict
- **In-browser editor** — view and edit any workspace file without leaving the UI (Tab indenting, Cmd+S to save, unsaved-changes guard)

---

## Options

### Online (no install)

Go to **https://filefold-production.up.railway.app** — upload a file and use it directly in the browser.

### Desktop app

Download from the [Releases page](https://github.com/E1400/FileFold/releases):

- **macOS** — `FileFold-macOS.zip` → unzip → open `FileFold.app`. Runs as a menu bar tray app (no terminal needed).
- **Windows** — `FileFold-Windows.zip` → unzip → run `FileFold.exe`. Same tray-icon experience.

The desktop app runs a local server on a free port and opens the UI in an embedded browser window. Files never leave your machine.

### Self-hosted / local development

**Requirements:** Python 3.13+, [uv](https://docs.astral.sh/uv/)

```bash
git clone https://github.com/E1400/FileFold.git
cd FileFold
uv sync
uv run filefold serve
```

Then open http://127.0.0.1:8000.

**With hot-reload (dev mode):**
```bash
uv run filefold serve --reload
```

**Custom host/port:**
```bash
uv run filefold serve --host 0.0.0.0 --port 9000
```

---

## CLI

FileFold also ships a command-line interface for scripted workflows.

```bash
# Inspect a file — print keyword block tree
uv run filefold inspect model.inp

# Split into category files (all categories, separate directory per category)
uv run filefold split model.inp ./output/

# Split with *INCLUDE pointers (creates a workspace from the command line)
uv run filefold split-partial model.inp ./output/ -e mesh -e material -e step

# Launch the desktop GUI
uv run filefold launch

# Workspace management
uv run filefold workspace create ./my-workspace model.inp -e mesh -e material
uv run filefold workspace status ./my-workspace
uv run filefold workspace reimport ./my-workspace updated_model.inp
```

---

## Development

**Install with dev dependencies:**
```bash
uv sync --dev
```

**Run tests:**
```bash
uv run pytest
```

**Build the desktop app (requires icons first):**
```bash
uv sync --extra desktop
uv run python build/make_icons.py
uv run pyinstaller filefold.spec --clean
```

The built app appears at `dist/FileFold.app` (macOS) or `dist/FileFold/` (Windows).

**Release a new version** (triggers GitHub Actions to build Mac + Windows bundles):
```bash
git tag v0.x.x
git push origin v0.x.x
```

---

## Project structure

```
src/filefold/
├── api/
│   ├── main.py        # FastAPI routes
│   └── server.py      # Workspace base path, FILEFOLD_WORKSPACE_DIR
├── cli/
│   └── main.py        # Typer CLI (inspect, split, serve, launch, workspace)
├── core/
│   ├── parser.py      # .inp file parser
│   ├── tokenizer.py   # Keyword/data line tokenizer
│   ├── block.py       # Block data model
│   ├── keywords.py    # Category taxonomy
│   ├── splitter.py    # Split logic, *INCLUDE generation, SHA-256 tracking
│   └── workspace.py   # Workspace create/load/reimport
├── desktop/
│   └── app.py         # PySide6 app + uvicorn server thread + system tray
└── web/
    └── index.html     # Single-page frontend (vanilla JS, no build step)

docs/
└── index.html         # Landing page (served via GitHub Pages)

build/
├── make_icons.py      # Generates icon.icns / icon.ico via PySide6 + iconutil
└── entitlements.plist # macOS codesign entitlements for WebEngine

tests/
├── test_api.py        # FastAPI endpoint tests (20 tests)
├── test_splitter.py   # Core splitter tests (14 tests)
└── fixtures/          # Sample .inp files for testing
```

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `FILEFOLD_WORKSPACE_DIR` | `~/.filefold/workspaces` | Where workspaces are stored on disk |
| `PORT` | `8000` | Port for the web server (set automatically by Railway) |
| `FILEFOLD_HOST` | `127.0.0.1` | Bind address for the web server |
