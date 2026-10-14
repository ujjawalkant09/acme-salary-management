# shellcheck shell=bash disable=SC2034  # variables set here are used by the scripts that source this file
# Shared helpers for the aws-deploy scripts. Sourced, never run directly.
#
# Credential rules followed everywhere:
#   - AWS access comes only from the named profile in config.env (keys stay in ~/.aws).
#   - Secrets never appear in a command's arguments, a variable that gets printed, or a log.
#     They travel through pipes (stdin) only.

set -euo pipefail

SKILL_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
REPO_ROOT=${REPO_ROOT:-$(git -C "$SKILL_DIR" rev-parse --show-toplevel)}
CONFIG_FILE=${CONFIG_FILE:-$SKILL_DIR/config.env}
SECRETS_ENV_FILE=${SECRETS_ENV_FILE:-$REPO_ROOT/.env}
SECRET_NAMES=(SECRET_KEY POSTGRES_PASSWORD DEMO_ADMIN_PASSWORD DEMO_VIEWER_PASSWORD)

die() {
  echo "error: $*" >&2
  exit 1
}

log() { echo "==> $*"; }

load_config() {
  [[ -f "$CONFIG_FILE" ]] || die "missing $CONFIG_FILE (copy config.env.example and fill it in)"
  # shellcheck source=/dev/null
  . "$CONFIG_FILE"
  local name
  for name in AWS_PROFILE AWS_REGION STACK_NAME DOMAIN ALERT_EMAIL BUDGET_USD AUTO_STOP_HOURS; do
    [[ -n "${!name:-}" ]] || die "$name is empty in $CONFIG_FILE"
  done
  [[ "$BUDGET_USD" =~ ^[1-9][0-9]*$ ]] || die "BUDGET_USD must be a whole number of dollars above 0"
  [[ "$AUTO_STOP_HOURS" =~ ^[0-9]+$ ]] || die "AUTO_STOP_HOURS must be a whole number (0 = never)"
  # Keys exported in the shell would silently win over the profile and could point at another account.
  unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN
  export AWS_PROFILE AWS_REGION
  PARAM_PATH="/$STACK_NAME"
}

require_tools() {
  local tool
  for tool in "$@"; do
    command -v "$tool" >/dev/null || die "$tool is not installed"
  done
}

# Prints the account and user the profile signs in as (neither is a secret) and refuses root keys.
check_identity() {
  local arn
  arn=$(aws sts get-caller-identity --query Arn --output text) ||
    die "AWS profile '$AWS_PROFILE' does not work; run: aws configure --profile $AWS_PROFILE"
  [[ "$arn" != *":root" ]] || die "refusing to use root account keys; create an IAM user (see SKILL.md)"
  log "AWS identity: $arn"
}

stack_exists() {
  aws cloudformation describe-stacks --stack-name "$STACK_NAME" >/dev/null 2>&1
}

stack_output() {
  aws cloudformation describe-stacks --stack-name "$STACK_NAME" \
    --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" --output text
}

instance_state() {
  aws ec2 describe-instances --instance-ids "$1" \
    --query 'Reservations[0].Instances[0].State.Name' --output text
}

# retry <attempts> <seconds between> <command...>
retry() {
  local attempts=$1 delay=$2 i
  shift 2
  for ((i = 1; i <= attempts; i++)); do
    "$@" && return 0
    ((i < attempts)) && sleep "$delay"
  done
  return 1
}

ssm_online() {
  [[ $(aws ssm describe-instance-information --filters "Key=InstanceIds,Values=$1" \
    --query 'InstanceInformationList[0].PingStatus' --output text) == "Online" ]]
}

wait_for_ssm() {
  log "Waiting for the server to accept commands (SSM)"
  retry 60 10 ssm_online "$1" || die "server $1 did not come online in SSM within 10 minutes"
}

# run_remote <instance-id> <shell commands...>
# Runs commands as root on the server through SSM and prints their output.
# Never pass secrets here: SSM keeps the command text in its history.
run_remote() {
  local instance=$1 command_id status
  shift
  command_id=$(aws ssm send-command --instance-ids "$instance" --document-name AWS-RunShellScript \
    --parameters "$(jq -cn '{commands: $ARGS.positional, executionTimeout: ["1800"]}' --args "$@")" \
    --query Command.CommandId --output text)
  status=$(remote_status "$instance" "$command_id")
  while [[ "$status" == "Pending" || "$status" == "InProgress" || "$status" == "Delayed" ]]; do
    sleep 5
    status=$(remote_status "$instance" "$command_id")
  done
  aws ssm get-command-invocation --instance-id "$instance" --command-id "$command_id" \
    --query '[StandardOutputContent, StandardErrorContent]' --output text
  [[ "$status" == "Success" ]] || {
    echo "error: remote command finished with status: $status" >&2
    return 1
  }
}

remote_status() {
  aws ssm get-command-invocation --instance-id "$1" --command-id "$2" \
    --query Status --output text 2>/dev/null || echo Pending
}

# schedule_auto_stop <instance-id> <hours>: back up and stop the server after <hours>; 0 = never.
# Replaces any earlier schedule, so it also extends a running demo.
schedule_auto_stop() {
  run_remote "$1" "bash /opt/acme/release/auto-stop.sh $2"
}

site_healthy() {
  curl -fsS --max-time 10 -o /dev/null "https://$DOMAIN/api/v1/health"
}

wait_for_site() {
  log "Waiting for https://$DOMAIN to answer (the first certificate can take a minute)"
  retry 30 10 site_healthy || die "https://$DOMAIN/api/v1/health did not answer within 5 minutes"
  log "Live: https://$DOMAIN"
}

# GoDaddy accepts an API key pair ("sso-key KEY:SECRET") or a personal access token ("Bearer TOKEN").
# The value is read from .env on each call and handed to curl on stdin, so it is never in a variable
# that outlives the call or in curl's arguments.
godaddy_token() {
  [[ -f "$SECRETS_ENV_FILE" ]] || die "missing $SECRETS_ENV_FILE with GODADDY_API=TOKEN or KEY:SECRET"
  local line
  line=$(grep -E '^GODADDY_API=' "$SECRETS_ENV_FILE" | tail -n 1 || true)
  line=${line#GODADDY_API=}
  line=${line%\"}
  line=${line#\"}
  [[ -n "$line" && "$line" != *[[:space:]]* ]] || die "GODADDY_API in $SECRETS_ENV_FILE is empty or has spaces"
  if [[ "$line" == ?*:?* ]]; then
    printf 'Authorization: sso-key %s\n' "$line"
  else
    printf 'Authorization: Bearer %s\n' "$line"
  fi
}

# godaddy <method> <path> [json body]
godaddy() {
  local method=$1 path=$2 body=${3:-}
  local args=(-fsS --max-time 20 -X "$method" -H @- -H 'Accept: application/json')
  [[ -n "$body" ]] && args+=(-H 'Content-Type: application/json' --data "$body")
  godaddy_token | curl "${args[@]}" "https://api.godaddy.com/v1/domains/$DNS_ZONE$path"
}

# acme.docrelay.in -> record "acme" in zone "docrelay.in"
split_domain() {
  [[ "$DOMAIN" == *.*.* ]] || die "DOMAIN must be a subdomain like acme.docrelay.in"
  DNS_RECORD=${DOMAIN%%.*}
  DNS_ZONE=${DOMAIN#*.}
}
