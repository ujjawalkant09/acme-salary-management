#!/usr/bin/env bash
# A throwaway copy of ACME Pay for the as-user oracles: its own database (acme_oracles_<port> on
# the local Postgres, 1,000 seeded employees), its own file storage, its own random secret and
# demo passwords, and no rate limit. It never touches the `acme` database or backend/.env, so it
# also works in a fresh worktree.
#
#   app.sh start              build the UI, create and seed a new database, start the app
#   app.sh run [args…]        run the oracles against it, data changes allowed (default: all)
#   app.sh probe <path> [..]  show what a person sees on a page (see probe.py)
#   app.sh status             is it running?
#   app.sh stop               stop it
set -euo pipefail

ROOT=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
SKILL_DIR=$(cd "$(dirname "$0")/.." && pwd)
PORT=${ORACLE_APP_PORT:-8100}
TMP=${TMPDIR:-/tmp}
DATA=${ORACLE_APP_DIR:-${TMP%/}/acme-oracles-$PORT}
PID_FILE=$DATA/app.pid
ENV_FILE=$DATA/oracle.env

die() { echo "app.sh: $*" >&2; exit 1; }

running() {
  [[ -f $PID_FILE ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null
}

port_in_use() {
  python3 -c "import socket, sys; sys.exit(socket.socket().connect_ex(('127.0.0.1', $PORT)) != 0)"
}

stop() {
  if running; then
    kill "$(cat "$PID_FILE")"
    for _ in $(seq 1 20); do running || break; sleep 0.25; done
    echo "stopped the app on port $PORT"
  else
    echo "the app is not running"
  fi
  rm -f "$PID_FILE"
}

start() {
  stop >/dev/null
  if port_in_use; then die "port $PORT is in use by another program; set ORACLE_APP_PORT"; fi

  rm -rf "$DATA"
  mkdir -p "$DATA/storage"
  chmod 700 "$DATA"
  local admin viewer secret
  admin=$(openssl rand -hex 12)
  viewer=$(openssl rand -hex 12)
  secret=$(openssl rand -hex 24)
  (
    umask 077
    printf 'export %s\n' "ORACLE_BASE_URL=http://localhost:$PORT" \
      "DEMO_ADMIN_PASSWORD=$admin" "DEMO_VIEWER_PASSWORD=$viewer" >"$ENV_FILE"
  )

  echo "building the UI…"
  (cd "$ROOT/frontend" && { [[ -d node_modules ]] || npm ci --silent; } && npm run build) \
    >"$DATA/build.log" 2>&1 || die "the UI build failed, see $DATA/build.log"

  local db="acme_oracles_$PORT"
  echo "creating the database ${db}…"
  (cd "$ROOT" && docker compose up -d --wait db &&
    docker compose exec -T db psql -U acme -d postgres -q \
      -c "DROP DATABASE IF EXISTS $db WITH (FORCE)" -c "CREATE DATABASE $db") \
    >"$DATA/db.log" 2>&1 || die "could not create the database (is Docker running?), see $DATA/db.log"

  export DATABASE_URL="postgresql+psycopg://acme:acme@localhost:5432/$db" STORAGE_DIR="$DATA/storage" \
    SECRET_KEY="$secret" SESSION_COOKIE_SECURE=false RATE_LIMIT_ENABLED=false \
    FRONTEND_DIST="$ROOT/frontend/dist" DEMO_ADMIN_PASSWORD="$admin" DEMO_VIEWER_PASSWORD="$viewer"
  cd "$ROOT/backend"
  echo "migrating and seeding the database…"
  {
    uv sync --frozen --quiet
    .venv/bin/alembic upgrade head
    .venv/bin/python -m scripts.seed --count 1000
  } >"$DATA/setup.log" 2>&1 || die "the database setup failed, see $DATA/setup.log"

  nohup .venv/bin/uvicorn app.main:app --port "$PORT" >"$DATA/app.log" 2>&1 &
  echo $! >"$PID_FILE"
  for _ in $(seq 1 60); do
    if curl -fs "http://localhost:$PORT/api/v1/health" >/dev/null; then
      echo "the app is up on http://localhost:$PORT (log: $DATA/app.log)"
      return
    fi
    running || break
    sleep 0.5
  done
  tail -20 "$DATA/app.log" >&2
  die "the app did not start"
}

need_app() {
  running || die "the app is not running; start it with: $0 start"
  # shellcheck source=/dev/null
  source "$ENV_FILE"
}

case "${1:-}" in
  start) start ;;
  stop) stop ;;
  status)
    if running; then
      echo "running on http://localhost:$PORT (data: $DATA)"
    else
      echo "not running"
      exit 1
    fi
    ;;
  run)
    need_app
    shift
    cd "$ROOT/e2e"
    ORACLE_ALLOW_WRITES=1 uv run python oracle_kit.py "${@:-all}"
    ;;
  probe)
    need_app
    shift
    cd "$ROOT/e2e"
    uv run python "$SKILL_DIR/scripts/probe.py" "$@"
    ;;
  *) die "usage: app.sh start | run [feature ids…] | probe <path> [--as role] [--click name…] | status | stop" ;;
esac
