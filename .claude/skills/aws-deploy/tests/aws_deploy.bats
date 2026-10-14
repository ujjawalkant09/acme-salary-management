#!/usr/bin/env bats
# Tests for the aws-deploy scripts. AWS, curl and dig are stubs (tests/stubs): no network, no account.

SKILL=$(cd "$BATS_TEST_DIRNAME/.." && pwd)
GODADDY_SECRET_PART=s3cr3tPart

setup() {
  export PATH="$SKILL/tests/stubs:$PATH"
  export STUB_LOG="$BATS_TEST_TMPDIR/calls.log" STUB_STDIN_LOG="$BATS_TEST_TMPDIR/stdin.log"
  : >"$STUB_LOG"
  : >"$STUB_STDIN_LOG"
  : >"$STUB_STDIN_LOG.files"
  export CONFIG_FILE="$BATS_TEST_TMPDIR/config.env" SECRETS_ENV_FILE="$BATS_TEST_TMPDIR/.env"
  write_config
  echo "GODADDY_API=keyPart:$GODADDY_SECRET_PART" >"$SECRETS_ENV_FILE"
}

write_config() {
  cat >"$CONFIG_FILE" <<EOF
AWS_PROFILE=acme
AWS_REGION=ap-south-1
STACK_NAME=acme-salary
DOMAIN=acme.docrelay.in
ALERT_EMAIL=${ALERT_EMAIL-hr@example.com}
BUDGET_USD=${BUDGET_USD-10}
AUTO_STOP_HOURS=4
EOF
}

# in_deploy <commands>: source deploy.sh (functions only) and run commands after loading config.
in_deploy() {
  run bash -c ". '$SKILL/scripts/deploy.sh' && load_config && $1"
}

# not_in <pattern> <file>: fails the test if the pattern is in the file.
# (A bare "! grep" line does not fail a bats test unless it is the last line.)
not_in() {
  if grep -q -- "$1" "$2"; then
    echo "unexpected: '$1' found in $2"
    return 1
  fi
}

line_of() {
  grep -n -- "$1" "$STUB_LOG" | head -n 1 | cut -d: -f1
}

# --- config and identity ---

@test "config: an empty required value is rejected" {
  ALERT_EMAIL= write_config
  in_deploy "true"
  [ "$status" -eq 1 ]
  [[ "$output" == *"ALERT_EMAIL is empty"* ]]
}

@test "config: a budget of 0 is rejected" {
  BUDGET_USD=0 write_config
  in_deploy "true"
  [ "$status" -eq 1 ]
  [[ "$output" == *"BUDGET_USD must be"* ]]
}

@test "config: exported AWS keys are dropped so only the profile is used" {
  AWS_ACCESS_KEY_ID=AKIAFAKE AWS_SECRET_ACCESS_KEY=fake in_deploy 'echo "${AWS_ACCESS_KEY_ID:-unset} $AWS_PROFILE"'
  [ "$status" -eq 0 ]
  [ "$output" = "unset acme" ]
}

@test "config: in GitHub Actions the OIDC keys are kept and no profile is needed" {
  sed -i.bak '/^AWS_PROFILE=/d' "$CONFIG_FILE"
  GITHUB_ACTIONS=true AWS_ACCESS_KEY_ID=ASIAOIDC in_deploy 'echo "$AWS_ACCESS_KEY_ID ${AWS_PROFILE:-none}"'
  [ "$status" -eq 0 ]
  [ "$output" = "ASIAOIDC none" ]
}

@test "config: outside GitHub Actions a missing profile is rejected" {
  sed -i.bak '/^AWS_PROFILE=/d' "$CONFIG_FILE"
  in_deploy "true"
  [ "$status" -eq 1 ]
  [[ "$output" == *"AWS_PROFILE is empty"* ]]
}

@test "identity: root account keys are refused" {
  STUB_ARN=arn:aws:iam::123456789012:root in_deploy "check_identity"
  [ "$status" -eq 1 ]
  [[ "$output" == *"refusing to use root"* ]]
}

@test "identity: an IAM user is accepted" {
  in_deploy "check_identity"
  [ "$status" -eq 0 ]
  [[ "$output" == *"user/acme-deployer"* ]]
}

# --- GoDaddy DNS ---

@test "godaddy: a KEY:SECRET pair is sent as sso-key" {
  in_deploy "godaddy_token"
  [ "$status" -eq 0 ]
  [ "$output" = "Authorization: sso-key keyPart:$GODADDY_SECRET_PART" ]
}

@test "godaddy: a personal access token is sent as Bearer" {
  echo 'GODADDY_API="patToken123"' >"$SECRETS_ENV_FILE"
  in_deploy "godaddy_token"
  [ "$status" -eq 0 ]
  [ "$output" = "Authorization: Bearer patToken123" ]
}

@test "godaddy: an empty token is rejected" {
  echo "GODADDY_API=" >"$SECRETS_ENV_FILE"
  in_deploy "godaddy_token"
  [ "$status" -eq 1 ]
  [[ "$output" == *"empty or has spaces"* ]]
}

@test "godaddy: a missing .env is reported" {
  rm "$SECRETS_ENV_FILE"
  in_deploy "godaddy_token"
  [ "$status" -eq 1 ]
  [[ "$output" == *"missing"* ]]
}

@test "dns: a wrong record is updated and the token never appears in command arguments" {
  STUB_DIG_IP_BEFORE=198.51.100.1 STUB_CURL_OUT='[{"data":"198.51.100.1"}]' in_deploy "ensure_dns 203.0.113.10"
  [ "$status" -eq 0 ]
  grep -q -- "-X PUT .*records/A/acme" "$STUB_LOG"
  grep -q '"data":"203.0.113.10"' "$STUB_LOG"
  not_in "$GODADDY_SECRET_PART" "$STUB_LOG"
  grep -q "sso-key keyPart:$GODADDY_SECRET_PART" "$STUB_STDIN_LOG"
}

@test "dns: a record that already resolves is left alone without calling GoDaddy" {
  rm "$SECRETS_ENV_FILE"
  in_deploy "ensure_dns 203.0.113.10"
  [ "$status" -eq 0 ]
  not_in "curl" "$STUB_LOG"
  [[ "$output" == *"already points to"* ]]
}

@test "dns: a bare domain without a subdomain is rejected" {
  sed -i.bak 's/^DOMAIN=.*/DOMAIN=docrelay.in/' "$CONFIG_FILE"
  in_deploy "split_domain"
  [ "$status" -eq 1 ]
  [[ "$output" == *"must be a subdomain"* ]]
}

# --- secrets ---

@test "secrets: only missing secrets are created, with values never in the command" {
  STUB_MISSING="/acme-salary/SECRET_KEY	/acme-salary/DEMO_VIEWER_PASSWORD" in_deploy "ensure_secrets"
  [ "$status" -eq 0 ]
  [ "$(grep -c 'ssm put-parameter' "$STUB_LOG")" -eq 2 ]
  grep -q '"Name":"/acme-salary/SECRET_KEY"' <(jq -c . "$STUB_STDIN_LOG")
  [ "$(jq -s 'map(select(.Type == "SecureString" and (.Value | length) == 64)) | length' "$STUB_STDIN_LOG")" -eq 2 ]
  not_in "--value" "$STUB_LOG"
  not_in "$(jq -rs '.[0].Value' "$STUB_STDIN_LOG")" "$STUB_LOG"
}

@test "secrets: each value is in an owner-only temp file that is deleted after the call" {
  STUB_MISSING="/acme-salary/SECRET_KEY" in_deploy "ensure_secrets"
  [ "$status" -eq 0 ]
  local path mode
  read -r path mode <"$STUB_STDIN_LOG.files"
  [ "$mode" = "drwx------" ]
  [ ! -e "$path" ]
  [ ! -e "$(dirname "$path")" ]
}

@test "secrets: a failed AWS call still deletes the temp file" {
  STUB_MISSING="/acme-salary/SECRET_KEY" STUB_FAIL="ssm put-parameter" in_deploy "ensure_secrets"
  [ "$status" -ne 0 ]
  local path mode
  read -r path mode <"$STUB_STDIN_LOG.files"
  [ ! -e "$(dirname "$path")" ]
}

@test "secrets: re-running with every secret present changes nothing" {
  STUB_MISSING=None in_deploy "ensure_secrets"
  [ "$status" -eq 0 ]
  not_in "ssm put-parameter" "$STUB_LOG"
}

# --- deploy ---

@test "deploy: an unknown option is rejected" {
  run "$SKILL/scripts/deploy.sh" --force
  [ "$status" -eq 1 ]
  [[ "$output" == *"usage: deploy.sh"* ]]
}

@test "deploy: uncommitted changes block the release" {
  local repo="$BATS_TEST_TMPDIR/repo"
  git init -q "$repo"
  git -C "$repo" -c user.email=t@t -c user.name=t commit -q --allow-empty -m init
  touch "$repo/new-file"
  REPO_ROOT="$repo" in_deploy "image_tag"
  [ "$status" -eq 1 ]
  [[ "$output" == *"commit or stash"* ]]
}

@test "deploy: a clean tree is tagged with the commit" {
  local repo="$BATS_TEST_TMPDIR/repo"
  git init -q "$repo"
  git -C "$repo" -c user.email=t@t -c user.name=t commit -q --allow-empty -m init
  REPO_ROOT="$repo" in_deploy "image_tag"
  [ "$status" -eq 0 ]
  [ "$output" = "$(git -C "$repo" rev-parse --short=12 HEAD)" ]
}

# --- release only (GitHub Deploy button) ---

# release_repo: a committed repo with a Dockerfile, for end-to-end deploy runs.
release_repo() {
  local repo="$BATS_TEST_TMPDIR/repo"
  git init -q "$repo"
  touch "$repo/Dockerfile"
  git -C "$repo" add Dockerfile
  git -C "$repo" -c user.email=t@t -c user.name=t commit -q -m init
  echo "$repo"
}

@test "release: changes no infrastructure or secrets and never needs the GoDaddy token" {
  rm "$SECRETS_ENV_FILE"
  REPO_ROOT=$(release_repo) run "$SKILL/scripts/deploy.sh" --release
  [ "$status" -eq 0 ]
  not_in "cloudformation deploy" "$STUB_LOG"
  not_in "put-parameter" "$STUB_LOG"
  not_in "api.godaddy.com" "$STUB_LOG"
  grep -q "remote-update.sh" "$STUB_LOG"
  grep -q "auto-stop.sh 4" "$STUB_LOG"
}

@test "release: a stopped server is started first" {
  STUB_STATE=stopped REPO_ROOT=$(release_repo) run "$SKILL/scripts/deploy.sh" --release
  [ "$status" -eq 0 ]
  local start update
  start=$(line_of "ec2 start-instances")
  update=$(line_of "remote-update.sh")
  [ -n "$start" ]
  [ "$start" -lt "$update" ]
}

@test "release: refuses when the domain does not point to the server" {
  STUB_DIG_IP=198.51.100.9 REPO_ROOT=$(release_repo) run "$SKILL/scripts/deploy.sh" --release
  [ "$status" -eq 1 ]
  [[ "$output" == *"does not point to"* ]]
  not_in "remote-update.sh" "$STUB_LOG"
}

@test "release: refuses before anything is deployed" {
  STUB_NO_STACK=1 REPO_ROOT=$(release_repo) run "$SKILL/scripts/deploy.sh" --release
  [ "$status" -eq 1 ]
  [[ "$output" == *"run deploy.sh from the author's laptop first"* ]]
}

# --- server on/off ---

@test "stop: backs up before stopping" {
  run "$SKILL/scripts/server.sh" stop
  [ "$status" -eq 0 ]
  local backup stop
  backup=$(line_of "backup.sh")
  stop=$(line_of "ec2 stop-instances")
  [ -n "$backup" ]
  [ -n "$stop" ]
  [ "$backup" -lt "$stop" ]
}

@test "stop: a failed backup leaves the server running" {
  STUB_REMOTE_STATUS=Failed run "$SKILL/scripts/server.sh" stop
  [ "$status" -eq 1 ]
  [[ "$output" == *"backup failed, server left running"* ]]
  not_in "ec2 stop-instances" "$STUB_LOG"
}

@test "stop: --skip-backup stops without a backup" {
  run "$SKILL/scripts/server.sh" stop --skip-backup
  [ "$status" -eq 0 ]
  not_in "ssm send-command" "$STUB_LOG"
  grep -q "ec2 stop-instances" "$STUB_LOG"
}

@test "stop: an already stopped server is left alone" {
  STUB_STATE=stopped run "$SKILL/scripts/server.sh" stop
  [ "$status" -eq 0 ]
  [[ "$output" == *"already stopped"* ]]
  not_in "ec2 stop-instances" "$STUB_LOG"
}

@test "start: starts a stopped server and schedules the auto-stop" {
  STUB_STATE=stopped run "$SKILL/scripts/server.sh" start 2
  [ "$status" -eq 0 ]
  grep -q "ec2 start-instances" "$STUB_LOG"
  grep -q "auto-stop.sh 2" "$STUB_LOG"
}

@test "start: on a running server it only resets the auto-stop (default hours)" {
  run "$SKILL/scripts/server.sh" start
  [ "$status" -eq 0 ]
  not_in "ec2 start-instances" "$STUB_LOG"
  grep -q "auto-stop.sh 4" "$STUB_LOG"
}

@test "start: hours must be a whole number" {
  run "$SKILL/scripts/server.sh" start -1
  [ "$status" -eq 1 ]
  [[ "$output" == *"hours must be a whole number"* ]]
}

@test "server: nothing deployed yet is reported" {
  STUB_NO_STACK=1 run "$SKILL/scripts/server.sh" status
  [ "$status" -eq 1 ]
  [[ "$output" == *"run deploy.sh first"* ]]
}

@test "server: an unknown action shows usage" {
  run "$SKILL/scripts/server.sh" reboot
  [ "$status" -eq 1 ]
  [[ "$output" == *"usage: server.sh"* ]]
}

@test "auto-stop: hours must be a whole number" {
  run "$SKILL/server/auto-stop.sh" soon
  [ "$status" -eq 1 ]
  [[ "$output" == *"whole number"* ]]
}

# --- author-only scripts ---

@test "logins: refuses when output is captured" {
  run "$SKILL/scripts/logins.sh"
  [ "$status" -eq 1 ]
  [[ "$output" == *"run this yourself"* ]]
  [ ! -s "$STUB_LOG" ]
}

@test "destroy: refuses when not in a terminal" {
  run "$SKILL/scripts/destroy.sh"
  [ "$status" -eq 1 ]
  [[ "$output" == *"run this yourself"* ]]
  [ ! -s "$STUB_LOG" ]
}
