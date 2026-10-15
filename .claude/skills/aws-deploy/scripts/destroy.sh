#!/usr/bin/env bash
# Deletes everything deploy.sh created: the server, the database, uploaded files, backups,
# images, secrets, the wake page, its certificate and the DNS records. Cannot be undone.
# Asks you to type the domain to confirm, and only runs in your own terminal.

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

  local bucket names=() name cert
  bucket=$(stack_output BucketName)
  split_domain
  read -r cert _ < <(wake_certificate) || true
  [[ "$cert" != "None" ]] || cert=""
  # The record that proves the domain to ACM; read now, while the certificate still exists.
  VALIDATION_NAME=""
  [[ -z "$cert" ]] || validation_record "$cert" || VALIDATION_NAME=""
  log "Emptying bucket $bucket"
  aws s3 rm --recursive --quiet "s3://$bucket"
  log "Deleting stack $STACK_NAME (takes a few minutes)"
  aws cloudformation delete-stack --stack-name "$STACK_NAME"
  aws cloudformation wait stack-delete-complete --stack-name "$STACK_NAME"

  for name in "${SECRET_NAMES[@]}"; do names+=("$PARAM_PATH/$name"); done
  aws ssm delete-parameters --names "${names[@]}" >/dev/null

  if [[ -n "$cert" ]]; then
    log "Deleting the certificate for $WAKE_DOMAIN"
    aws acm delete-certificate --certificate-arn "$cert" ||
      echo "warning: delete the certificate for $WAKE_DOMAIN in the ACM console yourself" >&2
  fi

  log "Removing the DNS records"
  remove_record A "$DNS_RECORD"
  remove_record CNAME "wake.$DNS_RECORD"
  [[ -z "$VALIDATION_NAME" ]] || remove_record CNAME "${VALIDATION_NAME%".$DNS_ZONE."}"
  log "Done"
}

# remove_record <type> <name in the zone>
remove_record() {
  godaddy DELETE "/records/$1/$2" >/dev/null || echo "warning: remove the $1 record '$2' in GoDaddy yourself" >&2
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
