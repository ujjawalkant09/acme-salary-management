#!/usr/bin/env bash
# Turn the demo server on and off to save money. The address and data stay the same.
#
#   server.sh status
#   server.sh start [hours]   start (or extend); stops itself after [hours] (default AUTO_STOP_HOURS, 0 = never)
#   server.sh stop            back up the database and files to S3, then stop
#   server.sh stop --skip-backup

# shellcheck source=lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

status() {
  local instance=$1
  echo "Server:  $instance ($(instance_state "$instance"))"
  echo "Address: https://$DOMAIN ($(stack_output PublicIp))"
}

start() {
  local instance=$1 hours=$2
  [[ "$hours" =~ ^[0-9]+$ ]] || die "hours must be a whole number"
  ensure_running "$instance"
  wait_for_site
  schedule_auto_stop "$instance" "$hours"
}

stop() {
  local instance=$1 skip_backup=$2
  case "$(instance_state "$instance")" in
    stopped)
      log "Server is already stopped"
      return
      ;;
    running) ;;
    *) die "the server is $(instance_state "$instance"); try again in a minute" ;;
  esac
  if [[ "$skip_backup" != "--skip-backup" ]]; then
    log "Backing up to S3"
    run_remote "$instance" "bash /opt/acme/release/backup.sh" ||
      die "backup failed, server left running; fix it or run: server.sh stop --skip-backup"
  fi
  log "Stopping the server"
  aws ec2 stop-instances --instance-ids "$instance" >/dev/null
  aws ec2 wait instance-stopped --instance-ids "$instance"
  log "Stopped. While stopped you pay only for the disk and the address."
}

main() {
  local action=${1:-}
  load_config
  require_tools aws jq curl
  stack_exists || die "nothing deployed yet; run deploy.sh first"
  local instance
  instance=$(stack_output InstanceId)
  case "$action" in
    status) status "$instance" ;;
    start) start "$instance" "${2:-$AUTO_STOP_HOURS}" ;;
    stop) stop "$instance" "${2:-}" ;;
    *) die "usage: server.sh status | start [hours] | stop [--skip-backup]" ;;
  esac
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
