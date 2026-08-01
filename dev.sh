#!/usr/bin/env bash
# Bifrost local dev — hub API on :8000 and the Vite SPA on :5173 (which
# proxies /api to the hub). Ctrl-C tears both down. Hub state lives in
# ./data/ (gitignored), so a local run never touches a real deployment.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

mkdir -p data
[ -d frontend/node_modules ] || (cd frontend && npm install)
(cd hub && uv sync --quiet)

# Kill the whole process group on exit so uvicorn and vite die together.
trap 'trap - INT TERM EXIT; kill 0' INT TERM EXIT

(
  cd hub
  BIFROST_DATA_DIR="$(pwd)/../data" exec uv run uvicorn app.asgi:app \
    --reload --port "${BIFROST_DEV_HUB_PORT:-8000}"
) &

(cd frontend && exec npm run dev) &

wait
