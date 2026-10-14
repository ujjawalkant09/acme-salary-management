# shellcheck shell=bash
# Sourced by the server scripts: the one place that knows where the settings and compose file live.
export PATH="$PATH:/snap/bin"
APP_DIR=/opt/acme

compose() {
  docker compose --project-name acme --env-file "$APP_DIR/.env" -f "$APP_DIR/release/docker-compose.yml" "$@"
}
