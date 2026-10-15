#!/usr/bin/env bash
# Runs on the server as root, started by deploy.sh through SSM.
# Writes the settings file from SSM, pulls the new image, runs migrations and swaps the
# containers. If the app does not become healthy it goes back to the previous image.
set -euo pipefail
: "${IMAGE:?}" "${DOMAIN:?}" "${ACME_EMAIL:?}" "${PARAM_PATH:?}" "${AWS_REGION:?}" "${LOG_GROUP:?}" "${BUCKET:?}" "${AUTO_STOP_HOURS:?}"
# shellcheck source=compose.sh
. "$(dirname "$0")/compose.sh"

# First boot: wait until the user data has installed Docker.
cloud-init status --wait >/dev/null

write_settings() {
  local secrets
  secrets=$(aws ssm get-parameters-by-path --path "$PARAM_PATH" --with-decryption \
    --query 'Parameters[].[Name,Value]' --output text | while read -r name value; do echo "${name##*/}=$value"; done)
  [[ $(grep -c . <<<"$secrets") -eq 4 ]] || {
    echo "error: expected 4 secrets under $PARAM_PATH in SSM" >&2
    exit 1
  }
  # Root-only file; never printed.
  (
    umask 077
    printf '%s\n' "$secrets" \
      "IMAGE=$IMAGE" "DOMAIN=$DOMAIN" "ACME_EMAIL=$ACME_EMAIL" \
      "AWS_REGION=$AWS_REGION" "LOG_GROUP=$LOG_GROUP" "BUCKET=$BUCKET" >"$APP_DIR/.env.new"
  )
  mv "$APP_DIR/.env.new" "$APP_DIR/.env"
}

set_image() {
  sed -i "s|^IMAGE=.*|IMAGE=$1|" "$APP_DIR/.env"
}

previous=$(sed -n 's/^IMAGE=//p' "$APP_DIR/.env" 2>/dev/null || true)
write_settings

aws ecr get-login-password | docker login --username AWS --password-stdin "${IMAGE%%/*}" >/dev/null
compose pull --quiet
compose up -d --wait db
compose run --rm --no-deps app alembic upgrade head
# Demo data and the two logins on a fresh database only; never touches existing data.
compose run --rm --no-deps app python -m scripts.seed --if-empty

if ! compose up -d --remove-orphans --wait --wait-timeout 180; then
  if [[ -n "$previous" && "$previous" != "$IMAGE" ]]; then
    set_image "$previous"
    compose up -d --remove-orphans --wait --wait-timeout 180 || true
    echo "error: $IMAGE did not become healthy; rolled back to $previous" >&2
  else
    echo "error: $IMAGE did not become healthy" >&2
  fi
  compose logs --tail 50 app >&2 || true
  exit 1
fi

# Nightly backup at 03:00 India time (21:30 UTC).
echo "30 21 * * * root bash $APP_DIR/release/backup.sh >> /var/log/acme-backup.log 2>&1" >/etc/cron.d/acme-backup
# Every boot schedules the auto-stop, also when the wake page started the server.
bash "$(dirname "$0")/boot-auto-stop.sh" "$AUTO_STOP_HOURS"
docker image prune -af --filter until=72h >/dev/null
echo "Running $IMAGE"
