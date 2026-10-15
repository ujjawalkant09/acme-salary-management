#!/usr/bin/env bats
# Tests for the aws-deploy scripts. AWS, curl and dig are stubs (tests/stubs): no network, no account.

SKILL=$(cd "$BATS_TEST_DIRNAME/.." && pwd)
GODADDY_SECRET_PART=s3cr3tPart

setup() {
  # Tests run on GitHub too; each test opts in to GitHub Actions behaviour itself.
  unset GITHUB_ACTIONS
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
  STUB_DIG_IP_BEFORE=198.51.100.1 STUB_CURL_OUT='[{"data":"198.51.100.1"}]' in_deploy "split_domain && ensure_record A acme 203.0.113.10"
  [ "$status" -eq 0 ]
  grep -q -- "-X PUT .*records/A/acme" "$STUB_LOG"
  grep -q '"data":"203.0.113.10"' "$STUB_LOG"
  not_in "$GODADDY_SECRET_PART" "$STUB_LOG"
  grep -q "sso-key keyPart:$GODADDY_SECRET_PART" "$STUB_STDIN_LOG"
}

@test "dns: a record that already resolves is left alone without calling GoDaddy" {
  rm "$SECRETS_ENV_FILE"
  in_deploy "split_domain && ensure_record A acme 203.0.113.10"
  [ "$status" -eq 0 ]
  not_in "curl" "$STUB_LOG"
  [[ "$output" == *"already points to"* ]]
}

@test "dns: a missing CNAME is created with the value and no trailing dot" {
  STUB_DIG_CNAME= in_deploy "split_domain && ensure_record CNAME wake.acme d-abc.execute-api.ap-south-1.amazonaws.com"
  [ "$status" -eq 0 ]
  grep -q -- "-X PUT .*records/CNAME/wake.acme" "$STUB_LOG"
  grep -q '"data":"d-abc.execute-api.ap-south-1.amazonaws.com"' "$STUB_LOG"
}

@test "dns: a CNAME that already resolves (answer ends with a dot) is left alone" {
  rm "$SECRETS_ENV_FILE"
  in_deploy "split_domain && ensure_record CNAME wake.acme d-abc.execute-api.ap-south-1.amazonaws.com"
  [ "$status" -eq 0 ]
  not_in "curl" "$STUB_LOG"
  [[ "$output" == *"wake.acme.docrelay.in already points to"* ]]
}

@test "dns: a GoDaddy record that is right but not yet visible is not written again" {
  STUB_DIG_CNAME= STUB_CURL_OUT='[{"data":"d-abc.execute-api.ap-south-1.amazonaws.com."}]' \
    in_deploy "split_domain && retry() { return 0; } && ensure_record CNAME wake.acme d-abc.execute-api.ap-south-1.amazonaws.com"
  [ "$status" -eq 0 ]
  not_in "-X PUT" "$STUB_LOG"
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

@test "secrets: the wake code is a secret one level below the server's settings" {
  STUB_MISSING="/acme-salary/wake/WAKE_CODE" in_deploy "ensure_secrets"
  [ "$status" -eq 0 ]
  grep -q "/acme-salary/wake/WAKE_CODE" "$STUB_LOG"
  [ "$(jq -r .Name "$STUB_STDIN_LOG")" = "/acme-salary/wake/WAKE_CODE" ]
  [ "$(jq -r '.Value | length' "$STUB_STDIN_LOG")" -eq 64 ]
}

@test "secrets: re-running with every secret present changes nothing" {
  STUB_MISSING=None in_deploy "ensure_secrets"
  [ "$status" -eq 0 ]
  not_in "ssm put-parameter" "$STUB_LOG"
}

# --- deploy ---

@test "deploy: the GitHub OIDC subject from config.env goes to the stack (empty = no GitHub access)" {
  echo "GITHUB_OIDC_SUBJECT_PREFIX=repo:owner@1/repo@2" >>"$CONFIG_FILE"
  in_deploy "apply_stack apply"
  [ "$status" -eq 0 ]
  grep -q "GitHubSubjectPrefix=repo:owner@1/repo@2" "$STUB_LOG"
}

@test "deploy: without a GitHub subject the stack gets an empty one" {
  in_deploy "apply_stack apply"
  [ "$status" -eq 0 ]
  grep -qE "GitHubSubjectPrefix=( |$)" "$STUB_LOG"
}

@test "deploy: the stack gets the domain and the wake certificate" {
  in_deploy "WAKE_CERTIFICATE_ARN=arn:cert && apply_stack apply"
  [ "$status" -eq 0 ]
  grep -q "Domain=acme.docrelay.in" "$STUB_LOG"
  grep -q "WakeCertificateArn=arn:cert" "$STUB_LOG"
}

@test "deploy: requests the certificate before the stack, uploads the wake page and points wake.<domain> at it" {
  STUB_CERT=None STUB_DIG_CNAME= REPO_ROOT=$(release_repo) run "$SKILL/scripts/deploy.sh"
  [ "$status" -eq 0 ]
  local cert stack upload wake_dns
  cert=$(line_of "acm wait certificate-validated")
  stack=$(line_of "cloudformation deploy")
  upload=$(line_of "lambda update-function-code")
  wake_dns=$(line_of "records/CNAME/wake.acme")
  [ "$cert" -lt "$stack" ]
  [ "$stack" -lt "$upload" ]
  [ -n "$wake_dns" ]
  grep -q "WakeCertificateArn=arn:aws:acm:ap-south-1:123456789012:certificate/new" "$STUB_LOG"
  [ "$(jq -r '.[0].data' "$STUB_LOG.cname_put")" = "d-abc.execute-api.ap-south-1.amazonaws.com" ]
}

@test "plan: an issued wake certificate goes to the plan and nothing is requested or changed" {
  run "$SKILL/scripts/deploy.sh" --plan
  [ "$status" -eq 0 ]
  grep -q -- "--no-execute-changeset" "$STUB_LOG"
  grep -q "WakeCertificateArn=arn:aws:acm:ap-south-1:123456789012:certificate/old" "$STUB_LOG"
  not_in "request-certificate" "$STUB_LOG"
  not_in "curl" "$STUB_LOG"
}

@test "plan: a certificate that is not issued yet is left out" {
  STUB_CERT="arn:aws:acm:ap-south-1:123456789012:certificate/new	PENDING_VALIDATION" run "$SKILL/scripts/deploy.sh" --plan
  [ "$status" -eq 0 ]
  grep -qE "WakeCertificateArn=( |$)" "$STUB_LOG"
  not_in "acm wait" "$STUB_LOG"
}

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
  grep -q "AUTO_STOP_HOURS=4 bash /opt/acme/release/remote-update.sh" "$STUB_LOG"
  grep -q "auto-stop.sh 4" "$STUB_LOG"
  not_in "acm " "$STUB_LOG"
  not_in "lambda " "$STUB_LOG"
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

# --- wake page ---

@test "certificate: an issued one is reused without a new request or DNS change" {
  rm "$SECRETS_ENV_FILE"
  in_deploy 'split_domain && ensure_wake_certificate && echo "arn=$WAKE_CERTIFICATE_ARN"'
  [ "$status" -eq 0 ]
  [[ "$output" == *"arn=arn:aws:acm:ap-south-1:123456789012:certificate/old"* ]]
  not_in "request-certificate" "$STUB_LOG"
  not_in "acm wait" "$STUB_LOG"
  not_in "curl" "$STUB_LOG"
}

@test "certificate: a missing one is requested for wake.<domain>, proved in GoDaddy, then waited for" {
  STUB_CERT=None in_deploy 'split_domain && ensure_wake_certificate && echo "arn=$WAKE_CERTIFICATE_ARN"'
  [ "$status" -eq 0 ]
  [[ "$output" == *"arn=arn:aws:acm:ap-south-1:123456789012:certificate/new"* ]]
  grep -q "acm request-certificate --domain-name wake.acme.docrelay.in --validation-method DNS" "$STUB_LOG"
  grep -q -- "-X PUT .*records/CNAME/_v1.wake.acme$" "$STUB_LOG"
  [ "$(jq -r '.[0].data' "$STUB_LOG.cname_put")" = "_t1.acm-validations.aws" ]
  [ "$(line_of "records/CNAME/_v1")" -lt "$(line_of "acm wait certificate-validated")" ]
}

@test "certificate: a pending one is not requested again" {
  STUB_CERT="arn:aws:acm:ap-south-1:123456789012:certificate/pending	PENDING_VALIDATION" \
    in_deploy 'split_domain && ensure_wake_certificate && echo "arn=$WAKE_CERTIFICATE_ARN"'
  [ "$status" -eq 0 ]
  [[ "$output" == *"arn=arn:aws:acm:ap-south-1:123456789012:certificate/pending"* ]]
  not_in "request-certificate" "$STUB_LOG"
  grep -q "acm wait certificate-validated --certificate-arn arn:aws:acm:ap-south-1:123456789012:certificate/pending" "$STUB_LOG"
}

@test "certificate: no validation record from ACM stops the deploy" {
  STUB_CERT=None STUB_VALIDATION="None	None" in_deploy "split_domain && ensure_wake_certificate"
  [ "$status" -eq 1 ]
  [[ "$output" == *"ACM gave no validation record"* ]]
  not_in "acm wait" "$STUB_LOG"
}

@test "wake: the page code is zipped and uploaded to the function, and the zip is deleted" {
  in_deploy "upload_wake_code acme-salary-WakeFunction"
  [ "$status" -eq 0 ]
  grep -q "lambda update-function-code --function-name acme-salary-WakeFunction --zip-file fileb://" "$STUB_LOG"
  grep -q "lambda wait function-updated --function-name acme-salary-WakeFunction" "$STUB_LOG"
  [ "$(sort "$STUB_LOG.zip" | tr '\n' ' ')" = "index.py page.html " ]
  [ ! -e "$(dirname "$(cat "$STUB_LOG.zip.path")")" ]
}

@test "wake: a failed upload still deletes the zip" {
  STUB_FAIL="lambda update-function-code" in_deploy "upload_wake_code acme-salary-WakeFunction"
  [ "$status" -ne 0 ]
  [ ! -e "$(dirname "$(cat "$STUB_LOG.zip.path")")" ]
  not_in "lambda wait" "$STUB_LOG"
}

@test "boot auto-stop: every boot runs auto-stop.sh with the hours, before the SSM agent" {
  UNIT_DIR="$BATS_TEST_TMPDIR" run "$SKILL/server/boot-auto-stop.sh" 3
  [ "$status" -eq 0 ]
  local unit="$BATS_TEST_TMPDIR/acme-autostop-on-boot.service"
  grep -qx "ExecStart=/bin/bash /opt/acme/release/auto-stop.sh 3" "$unit"
  grep -qx "Before=snap.amazon-ssm-agent.amazon-ssm-agent.service" "$unit"
  grep -qx "WantedBy=multi-user.target" "$unit"
  [ "$(line_of "systemctl daemon-reload")" -lt "$(line_of "systemctl enable --quiet acme-autostop-on-boot.service")" ]
}

@test "boot auto-stop: running it again replaces the hours" {
  UNIT_DIR="$BATS_TEST_TMPDIR" run "$SKILL/server/boot-auto-stop.sh" 3
  UNIT_DIR="$BATS_TEST_TMPDIR" run "$SKILL/server/boot-auto-stop.sh" 0
  [ "$status" -eq 0 ]
  [ "$(grep -c ExecStart "$BATS_TEST_TMPDIR/acme-autostop-on-boot.service")" -eq 1 ]
  grep -qx "ExecStart=/bin/bash /opt/acme/release/auto-stop.sh 0" "$BATS_TEST_TMPDIR/acme-autostop-on-boot.service"
}

@test "boot auto-stop: hours must be a whole number and nothing is installed" {
  UNIT_DIR="$BATS_TEST_TMPDIR" run "$SKILL/server/boot-auto-stop.sh" 2h
  [ "$status" -eq 1 ]
  [[ "$output" == *"whole number"* ]]
  [ ! -e "$BATS_TEST_TMPDIR/acme-autostop-on-boot.service" ]
  not_in "systemctl" "$STUB_LOG"
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
