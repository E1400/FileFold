# Switching to a real host (Railway)

During development FileFold is a **static site on GitHub Pages**: the Python runs inside the
visitor's browser (Pyodide), so it costs nothing but is limited by browser memory (tested to
100 MB decks). This page is the checklist for moving to a server when you want larger decks and
shared access. The server path is kept working all the time:

- CI builds the production image and exercises it on every push (`scripts/docker_smoke.sh`):
  health check, a real upload, no dev dependencies in the image, and workspaces surviving a
  restart on a mounted volume.
- Every browser test runs against **both** the real server and the Pages build.
- `tests/test_deploy_config.py` checks the Dockerfile, `railway.toml` healthcheck, `PORT` /
  `FILEFOLD_WORKSPACE_DIR` handling and that `uv.lock` matches `pyproject.toml`.

## Switch-over checklist

1. **Create the service.** Railway → New Project → Deploy from GitHub repo → `E1400/FileFold`.
   `railway.toml` already points at the `Dockerfile` and the `/` health check.
2. **Attach a volume** mounted at `/data`. Workspaces live in `/data/workspaces`
   (`FILEFOLD_WORKSPACE_DIR`). Without a volume they vanish on every deploy.
3. **Size the memory** (see below) and set the variables:

   | Variable | Purpose |
   |---|---|
   | `PORT` | set by Railway, nothing to do |
   | `FILEFOLD_WORKSPACE_DIR` | already `/data/workspaces` in the image |
   | `FILEFOLD_MAX_UPLOAD_MB` | reject uploads above this size with a clear 413 (recommended) |
   | `FILEFOLD_BASIC_AUTH` | `user:password`, gates the whole app behind one shared password |

4. **Protect it before sharing the URL.** The server has no accounts and every visitor shares one
   workspace folder, so anyone who can open the URL can see, edit and delete everyone's
   workspaces. `FILEFOLD_BASIC_AUTH` is a stop-gap for a private lab or a staging copy. Per-user
   workspaces behind real sign-in are needed before a public launch.
5. **Point the links.** In `docs/index.html` and `README.md` the "Try it online" button goes to
   `app/` (the in-browser build). Change it to the Railway URL, or keep both: the Pages build
   needs no server and works as a free fallback.
6. **Keep or retire Pages.** `.github/workflows/pages.yml` can stay (landing page plus in-browser
   build) or be limited to the landing page.

## Sizing memory

Measured on the server (`uvicorn`, one worker) with synthetic decks made by repeating a real
deck, peak resident memory:

| Deck | Inspect (upload + parse) | Create workspace | Open workspace |
|---|---|---|---|
| 100 MB | about 60 MB | about 570 MB | about 570 MB |
| 200 MB | about 55 MB | about 1.05 GB | about 1.05 GB |

Rule of thumb: **plan for about 5 to 6 times the largest deck during a create or re-split**, plus
about 50 MB baseline, and multiply by the number of simultaneous creates you expect. Inspecting
and opening a workspace no longer scale with deck size (uploads are streamed to disk, files are
hashed in chunks, and read-only parses drop the data lines). Creating and re-splitting still hold
the deck's lines in memory while they rearrange them; making that streaming is the next step if
decks beyond a few hundred MB matter. These are measurements on one machine, so check the real
service's memory graph after the first large upload.

## Known limits of the server build

- One shared workspace folder, no per-user isolation (see step 4).
- A single uvicorn worker, so one long split blocks other requests; add workers or a queue when
  there are several users.
- Workspace files are on the volume. Back it up, or users should rely on **Export ZIP**.
