#!/usr/bin/env bash

# shellcheck source=lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

main() {
  [[ -t 0 && -t 1 ]] || die "run this yourself in a terminal; it never prints passwords into captured output"
  load_config
  require_tools aws
  local role
  for role in ADMIN VIEWER; do
    printf 'HR %-7s password: ' "$role"
    aws ssm get-parameter --name "$PARAM_PATH/DEMO_${role}_PASSWORD" --with-decryption \
      --query Parameter.Value --output text
  done
  # Share this link to let someone start the stopped demo; the code after # never reaches a server.
  printf 'Wake link:  https://%s/#code=' "$WAKE_DOMAIN"
  aws ssm get-parameter --name "$PARAM_PATH/wake/WAKE_CODE" --with-decryption --query Parameter.Value --output text
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
