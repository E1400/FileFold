# FileFold

Workspace manager for Abaqus `.inp` files. Split large FEA models by category, or down to one file per material, step or part. Track edits, detect reimport conflicts, and export clean archives — from your browser, a native desktop app, or the command line.

---

## Links

| | |
|---|---|
| **Web app** (runs in your browser) | https://e1400.github.io/FileFold/app/ |
| **Landing page** | https://e1400.github.io/FileFold |
| **Desktop downloads** | https://github.com/E1400/FileFold/releases |

---

## What it does

Abaqus `.inp` files grow large and become difficult to manage — mesh, materials, boundary conditions, and step definitions all living in one file. FileFold splits a mother file into category-specific child files using `*INCLUDE` directives, so Abaqus reads the model identically but engineers can work on each section independently.

**Core workflow:**

1. Upload a mother `.inp` file
2. Choose which categories to extract (`MESH`, `MATERIAL`, `STEP`, `LOADS`, `CONTACT`, `CONSTRAINT`, `OUTPUT`, etc.), and optionally split them further: one file per material, step or part; nodes, elements and sets; contact pairs; ties and couplings
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

Go to **https://e1400.github.io/FileFold/app/** — upload a file and use it directly in the browser.

This is a static site: FileFold's Python runs inside your browser (via [Pyodide](https://pyodide.org)), so your model **never leaves your machine** and there is no server. Workspaces are stored in the browser (IndexedDB) on that device; use **Export ZIP** to take them elsewhere. First load downloads about 13 MB of runtime, then it is cached.

Size: decks up to **100 MB** are tested end to end (about 7 s to inspect, 15 s to create). A 200 MB deck did not finish creating in the browser, so use the desktop app for models that large.

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

Everything the app can do is available from the command line (the CLI and the app share one implementation, and a test fails if they drift apart). Workspaces are stored in `~/.filefold/workspaces` (or `$FILEFOLD_WORKSPACE_DIR`, or `--workspaces DIR`), the same place the web app and desktop app use, so a workspace made in one shows up in the others.

```bash
# Look at a deck: block tree, and the finer splits it offers (per material, step, part, ...)
uv run filefold inspect model.inp --options

# Split a deck into a folder, leaving *INCLUDE pointers in the mother
uv run filefold split-partial model.inp ./out -e mesh -e material
uv run filefold split-partial model.inp ./out -e mesh=geometry.inp -s mesh:nodes -s material:material.steel

# Workspaces
uv run filefold workspace create demo model.inp -e mesh -s mesh:nodes -e step
uv run filefold workspace list
uv run filefold workspace status demo              # files and whether any were edited
uv run filefold workspace options demo             # what can still be extracted or split
uv run filefold workspace extract demo -e loads -e contact
uv run filefold workspace resplit demo mesh -s mesh:nodes -s mesh:elements
uv run filefold workspace resplit demo mesh        # no -s: fold the sub-files back
uv run filefold workspace recombine demo mesh-nodes.inp
uv run filefold workspace rename-file demo mesh.inp geometry.inp
uv run filefold workspace cat demo geometry.inp > copy.inp
uv run filefold workspace put demo geometry.inp edited.inp
uv run filefold workspace reimport demo updated_model.inp [--force] [-e newcategory]
uv run filefold workspace export demo -o demo.zip
uv run filefold workspace rename demo demo-v2
uv run filefold workspace delete demo --yes

# Apps
uv run filefold serve
uv run filefold launch
```

`-e CATEGORY[=filename]` extracts a category; `-s CATEGORY:KEY[=filename]` splits it further (list the keys with `inspect --options` or `workspace options`) and implies extracting the category. A workspace argument may also be a folder path, as in earlier versions.

---

## Development

**Install with dev dependencies:**
```bash
uv sync --dev
```

**Run tests** (unit, API, JS lint, and headless-browser end-to-end against the real server):
```bash
uv run playwright install chromium   # once
uv run pytest
FILEFOLD_E2E_TARGET=static uv run pytest tests/e2e   # same browser tests against the static build
```

**Build the static site** (landing page + in-browser app) into `site/`:
```bash
python scripts/build_pages.py
python -m http.server --directory site 8080   # then open http://localhost:8080/app/
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
| `PORT` | `8000` | Port for the web server (hosts such as Railway set it automatically) |
| `FILEFOLD_HOST` | `127.0.0.1` | Bind address for the web server |
