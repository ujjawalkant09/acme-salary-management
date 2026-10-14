#!/usr/bin/env bash
# Shows the two demo passwords. Only in your own terminal: it refuses when its output
# is captured (by Claude, a pipe or a file), so the passwords never leave your screen.

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
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
