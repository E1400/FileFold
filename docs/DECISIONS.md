# Decision log

Append-only. Add an entry ONLY for: a merged branch/milestone, an architecture or hosting
decision, a changed invariant, a new known gap. One or two lines, dated, newest last.
Do not rewrite history. `CLAUDE.md` holds the rules that follow from these decisions; keep
it true, keep this file as it happened.

## Where main stands (2026-10-15)

Trunk-based, old branches pruned. `main` contains everything through: theme redesign,
static Pages build, guidance features (sample data, (i) reminders, tour, Info tab), the
landing redesign + Supported breakdown, the sidebar redesign, the desktop app (3 platform
builds) and the element-type split fix. Latest release: desktop v0.1.1. No open working
branch.

## Log

- 2026-10-02: Created the Claude context file. Plan agreed to prioritise the parser keyword registry (data-driven, Abaqus-doc-based) and GitHub-based hosting evaluation.
- 2026-10-02: Went trunk-based; merged theme-redesign to main, pruned branches, moved reference repos to `reference/` (editable installs redone with `--no-deps`).
- 2026-10-02: Parser registry + inheritance + continuation lines + `Block.context`; new categories `constraint`, `initial`; static sub-splits for contact/constraint/loads.
- 2026-10-02: REGRESSION on main (commit 5f92e25 deleted JS const NON_EXTRACTABLE; create flow crashed) shipped because only the API was tested. Fixed on feature/keyword-registry with the Playwright e2e suite + eslint no-undef + CI (`.github/workflows/ci.yml`).
- 2026-10-02: Merged feature/keyword-registry (registry, e2e suite, CI, sub-split filtering) to main; main regression fixed. Started refactor/split-ui-and-api.
- 2026-10-02: Refactor done: `index.html` split into `static/*.css|js`, `api/main.py` split into `routes/`. No behaviour change; the e2e suite is the safety net. PyInstaller spec now bundles `web/static`.
- 2026-10-02: Dynamic splits (material/step/part/element type) + editor unsaved-changes dialog + CRLF-preserving editor saves on feature/dynamic-splits. Integrity test: every fixture split by every offered option loses/duplicates no lines.
- 2026-10-05: Hosting decision: GitHub Pages static build (Pyodide in a worker, IndexedDB workspaces) instead of Railway. Logic moved to framework-free `service.py` shared by FastAPI and `browser.py`; the same e2e suite passes on both targets.
- 2026-10-05: Registry expanded with ~60 keywords from the Abaqus Release Notes; doc-derived regression list in `tests/fixtures/abaqus_release_notes_keywords.txt`.
- 2026-10-05: Sub-split options now carry `sub_claims` (which options could receive which blocks, splitter precedence); the UI (`refreshSubAvailability` in `core.js`) disables/unticks options that would produce no file. A property test checks claims against the real splitter on all fixtures.
- 2026-10-05: Merged dynamic splits + the static Pages build to main. Fixed a path traversal (upload filename) in staging, added streaming uploads, light parse mode, a Docker fix (no `uv run` at start), the docker CI job, optional basic-auth/size cap, `docs/RAILWAY.md`.
- 2026-10-05: Sub-split UX: choices are never silently unticked (first choice wins; conflicting options are disabled via `can_tick` / `refreshSubAvailability`). Element-type splits hidden from menus (`HIDDEN_AXES`) but still supported by the splitter. Material/step/part remain the name-based axes.
- 2026-10-05: Keyword registry rebuilt against the Abaqus 2016 Keywords Reference (crawled 523 pages; facts only committed). Found and removed 4 invented names (BUOYANCY, STEP CONTROLS, DYNAMIC EXPLICIT, COUPLED TEMP-DISPLACEMENT); FIELD moved to loads. Prefix rules CONTACT/CONNECTOR needed step-level overrides.
- 2026-10-06: CLI rebuilt as a thin layer over `service` (full parity: sub-splits, extract, resplit, recombine, rename, delete, export, cat/put, reimport with new categories); old directory-path forms still work. Landing page and README refreshed (no Railway links; new feature copy); tests guard links and documented commands.
- 2026-10-06: User deferred streaming create/re-split until the Railway deployment; added the full-deployment backlog (now `docs/BACKLOG.md`) and the requirement for a separate educational deployment guide outside the repo.
- 2026-10-06: First attempt at user guidance (literal chalkboard + home-page samples) was a misread; the user meant 'chalkboard' figuratively. Replaced by: a Sample data button on New Workspace (user-initiated, never pre-loaded), minimal (i) reminders, a skippable coach-mark tour (Google-Sheets style), and an Info tab describing every function. 3 decks (~7 MB) ship as static assets and are publicly downloadable.
- 2026-10-07: Merged the guidance features and deployed to Pages; verified live. Found and fixed a flaky e2e on main CI (Splits-tab Apply read before it finished). LESSON: after every merge to main, check the CI run on main (not just the Pages deploy) and any failed run since the last check.
- 2026-10-08: Landing page rebuilt to match the app (ink-on-grey drafting-sheet look, shared tokens, real screenshots, a real Fig. 1 computed from Job-1). Caught by looking at screenshots: a CSS specificity bug showed both theme screenshots; e2e now checks both directions plus the system-theme default. Theme choice now persists and is shared between landing page and app.
- 2026-10-08: User approved the landing redesign; headline changed to 'Parse your FEA models.' and copy repositioned as an intelligent parser. Added the full 'Supported' breakdown, tied to the code by tests.
- 2026-10-08: Merged the landing redesign + Supported breakdown to main; CI green; verified live.
- 2026-10-08: Merged feature/sidebar-redesign (VS Code-style activity bar + collapsible panel, Workspaces group, title-only Search; Info as an activity-bar icon; fixed the open workspace never being highlighted) and regenerated the landing screenshots. User asked to run only the tests relevant to a change during iteration (full suite once before merge). Worktree `SWE/FileFold-sidebar` was used because another agent had `FileFold/` checked out.
- 2026-10-12: Element type is now a refinement of Elements (indented under it, ticking it ticks Elements, Elements may be empty = no file); replaces the 2026-10-05 `HIDDEN_AXES` approach, which made element type a one-way door once switched off (user-reported).
- 2026-10-12: Merged feature/desktop-app: Apple Silicon/Intel/Windows builds tested in CI (smoke + built-app e2e), stable port + persistent profile, downloads, Dock reopen; README rewritten; landing download buttons -> `releases/latest/download/<asset>`. Released v0.1.0 (unsigned). Apple Developer ID signing/notarization offered to the user ($99/yr), pending their decision. The CI docker job can fail on Docker Hub 429 rate limits (infra, rerun).
- 2026-10-15: Merged tour/Info wording (no redundant "Nothing is created" lines; tour steps 3-6 wait for a loaded deck, pointing at Sample data) and form-style errors: server errors carry `code`/`field`/`value` (`ServiceError`/`UnsafeName` `.payload()`, same via `browser.py`); the UI words them (`errorText` in `core.js`), marks the wrong field (`showFieldError`), and error toasts stay until closed. User-facing text uses US spelling.
- 2026-10-15: Released desktop v0.1.1 (tour/Info wording, form-style errors, US spelling).
- 2026-10-16: Moved the Claude context file from `SWE/CLAUDE.md` into the repo as `FileFold/CLAUDE.md`, trimmed to commands/invariants/gotchas; the decision log and the full-deployment backlog split out into `docs/DECISIONS.md` and `docs/BACKLOG.md`, read on demand.
