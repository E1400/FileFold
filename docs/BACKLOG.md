# Full-deployment backlog

The app is deliberately a LOW-MEMORY, serverless dev version (GitHub Pages + in-browser
Python). Several choices exist only because of that and are to be revisited at the Railway
switch. **Add to this list whenever a decision is made "because the browser build is
small".** Checklist for the switch itself: `docs/RAILWAY.md`.

## Deferred on purpose — do NOT work on these until we deploy to Railway

(user decision 2026-10-06)

- Streaming workspace create / re-split. Today both hold the whole deck: peak ~5-6x deck
  size (a 100 MB deck needs ~0.6 GB). Needs a redesign of `compute_split` that keeps the
  byte-exact guarantee.

## Before the switch

- Per-user workspaces + real sign-in. The server has one shared folder; `FILEFOLD_BASIC_AUTH`
  is only a stop-gap for a private/staging copy.
- Size the Railway plan from the `docs/RAILWAY.md` numbers, measure the real service after
  the first big upload, then set `FILEFOLD_MAX_UPLOAD_MB`.
- Attach a volume at `/data`; decide backups (users can Export ZIP).
- `get_workspace` re-hashes every file on each request: fine at dev scale, cache or store
  sizes/hashes for big workspaces.
- Single uvicorn worker: one long split blocks others. Add workers/a queue once there are
  several users.
- Remove or raise the 100 MB in-browser warning for the server build (`staticSizeWarning`
  only fires when `FILEFOLD_STATIC`).
- Decide what the landing page's and README's "Try it online" points to (Railway URL, with
  Pages kept as a free private fallback?). `tests/test_docs.py` currently forbids any
  `up.railway.app` link and requires `app/` — update it deliberately then.
- Pyodide-only code (`static-mode.js`, `pyodide-worker.js`, `browser.py`,
  `scripts/build_pages.py`, `pages.yml`) can stay as the fallback, but the server path must
  keep passing the docker CI job and both e2e targets.
- Revisit the Keywords Reference-derived category overrides if real decks show misplaced
  keywords (they are judgement calls, not facts from the manual).
- Rate limiting / abuse protection, logging and monitoring, a custom domain, a cost estimate.

## During the switch

- Follow the `docs/RAILWAY.md` checklist; first deploy behind `FILEFOLD_BASIC_AUTH`; run the
  real decks (Job-1, mmxmn, fempy_example) through it; watch the memory graph.
- Keep notes for the educational write-up as you go.

## Deliverable at full deployment

A full educational breakdown of the whole process, kept **separate from this repo**, at
`../deployment-guide/` (i.e. `/Users/elvissmith/Desktop/SWE/deployment-guide/`, NOT inside
`FileFold/`). Seed notes live in `../deployment-guide/NOTES.md`; append learnings there as
they happen so the final write-up is easy. Write it for a learner who has never deployed an
app: what hosting is, static vs server, containers/Docker, volumes, env vars, health checks,
CI/CD, memory sizing, auth, costs, and what went wrong/right here.

## Also open (not deployment-gated)

- Apple Developer ID signing + notarization for the desktop app ($99/yr) — offered to the
  user 2026-10-12, awaiting their decision. Until then the builds are unsigned (Gatekeeper
  'Open Anyway', SmartScreen 'Run anyway').
- The app shell is not phone-responsive (fixed 220 px sidebar); everything squeezes below
  ~700 px. Fine for desktop/tablet. Pre-existing, not fixed.
