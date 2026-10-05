# Production image for a real host (Railway, Fly, a VM, ...). During development the app is
# served as a static site from GitHub Pages instead; see docs/RAILWAY.md for the switch.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy

RUN pip install --no-cache-dir uv

WORKDIR /app

# Dependencies first: this layer is cached until pyproject.toml or uv.lock change.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

# Then the code (including the web UI under src/filefold/web)
COPY src/ ./src/
RUN uv sync --frozen --no-dev

# Run the installed script directly. `uv run` would re-sync the dev dependency group
# (pytest, pyinstaller, playwright, ...) every time the container starts.
ENV PATH="/app/.venv/bin:$PATH"

# Persistent volume mount point for workspace storage (attach a volume at /data)
RUN mkdir -p /data/workspaces
ENV FILEFOLD_WORKSPACE_DIR=/data/workspaces

EXPOSE 8000

# PORT is set automatically by Railway; FILEFOLD_HOST can override the bind address.
# Optional: FILEFOLD_MAX_UPLOAD_MB caps a single upload (unset = unlimited).
CMD ["sh", "-c", "filefold serve --host ${FILEFOLD_HOST:-0.0.0.0}"]
