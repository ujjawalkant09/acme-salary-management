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
  local params=("AlertEmail=$ALERT_EMAIL" "BudgetUsd=$BUDGET_USD" "GitHubSubjectPrefix=${GITHUB_OIDC_SUBJECT_PREFIX:-}")
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

# Uses the GoDaddy API only when the record is wrong, so a release needs no GoDaddy token.
ensure_dns() {
  local ip=$1 current
  if dns_points_to "$ip"; then
    log "DNS: $DOMAIN already points to $ip"
    return
  fi
  split_domain
  current=$(godaddy GET "/records/A/$DNS_RECORD" | jq -r '.[0].data // empty') ||
    die "GoDaddy API call failed: check GODADDY_API and that your account has API access"
  if [[ "$current" == "$ip" ]]; then
    log "DNS: $DOMAIN already points to $ip"
  else
    log "DNS: pointing $DOMAIN to $ip"
    godaddy PUT "/records/A/$DNS_RECORD" "[{\"data\":\"$ip\",\"ttl\":600}]" >/dev/null
  fi
  log "Waiting for $DOMAIN to resolve to $ip"
  retry 60 10 dns_points_to "$ip" || die "$DOMAIN does not resolve to $ip after 10 minutes"
}

dns_points_to() {
  [[ "$(dig +short A "$DOMAIN" @1.1.1.1 | tail -n 1)" == "$1" ]]
}

release() {
  local instance=$1 bucket=$2 image=$3 log_group=$4
  log "Releasing $image"
  aws s3 sync --delete "$SKILL_DIR/server" "s3://$bucket/deploy/" >/dev/null
  run_remote "$instance" \
    "aws s3 sync --delete s3://$bucket/deploy/ /opt/acme/release/" \
    "IMAGE=$image DOMAIN=$DOMAIN ACME_EMAIL=$ALERT_EMAIL PARAM_PATH=$PARAM_PATH AWS_REGION=$AWS_REGION LOG_GROUP=$log_group BUCKET=$bucket bash /opt/acme/release/remote-update.sh"
}

main() {
  local mode=${1:-}
  [[ -z "$mode" || "$mode" == "--plan" || "$mode" == "--release" ]] ||
    die "usage: deploy.sh [--plan | --release]"
  load_config
  require_tools aws docker jq dig curl openssl git
  check_identity
  if [[ "$mode" == "--plan" ]]; then
    apply_stack plan
    return
  fi
  [[ -f "$REPO_ROOT/Dockerfile" ]] || die "no Dockerfile at $REPO_ROOT (the app image is built from it)"
  local tag
  tag=$(image_tag)

  if [[ "$mode" == "--release" ]]; then
    stack_exists || die "nothing deployed yet; run deploy.sh from the author's laptop first"
  else
    apply_stack apply
    ensure_secrets
  fi
  local instance ip bucket repo_uri log_group
  instance=$(stack_output InstanceId)
  ip=$(stack_output PublicIp)
  bucket=$(stack_output BucketName)
  repo_uri=$(stack_output RepositoryUri)
  log_group=$(stack_output LogGroup)

  push_image "$repo_uri" "$tag"
  if [[ "$mode" == "--release" ]]; then
    dns_points_to "$ip" || die "$DOMAIN does not point to $ip; run deploy.sh from the author's laptop"
  else
    ensure_dns "$ip"
  fi
  ensure_running "$instance"
  release "$instance" "$bucket" "$repo_uri:$tag" "$log_group"
  wait_for_site
  schedule_auto_stop "$instance" "$AUTO_STOP_HOURS"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
