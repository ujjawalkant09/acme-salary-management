#!/usr/bin/env bash
# Deletes everything deploy.sh created: the server, the database, uploaded files, backups,
# images, secrets and the DNS record. Cannot be undone. Asks you to type the domain to confirm,
# and only runs in your own terminal.

# shellcheck source=lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

main() {
  [[ -t 0 && -t 1 ]] || die "run this yourself in a terminal; it needs your typed confirmation"
  load_config
  require_tools aws jq curl
  check_identity
  stack_exists || die "stack $STACK_NAME does not exist"

  echo "This permanently deletes the server, the database, all files and all backups for $DOMAIN."
  local answer
  read -r -p "Type the domain ($DOMAIN) to confirm: " answer
  [[ "$answer" == "$DOMAIN" ]] || die "confirmation did not match; nothing deleted"

  local bucket names=() name
  bucket=$(stack_output BucketName)
  log "Emptying bucket $bucket"
  aws s3 rm --recursive --quiet "s3://$bucket"
  log "Deleting stack $STACK_NAME (takes a few minutes)"
  aws cloudformation delete-stack --stack-name "$STACK_NAME"
  aws cloudformation wait stack-delete-complete --stack-name "$STACK_NAME"

  for name in "${SECRET_NAMES[@]}"; do names+=("$PARAM_PATH/$name"); done
  aws ssm delete-parameters --names "${names[@]}" >/dev/null

  split_domain
  log "Removing DNS record $DOMAIN"
  godaddy DELETE "/records/A/$DNS_RECORD" >/dev/null || echo "warning: remove the A record '$DNS_RECORD' in GoDaddy yourself" >&2
  log "Done"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
