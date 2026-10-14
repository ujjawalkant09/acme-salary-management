#!/usr/bin/env bash
# auto-stop.sh <hours>: back up, then stop this server after <hours>; 0 turns auto-stop off.
# Replaces any earlier schedule. Shutting down from inside stops (not deletes) an EC2 server.
set -euo pipefail
hours=${1:?usage: auto-stop.sh <hours>}
[[ "$hours" =~ ^[0-9]+$ ]] || {
  echo "error: hours must be a whole number" >&2
  exit 1
}

systemctl stop acme-autostop.timer 2>/dev/null || true
systemctl reset-failed acme-autostop.service 2>/dev/null || true

if ((hours == 0)); then
  echo "Auto-stop is off: run server.sh stop when you are done"
  exit 0
fi
systemd-run --quiet --unit acme-autostop --on-active="${hours}h" \
  /bin/sh -c "bash /opt/acme/release/backup.sh; shutdown -h now"
echo "Server will back up and stop itself at $(date -u -d "+$hours hours" '+%H:%M UTC')"
