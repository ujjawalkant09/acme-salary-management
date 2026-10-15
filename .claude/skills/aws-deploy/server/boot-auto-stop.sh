#!/usr/bin/env bash
# boot-auto-stop.sh <hours>: runs auto-stop.sh <hours> on every boot, so the server stops itself
# however it was started (deploy, server.sh start, the wake page or the AWS console).
# The boot run comes before the SSM agent starts, so a schedule sent later through SSM
# (server.sh start <hours>) replaces it.
set -euo pipefail
hours=${1:?usage: boot-auto-stop.sh <hours>}
[[ "$hours" =~ ^[0-9]+$ ]] || {
  echo "error: hours must be a whole number" >&2
  exit 1
}
UNIT_DIR=${UNIT_DIR:-/etc/systemd/system}

cat >"$UNIT_DIR/acme-autostop-on-boot.service" <<EOF
[Unit]
Description=Schedule the ACME demo auto-stop
Before=snap.amazon-ssm-agent.amazon-ssm-agent.service

[Service]
Type=oneshot
ExecStart=/bin/bash /opt/acme/release/auto-stop.sh $hours

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --quiet acme-autostop-on-boot.service
