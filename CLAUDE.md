# FileFold — Claude context

Workspace manager / intelligent parser for Abaqus `.inp` files. Parses a **mother** file
into keyword blocks, splits categories into child files joined by `*INCLUDE`, tracks edits
via SHA-256, detects reimport conflicts, exports ZIP. Four surfaces over one core: FastAPI
web app, in-browser Pyodide build (GitHub Pages), Typer CLI, PySide6 desktop app.

Read on demand, not up front:
- `docs/DECISIONS.md` — append-only decision log + where `main` stands. Append when a
  branch merges, an invariant changes, or an architecture/hosting call is made.
- `docs/BACKLOG.md` — full-deployment backlog. Append whenever something is decided
  *because* the browser build is small.
- `docs/RAILWAY.md` — deploy checklist and the real memory numbers.
- `../deployment-guide/NOTES.md` — educational write-up notes, deliberately **outside** this
  repo. Append as things happen.

Owner: Elvis. Reference-only repos (never edit; each has its own `.git`): `../reference/`
holds `AbqParse`, `fempy`, `meshio`, compared in `notebooks/parse-comparison.ipynb`.

## Commands

```bash
.venv/bin/python -m pytest -q                       # everything (unit, API, e2e, JS lint)
FILEFOLD_E2E_TARGET=static .venv/bin/python -m pytest -q tests/e2e   # the Pages build
.venv/bin/filefold serve [--reload]                 # http://127.0.0.1:8000
```

`uv` is NOT on PATH in the agent shell (`pip install uv` into a scratch venv when a lock
refresh is needed). The README documents `uv run filefold serve`; its command examples are
executed by `tests/test_docs.py`.

## Invariants

- **Byte-exact round-trip.** Parse -> split -> recombine must return the original bytes.
  Editor saves preserve CRLF. `tests/test_roundtrip.py` and the split-integrity tests are
  the guard; no split may lose or duplicate a line.
- **`service.py` holds ALL application logic**, framework-free, raising `ServiceError`.
  `api/routes/*` are thin FastAPI wrappers; `browser.py` is the in-browser dispatcher and
  its route table must mirror FastAPI (tested); `cli/` is a thin layer, never a second
  implementation.
- **Four-way parity for any `service.py` or `/api` change**: update `browser.py`,
  and `service.OPERATIONS` must stay mapped by `cli.main.OPERATION_COMMANDS`
  (`tests/test_cli.py` fails otherwise).
- **The server path must never rot** even though Pages is the current host: FastAPI app,
  `Dockerfile`, `railway.toml`, `uv.lock`, `docs/RAILWAY.md`. Enforced by the CI `docker`
  job (`scripts/docker_smoke.sh`), `uv lock --check`, `tests/test_deploy_config.py` and the
  e2e suite running on BOTH targets. Pages is the dev phase; the user moves to Railway when
  the app is done (bigger decks, shared access). Railway is intentionally not deployed yet
  (cost) — the app returns 404 there.
- **Adding a category or a split option requires updating the Info page**
  (`src/filefold/web/index.html` `#view-help`) — `test_info_tab_describes_every_function`
  fails otherwise — **and the landing page** `docs/index.html`, whose "Supported" breakdown
  is tied to the code by `tests/test_docs.py` (every `Category`, every fixed split label,
  `len(FACTS)`, every CLI command, the in-browser size limit, each example keyword's
  category). Same for a new CLI command or a changed limit.
- **(i) reminder texts stay <= 240 chars** (tested). User-facing text uses **US spelling**.
- The landing page is self-contained (inline CSS, no external requests) and reuses the app's
  exact design tokens; `tests/test_docs.py` fails if they drift from `app.css`.
- Version lives in `pyproject.toml` **and** `FastAPI(version=...)` (a test keeps them equal)
  plus `uv.lock`. Bump on a `release/vX.Y.Z` branch, merge, wait for CI on main, then tag.

## Workflow rules

- A new git branch per edit stage (`feature/…`, `fix/…`, `release/…`); merge to `main` only
  after the user has tested. Never commit feature work to `main`.
- Never switch branches here while the user may be testing the checked-out one — ask first.
  (If another agent holds `FileFold/`, use a git worktree.)
- During iteration run only the tests relevant to the change; the full suite once before
  merge. After every merge to `main`, check the CI run on `main` — not just the Pages
  deploy — and any failed run since the last check.
- Skills install to `~/.claude/skills/`, never per-project.

## Testing protocol (mandatory before telling the user to test)

- Any UI/API change needs a browser test that exercises it. API-only tests are not enough —
  that gap shipped a broken create flow to `main`.
- New bug => write the failing e2e test first, watch it fail, then fix.
- e2e rule: every test fails on ANY console error, pageerror or failed `/api` response. A
  test that provokes an error must clear `page.expected_errors`.
- `tests/e2e` runs real uvicorn + headless Chromium (Playwright); `tests/test_js_static.py`
  is ESLint `no-undef` over the inline JS.

## Map (`src/filefold/`)

- `core/tokenizer.py` line classify (KEYWORD/COMMENT/BLANK/DATA), `keyword_of`,
  `parse_params` (quote-aware; the parser merges continuation lines)
- `core/parser.py` -> `list[Block]` tree. Containers: STEP, PART, ASSEMBLY, INSTANCE.
- `core/keywords.py` keyword -> `Category` (hand tables + `_REFERENCE_OVERRIDES` + prefix
  rules + categories derived from the reference); static sub-category groups for mesh,
  contact, constraint, loads
- `core/keyword_reference.py` GENERATED facts (type, level, documented parents) for all 523
  keywords of the Abaqus 2016 Keywords Reference. Regenerate with
  `scripts/extract_keyword_reference.py --html-dir <local copy>` — the pages are not in the
  repo (source: ceae-server.colorado.edu/v2016/books/key/, `chNNabkMM.html`).
- `core/subsplits.py` sub-split keys (static groups + name-based); `discover_options()` feeds
  the UI via `sub_options`
- `core/splitter.py` `split()` (full), `compute_split()` / `split_with_includes()` (partial,
  INCLUDE pointers, sub-splits)
- `core/workspace.py` manifest, reimport preview/apply, recombine, resplit_child, rename_child
- `service.py`, `api/routes/*`, `browser.py` — see Invariants. `api/main.py` app + static
  mount; `api/server.py` storage + path safety.
- `web/index.html` markup only (also the Info page `#view-help`). `web/static/`: `core.js`
  (incl. `errorText`, `showFieldError`, `refreshSubAvailability`), `info.js` ((i) popover +
  `INFO` texts), `samples.js` (Sample data menu; decks + generated `manifest.json` in
  `static/samples/`, regenerate with `scripts/build_samples_manifest.py` — tests keep it in
  sync and keep the decks identical to `tests/fixtures`), `tour.js` (skippable coach-mark
  tour; pref in localStorage `filefold.tour`). Classic scripts, load order matters:
  `core, views, splits, create, reimport, editor, info, samples, tour, boot`.
  Nothing is ever pre-loaded — samples load only when chosen. The e2e harness seeds the tour
  as dismissed; tour tests call `as_new_visitor`.
- `desktop/` PySide6 QtWebEngine window over the real FastAPI server on 127.0.0.1, **fixed
  port 47321** (localStorage is per-origin, so a stable port keeps theme/tour), named
  persistent profile in `~/.filefold/desktop`. Loads `/?desktop=1` -> `data-desktop` hides
  `.hide-in-desktop`. Icon drawn by `desktop/icon.py` (`build/make_icons.py`).
  `--smoke-test` exits 0 only when the UI really renders. `tests/desktop` drives the BUILT
  app over QtWebEngine remote debugging with a raw CDP client (Playwright cannot attach);
  needs `FILEFOLD_DESKTOP_APP=...` and `QT_QPA_PLATFORM=offscreen`.
  Builds: `.github/workflows/build-desktop.yml` (Apple Silicon, Intel `macos-15-intel`,
  Windows); a `v*` tag attaches `FileFold-macOS-AppleSilicon.zip`,
  `FileFold-macOS-Intel.zip`, `FileFold-Windows.zip`. Landing download buttons point at
  `releases/latest/download/<asset>` (a test ties the names to the workflow), so a release
  must exist before those links work. Unsigned. The local Mac is Intel — local builds are
  x86_64 only.
- Hosting build: `scripts/build_pages.py` -> `site/` (landing `/` + app `/app/`, Pyodide
  314.0.7, worker `web/static/pyodide-worker.js`, fetch shim `web/static/static-mode.js`),
  deployed by `.github/workflows/pages.yml` on push to `main`. Landing screenshots in
  `docs/img/` are generated from the real app by `scripts/make_landing_screenshots.py` —
  re-run after the UI's look changes. Theme choice: localStorage `filefold.theme`, shared by
  landing page and app.

## Gotchas / known gaps

- Keyword categories for ~250 reference keywords come from rules (parent, else documented
  type/level shape) plus hand overrides: **judgement calls, not facts from the manual.**
  Tests only enforce that every reference keyword *has* a category and that every
  hand-registered name really exists in Abaqus (typo guard). Keywords newer than 2016 come
  from the Release Notes list; anything else inherits the previous block's category
  (`Block.inherited`).
- Level/type facts are stored but deliberately **not** used to validate decks: decks without
  `*PART` legitimately use part-level keywords at top level, so a naive level check gives
  false warnings.
- `*SYSTEM` / `*TRANSFORM` apply to the *next* `*NODE`; a later `*SYSTEM`+`*NODE` pair can
  be separated when nodes are sub-split.
- Existing `*INCLUDE` in source decks are not resolved. Model-data vs history-data level is
  not modeled (only `Block.context`, the open container stack).
- Element type is a *refinement* of the static `elements` group (`parent_of`,
  `SubOption.parent`): ticking it ticks Elements, and Elements may then be empty
  ('covered', no file — `covered_parents` / JS `coveredSubParents`). Sub-split keys are
  slugs (`material.steel`), so names differing only by punctuation share a file. `*INSTANCE`
  (inside the non-extractable `model` category) cannot be split.
- Sub-split choices are never silently unticked: first choice wins, conflicting options are
  disabled via `can_tick` / `refreshSubAvailability`.
- Create and re-split peak at ~5-6x deck size (streaming is deferred — see
  `docs/BACKLOG.md`). In-browser: tested to 100 MB end to end (~7 s inspect, ~15 s create);
  200 MB did not finish create in Chromium; the UI warns above 100 MB.
- The app shell is not phone-responsive (fixed 220 px sidebar); it squeezes below ~700 px.
- The CI `docker` job can fail on Docker Hub 429 rate limits — infra, just rerun.
- Caching: the server sends `Cache-Control: no-store` on `/api/*` and `no-cache` on the UI, and
  the desktop window has no HTTP cache. Without it an updated desktop app kept running the old
  build's scripts. A desktop bug seen only there: first check the build (tray menu shows the
  version) — the user once ran a local pre-release build from `~/Downloads`.
- Server hardening done: streaming uploads, filename path-traversal fixed, read-only parses
  use `keep_lines=False`, optional `FILEFOLD_MAX_UPLOAD_MB` and `FILEFOLD_BASIC_AUTH`.
