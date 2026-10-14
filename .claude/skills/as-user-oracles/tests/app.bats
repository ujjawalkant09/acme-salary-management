#!/usr/bin/env bats
# app.sh without building or starting anything: argument handling, a stopped app, a busy port.

setup() {
  APP="$BATS_TEST_DIRNAME/../scripts/app.sh"
  export ORACLE_APP_DIR="$BATS_TEST_TMPDIR/data"
  ORACLE_APP_PORT=$(python3 -c "import socket; s = socket.socket(); s.bind(('127.0.0.1', 0)); print(s.getsockname()[1])")
  export ORACLE_APP_PORT
}

teardown() {
  if [[ -n "${SERVER_PID:-}" ]]; then
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
}

@test "no command prints the usage and fails" {
  run "$APP"
  [ "$status" -eq 1 ]
  [[ "$output" == *"usage: app.sh start | run"* ]]
}

@test "status, run and probe refuse when the app is not running" {
  run "$APP" status
  [ "$status" -eq 1 ]
  [ "$output" = "not running" ]
  run "$APP" run login
  [ "$status" -eq 1 ]
  [[ "$output" == *"the app is not running; start it with"* ]]
  run "$APP" probe /people
  [ "$status" -eq 1 ]
}

@test "stop is safe when nothing runs, and clears a stale pid file" {
  mkdir -p "$ORACLE_APP_DIR"
  echo 999999 >"$ORACLE_APP_DIR/app.pid"
  run "$APP" stop
  [ "$status" -eq 0 ]
  [ "$output" = "the app is not running" ]
  [ ! -e "$ORACLE_APP_DIR/app.pid" ]
}

@test "start refuses a port another program uses, before deleting anything" {
  mkdir -p "$ORACLE_APP_DIR"
  touch "$ORACLE_APP_DIR/keep-me"
  python3 -m http.server "$ORACLE_APP_PORT" --bind 127.0.0.1 >/dev/null 2>&1 &
  SERVER_PID=$!
  for _ in $(seq 1 40); do
    python3 -c "import socket, sys; sys.exit(socket.socket().connect_ex(('127.0.0.1', $ORACLE_APP_PORT)))" && break
    sleep 0.1
  done
  run "$APP" start
  [ "$status" -eq 1 ]
  [[ "$output" == *"port $ORACLE_APP_PORT is in use by another program"* ]]
  [ -e "$ORACLE_APP_DIR/keep-me" ]
}
