# FileFold

An intelligent parser for Abaqus `.inp` files. FileFold reads a model block by block, knows what every keyword is (all 523 in the Abaqus 2016 Keywords Reference, plus newer ones), and splits the model into a small mother file and organised child files joined by `*INCLUDE`. You can split by category, or down to one file per material, step or part. It tracks your edits, flags conflicts when you reimport an updated model, and exports clean archives. Use it in your browser, as a desktop app for Mac and Windows, or from the command line.

---

## Links

| | |
|---|---|
| **Web app** (runs in your browser) | https://e1400.github.io/FileFold/app/ |
| **Landing page** | https://e1400.github.io/FileFold |
| **Desktop downloads** | https://github.com/E1400/FileFold/releases/latest |

---

## What it does

Abaqus `.inp` files grow large and hard to manage: mesh, materials, boundary conditions and steps all in one file. FileFold splits the original (the **mother** file) into child files and puts `*INCLUDE` lines in their place, so Abaqus reads the model exactly as before while you work on each part separately.

**Core workflow:**

1. Upload a mother `.inp` file, or load one of the three sample decks (`Job-1`, `mmxmn`, `fempy_example`)
2. Choose which categories to extract (`mesh`, `section`, `material`, `step`, `loads`, `contact`, `constraint`, `initial`, `output`), and optionally split them further: one file per material, step or part; nodes, elements and sets; contact pairs; ties and couplings. Only splits that would produce a file for your deck are offered.
3. FileFold creates a workspace: the mother file with `*INCLUDE` pointers, plus one file per choice
4. Edit files in the built-in editor, extract more later, re-split, fold files back, rename them
5. Reimport an updated mother file when the source model changes; conflicts show exactly what changed
6. Export the whole workspace as a ZIP

**What makes it reliable:**

- **Byte-exact round-trips**: the reassembled model is character-for-character identical to the original, line endings included
- **Container-aware parsing**: `*PART`, `*ASSEMBLY`, `*INSTANCE` and `*STEP` own the blocks inside them; options such as `*ELASTIC` always stay with their `*MATERIAL`
- **SHA-256 change detection**: reimport knows whether a file changed in the new source, was edited by you, or both
- **Built-in editor**: find, line-range selection, comment toggling, Cmd/Ctrl+S to save, unsaved-changes guard

New users get a skippable one-minute tour, small (i) reminders, and an Info page that describes every function.

---

## Options

### Online (no install)

Go to **https://e1400.github.io/FileFold/app/**.

This is a static site: FileFold's Python runs inside your browser (via [Pyodide](https://pyodide.org)), so your model **never leaves your machine** and there is no server. Workspaces are stored in the browser (IndexedDB) on that device; use **Export ZIP** to take them elsewhere. The first visit downloads about 13 MB of runtime, which is then cached.

Size: decks up to **100 MB** are tested end to end (about 7 s to inspect, 15 s to create). A 200 MB deck did not finish creating in the browser, so use the desktop app or the command line for models that large.

### Desktop app

The same app, running on your computer. It has no size limit beyond your machine's memory and works without an internet connection. Download it from the [latest release](https://github.com/E1400/FileFold/releases/latest):

| Computer | Download | Then |
|---|---|---|
| Mac with Apple Silicon (M1 or later) | `FileFold-macOS-AppleSilicon.zip` | unzip, move `FileFold.app` to Applications, open it |
| Mac with an Intel processor | `FileFold-macOS-Intel.zip` | same as above |
| Windows 10 or 11 (64-bit) | `FileFold-Windows.zip` | unzip the whole folder, run `FileFold.exe` inside it |

To see which Mac you have, choose Apple menu > About This Mac: "Chip" means Apple Silicon, "Processor" means Intel. macOS 12 or later is needed.

**First launch.** The app is not yet signed with an Apple or Microsoft developer certificate, so your computer warns you the first time:

- **macOS** says it cannot verify the app. Click **Done**, open **System Settings > Privacy & Security**, scroll down to the message about FileFold and click **Open Anyway**, then confirm. You only do this once.
- **Windows** shows "Windows protected your PC". Click **More info**, then **Run anyway**.

**Using it.** FileFold opens in its own window and puts an icon in the menu bar (macOS) or the system tray (Windows). Closing the window keeps FileFold running; reopen it from that icon (or the Dock on macOS) and quit from the icon's menu or with Cmd/Ctrl+Q. Exports are saved to your Downloads folder. Workspaces are stored in `~/.filefold/workspaces`, the same folder the command line uses, so a workspace made in one shows up in the other.

The desktop app runs FileFold's server on your computer only (`127.0.0.1`) and shows it in a built-in browser window. Nothing is sent anywhere. It is about 550 MB unzipped, mostly the built-in browser engine.

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

A `Dockerfile` is included for hosting it on a server; see [docs/RAILWAY.md](docs/RAILWAY.md).

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

`-e CATEGORY[=filename]` extracts a category; `-s CATEGORY:KEY[=filename]` splits it further (list the keys with `inspect --options` or `workspace options`) and implies extracting the category. A workspace argument may also be a folder path, as in earlier versions. `filefold launch` starts the desktop app from source (needs `uv sync --extra desktop`).

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

**Build and test the desktop app:**
```bash
uv sync --extra desktop
uv run python build/make_icons.py            # icon.png / .ico / .icns from the app's logo
uv run pyinstaller filefold.spec --clean --noconfirm
dist/FileFold.app/Contents/MacOS/FileFold --smoke-test          # prints SMOKE OK
FILEFOLD_DESKTOP_APP=dist/FileFold.app/Contents/MacOS/FileFold uv run pytest tests/desktop
```

The built app appears at `dist/FileFold.app` (macOS) or `dist/FileFold/FileFold.exe` (Windows); it is built for the processor of the machine that builds it. `tests/desktop` drives the built app's real window through its remote-debugging port (creating a workspace, exporting it, settings surviving a restart); on a machine without a display set `QT_QPA_PLATFORM=offscreen`. `tests/test_desktop.py` covers the desktop code without building.

**Release a new version.** Pushing a tag builds the Apple Silicon, Intel and Windows apps on GitHub Actions, smoke-tests and end-to-end tests each one, and attaches the three zips to a GitHub release:
```bash
git tag v0.x.x
git push origin v0.x.x
```
Running the "Build Desktop App" workflow by hand builds and tests without releasing.

---

## Project structure

```
src/filefold/
├── core/              # the parser: tokenizer, parser, keyword registry, splitter, workspace
├── service.py         # all application logic, shared by every front end below
├── api/               # FastAPI server: main.py (app), routes/ (thin wrappers over service)
├── browser.py         # in-browser dispatcher for the static build (mirrors the API routes)
├── cli/main.py        # Typer CLI (thin layer over service)
├── desktop/           # PySide6 desktop app (app.py) and its icon (icon.py)
└── web/               # index.html + static/ (CSS, JS, sample decks); no build step

docs/                  # landing page (GitHub Pages) and RAILWAY.md hosting checklist
scripts/               # static site build, landing screenshots, sample manifest, Docker smoke test
build/                 # make_icons.py, macOS entitlements
filefold.spec          # PyInstaller recipe for the desktop app
tests/                 # unit + API tests, e2e/ (Playwright), desktop/ (built desktop app)
```

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `FILEFOLD_WORKSPACE_DIR` | `~/.filefold/workspaces` | Where workspaces are stored on disk |
| `PORT` | `8000` | Port for the web server (hosts such as Railway set it automatically) |
| `FILEFOLD_HOST` | `127.0.0.1` | Bind address for the web server |
| `FILEFOLD_MAX_UPLOAD_MB` | none | Server: reject uploads above this size |
| `FILEFOLD_BASIC_AUTH` | none | Server: `user:password` gate for the whole app |
| `FILEFOLD_DESKTOP_PORT` | `47321` | Desktop: local port (a fixed port keeps the window's settings; `0` = any free port) |
| `FILEFOLD_DESKTOP_DATA` | `~/.filefold/desktop` | Desktop: the window's browser storage (theme, tour) |
| `FILEFOLD_DOWNLOAD_DIR` | your Downloads folder | Desktop: where exports are saved |
