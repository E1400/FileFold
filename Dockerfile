FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN pip install --no-cache-dir uv

WORKDIR /app

# Dependency files first — Docker layer caches these until they change
COPY pyproject.toml uv.lock README.md ./
COPY src/ ./src/

# Production deps only: no pyside6, no pytest/httpx/pyinstaller
RUN uv sync --no-dev

# Persistent volume mount point for workspace storage
RUN mkdir -p /data/workspaces
ENV FILEFOLD_WORKSPACE_DIR=/data/workspaces

EXPOSE 8000

# HOST and PORT can be overridden by Railway (PORT is set automatically)
CMD ["sh", "-c", "uv run filefold serve --host ${FILEFOLD_HOST:-0.0.0.0}"]
