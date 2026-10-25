#!/usr/bin/env bash
# Run the whole app locally: API (:8000), worker and frontend (:5173). Ctrl+C stops all three.
#   ./dev.sh           install, migrate, seed an empty database, then start
#   ./dev.sh --fast    skip install/migrate/seed and just start
#
# All three run in this one terminal; each output line is labelled [api], [worker] or [web].
# To run them in separate terminals instead, start one command in each:
#   cd backend && uv run uvicorn app.main:app --reload --port 8000
#   cd backend && uv run python -m app.worker
#   cd frontend && npm run dev
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"

for tool in uv npm; do
  command -v "$tool" >/dev/null || { echo "Missing '$tool'. See README.md 'Run it locally'." >&2; exit 1; }
done

if [[ ! -f "$BACKEND/.env" ]]; then
  cp "$BACKEND/.env.example" "$BACKEND/.env"
  echo "Created backend/.env from .env.example. Set SECRET_KEY and the two demo passwords, then run again." >&2
  exit 1
fi

if [[ "${1:-}" != "--fast" ]]; then
  echo "==> Backend: install, migrate, seed"
  (cd "$BACKEND" && uv sync && uv run alembic upgrade head && uv run python -m scripts.seed --if-empty)
  echo "==> Frontend: install"
  (cd "$FRONTEND" && npm install)
fi

# Stop every child process when this script exits (Ctrl+C).
trap 'trap - EXIT; kill 0' INT TERM EXIT

(cd "$BACKEND" && uv run uvicorn app.main:app --reload --port 8000 2>&1 | sed 's/^/[api]    /') &
(cd "$BACKEND" && uv run python -m app.worker 2>&1 | sed 's/^/[worker] /') &
(cd "$FRONTEND" && npm run dev 2>&1 | sed 's/^/[web]    /') &

echo "==> App:  http://localhost:5173   API docs: http://localhost:8000/api/v1/docs   (Ctrl+C to stop)"
wait
