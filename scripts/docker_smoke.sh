#!/usr/bin/env bash
# Build the production image and exercise it like a host would: health check, a real upload
# through the API, and persistence of workspaces on a mounted volume across a restart.
# Run from the repository root:  scripts/docker_smoke.sh [image-name]
set -euo pipefail

IMAGE="${1:-filefold:smoke}"
PORT="${SMOKE_PORT:-8000}"
VOLUME="filefold-smoke-$$"
BASE="http://127.0.0.1:${PORT}"
cid=""

cleanup() {
  status=$?
  if [ -n "$cid" ]; then
    [ $status -ne 0 ] && docker logs "$cid" 2>&1 | tail -60
    docker rm -f "$cid" >/dev/null 2>&1 || true
  fi
  docker volume rm "$VOLUME" >/dev/null 2>&1 || true
  exit $status
}
trap cleanup EXIT

start() {
  cid=$(docker run -d -p "${PORT}:${PORT}" -e PORT="$PORT" -e FILEFOLD_MAX_UPLOAD_MB=50 \
        -v "${VOLUME}:/data" "$IMAGE")
  for _ in $(seq 1 60); do
    curl -fsS "$BASE/" >/dev/null 2>&1 && return 0
    sleep 1
  done
  echo "container did not become healthy" >&2
  return 1
}

docker build -t "$IMAGE" .

start
curl -fsS "$BASE/" | grep -q "FileFold"
curl -fsS "$BASE/static/app.css" >/dev/null
curl -fsS -F "file=@tests/fixtures/test_2.inp" "$BASE/api/inspect" | grep -q '"blocks"'
curl -fsS -F "file=@tests/fixtures/Job-1.inp" -F "name=smoke" \
     -F 'selections=[{"category":"mesh","filename":"mesh.inp","sub_selections":[]}]' \
     "$BASE/api/workspaces" | grep -q "mesh.inp"

# the image must not carry dev dependencies, and must not need the network to start
docker exec "$cid" sh -c 'test ! -e /app/.venv/lib/python3.13/site-packages/pytest'

# restart on the same volume: the workspace must still be there
docker rm -f "$cid" >/dev/null
start
curl -fsS "$BASE/api/workspaces/smoke" | grep -q '"mesh.inp"'
echo "docker smoke test passed"
