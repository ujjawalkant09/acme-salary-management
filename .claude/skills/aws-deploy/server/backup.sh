#!/usr/bin/env bash
# Copies the database and uploaded files to S3 (backups/ is kept 14 days).
# Runs nightly from cron, before every server.sh stop and before an auto-stop.
set -euo pipefail
# shellcheck source=compose.sh
. "$(dirname "$0")/compose.sh"

bucket=$(sed -n 's/^BUCKET=//p' "$APP_DIR/.env")
stamp=$(date -u +%Y%m%dT%H%M%SZ)
compose exec -T db pg_dump -U acme -Fc acme | aws s3 cp - "s3://$bucket/backups/$stamp/db.dump"
compose exec -T app tar -C /data -czf - storage | aws s3 cp - "s3://$bucket/backups/$stamp/files.tgz"
echo "Backed up to s3://$bucket/backups/$stamp/"
