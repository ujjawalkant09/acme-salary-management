#!/usr/bin/env bash
# Creates or updates everything on AWS and releases the current commit to https://$DOMAIN.
# Safe to run again: unchanged parts are left alone.
#
#   deploy.sh            create or update everything, then release (from the author's laptop)
#   deploy.sh --plan     show what CloudFormation would change, change nothing
#   deploy.sh --release  only build and release the current commit to the existing stack
#                        (used by the GitHub Deploy button; no infrastructure, secret or DNS changes)

# shellcheck source=lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

UBUNTU_AMI_PARAM=/aws/service/canonical/ubuntu/server/24.04/stable/current/arm64/hvm/ebs-gp3/ami-id

apply_stack() {
  local plan=$1
  local params=("Domain=$DOMAIN" "WakeCertificateArn=${WAKE_CERTIFICATE_ARN:-}" "AlertEmail=$ALERT_EMAIL"
    "BudgetUsd=$BUDGET_USD" "GitHubSubjectPrefix=${GITHUB_OIDC_SUBJECT_PREFIX:-}")
  # The server image is looked up once, when the stack is first created. Later runs keep it:
  # a new image id would make CloudFormation replace the server and lose its disk.
  if ! stack_exists; then
    params+=("ImageId=$(aws ssm get-parameter --name "$UBUNTU_AMI_PARAM" --query Parameter.Value --output text)")
  fi
  local args=(--template-file "$SKILL_DIR/infra/stack.yml" --stack-name "$STACK_NAME"
    --capabilities CAPABILITY_IAM --no-fail-on-empty-changeset --parameter-overrides "${params[@]}")
  if [[ "$plan" == "plan" ]]; then
    aws cloudformation deploy "${args[@]}" --no-execute-changeset
    return
  fi
  log "Applying CloudFormation stack $STACK_NAME (first run takes about 5 minutes)"
  aws cloudformation deploy "${args[@]}"
}

# Creates any missing secret with a random value. Existing secrets are never changed,
# so a re-run can't lock the app out of its own database.
# The AWS CLI can't read --cli-input-json from a pipe, so each value goes through a
# private temp file (owner-only, deleted right after the call, also on failure).
ensure_secrets() {
  local names=() missing name
  for name in "${SECRET_NAMES[@]}"; do names+=("$PARAM_PATH/$name"); done
  missing=$(aws ssm get-parameters --names "${names[@]}" --query 'InvalidParameters' --output text)
  for name in $missing; do
    [[ "$name" == "None" ]] && continue
    log "Creating secret $name"
    put_secret "$name"
  done
}

put_secret() {
  local dir status=0
  dir=$(umask 077 && mktemp -d)
  openssl rand -hex 32 | tr -d '\n' |
    jq -Rs --arg name "$1" '{Name: $name, Value: ., Type: "SecureString"}' >"$dir/input.json" ||
    status=$?
  if ((status == 0)); then
    aws ssm put-parameter --cli-input-json "file://$dir/input.json" >/dev/null || status=$?
  fi
  rm -rf "$dir"
  return "$status"
}

image_tag() {
  [[ -z "$(git -C "$REPO_ROOT" status --porcelain)" ]] ||
    die "commit or stash your changes first: the deployed image is tagged with the commit"
  git -C "$REPO_ROOT" rev-parse --short=12 HEAD
}

push_image() {
  local repo_uri=$1 tag=$2
  if aws ecr describe-images --repository-name "${repo_uri#*/}" --image-ids "imageTag=$tag" >/dev/null 2>&1; then
    log "Image $tag is already in ECR"
    return
  fi
  log "Building and pushing image $tag (linux/arm64)"
  aws ecr get-login-password | docker login --username AWS --password-stdin "${repo_uri%%/*}" >/dev/null
  # Layers are cached in ECR under one tag, so a release only rebuilds what changed. It is
  # pushed on every build, so it stays the newest image and the lifecycle rule keeps it.
  # Docker's default builder cannot export a cache, so builds use their own BuildKit container.
  docker buildx inspect acme-builder >/dev/null 2>&1 ||
    docker buildx create --name acme-builder --driver docker-container >/dev/null
  docker buildx build --builder acme-builder --platform linux/arm64 --build-arg GIT_COMMIT="$tag" \
    --cache-from "type=registry,ref=$repo_uri:buildcache" \
    --cache-to "type=registry,ref=$repo_uri:buildcache,mode=max,image-manifest=true,oci-mediatypes=true" \
    --tag "$repo_uri:$tag" --push "$REPO_ROOT"
}

# ensure_record <type> <name in the zone> <value>: makes <name>.<zone> answer <value>.
# Uses the GoDaddy API only when the record is wrong, so a re-run needs no GoDaddy token.
ensure_record() {
  local type=$1 name=$2 value=$3 fqdn="$2.$DNS_ZONE" current
  if record_points_to "$type" "$fqdn" "$value"; then
    log "DNS: $fqdn already points to $value"
    return
  fi
  current=$(godaddy GET "/records/$type/$name" | jq -r '.[0].data // empty') ||
    die "GoDaddy API call failed: check GODADDY_API and that your account has API access"
  if [[ "${current%.}" != "$value" ]]; then
    log "DNS: pointing $fqdn to $value"
    godaddy PUT "/records/$type/$name" "[{\"data\":\"$value\",\"ttl\":600}]" >/dev/null
  fi
  log "Waiting for $fqdn to resolve to $value"
  retry 60 10 record_points_to "$type" "$fqdn" "$value" || die "$fqdn does not resolve to $value after 10 minutes"
}

# record_points_to <type> <full name> <value>, asked of a public resolver. CNAME answers end with a dot.
record_points_to() {
  local answer
  answer=$(dig +short "$1" "$2" @1.1.1.1 | tail -n 1)
  [[ "${answer%.}" == "$3" ]]
}

# A free ACM certificate for the wake page, proved by a DNS record in GoDaddy. ACM renews it
# by itself while that record stays. Sets WAKE_CERTIFICATE_ARN.
ensure_wake_certificate() {
  local arn status
  read -r arn status < <(wake_certificate) || true
  if [[ -z "$arn" || "$arn" == "None" ]]; then
    log "Requesting a certificate for $WAKE_DOMAIN"
    arn=$(aws acm request-certificate --domain-name "$WAKE_DOMAIN" --validation-method DNS \
      --idempotency-token acmewake --query CertificateArn --output text)
    status=PENDING_VALIDATION
  fi
  if [[ "$status" != "ISSUED" ]]; then
    # ACM takes a few seconds to say which record it wants.
    retry 12 5 validation_record "$arn" || die "ACM gave no validation record for $WAKE_DOMAIN"
    ensure_record CNAME "${VALIDATION_NAME%".$DNS_ZONE."}" "${VALIDATION_VALUE%.}"
    log "Waiting for ACM to issue the certificate for $WAKE_DOMAIN"
    aws acm wait certificate-validated --certificate-arn "$arn"
  fi
  WAKE_CERTIFICATE_ARN=$arn
}

# The stack only holds a placeholder; the wake page's code comes from wake/.
upload_wake_code() {
  local function_name=$1 dir status=0
  dir=$(mktemp -d)
  (cd "$SKILL_DIR/wake" && zip -q -X "$dir/wake.zip" index.py page.html) || status=$?
  if ((status == 0)); then
    log "Uploading the wake page"
    aws lambda update-function-code --function-name "$function_name" --zip-file "fileb://$dir/wake.zip" >/dev/null &&
      aws lambda wait function-updated --function-name "$function_name" || status=$?
  fi
  rm -rf "$dir"
  return "$status"
}

release() {
  local instance=$1 bucket=$2 image=$3 log_group=$4
  log "Releasing $image"
  aws s3 sync --delete "$SKILL_DIR/server" "s3://$bucket/deploy/" >/dev/null
  run_remote "$instance" \
    "aws s3 sync --delete s3://$bucket/deploy/ /opt/acme/release/" \
    "IMAGE=$image DOMAIN=$DOMAIN ACME_EMAIL=$ALERT_EMAIL PARAM_PATH=$PARAM_PATH AWS_REGION=$AWS_REGION LOG_GROUP=$log_group BUCKET=$bucket AUTO_STOP_HOURS=$AUTO_STOP_HOURS bash /opt/acme/release/remote-update.sh"
}

main() {
  local mode=${1:-}
  [[ -z "$mode" || "$mode" == "--plan" || "$mode" == "--release" ]] ||
    die "usage: deploy.sh [--plan | --release]"
  load_config
  require_tools aws docker jq dig curl openssl git
  check_identity
  split_domain
  if [[ "$mode" == "--plan" ]]; then
    # Read-only: shows the wake address only once its certificate has been issued.
    local status
    read -r WAKE_CERTIFICATE_ARN status < <(wake_certificate) || true
    [[ "$status" == "ISSUED" ]] || WAKE_CERTIFICATE_ARN=""
    apply_stack plan
    return
  fi
  [[ -f "$REPO_ROOT/Dockerfile" ]] || die "no Dockerfile at $REPO_ROOT (the app image is built from it)"
  local tag
  tag=$(image_tag)

  if [[ "$mode" == "--release" ]]; then
    stack_exists || die "nothing deployed yet; run deploy.sh from the author's laptop first"
  else
    require_tools zip
    ensure_wake_certificate
    apply_stack apply
    ensure_secrets
    upload_wake_code "$(stack_output WakeFunctionName)"
  fi
  local instance ip bucket repo_uri log_group
  instance=$(stack_output InstanceId)
  ip=$(stack_output PublicIp)
  bucket=$(stack_output BucketName)
  repo_uri=$(stack_output RepositoryUri)
  log_group=$(stack_output LogGroup)

  push_image "$repo_uri" "$tag"
  if [[ "$mode" == "--release" ]]; then
    record_points_to A "$DOMAIN" "$ip" || die "$DOMAIN does not point to $ip; run deploy.sh from the author's laptop"
  else
    ensure_record A "$DNS_RECORD" "$ip"
    ensure_record CNAME "wake.$DNS_RECORD" "$(stack_output WakeTarget)"
  fi
  ensure_running "$instance"
  release "$instance" "$bucket" "$repo_uri:$tag" "$log_group"
  wait_for_site
  schedule_auto_stop "$instance" "$AUTO_STOP_HOURS"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
