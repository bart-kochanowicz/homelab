#!/usr/bin/env bash
# Run on Houston with the bucket-scoped R2 object credential.
set +x
set -euo pipefail
umask 077

fail() {
  printf '%s\n' "$*" >&2
  exit 1
}

[[ $# == 0 ]] || fail "Usage: $0 (generates its own disposable object keys)"
[[ ${R2_ACCOUNT_ID:-} =~ ^[a-f0-9]{32}$ ]] || fail 'Set R2_ACCOUNT_ID to the Cloudflare account ID.'
[[ ${R2_ACCESS_KEY_ID:-} =~ ^[a-f0-9]{32}$ ]] || fail 'Set R2_ACCESS_KEY_ID to the bucket-scoped R2 access key.'
[[ ${R2_SECRET_ACCESS_KEY:-} =~ ^[a-f0-9]{64}$ ]] || fail 'Set R2_SECRET_ACCESS_KEY to the R2 secret access key.'
mountpoint --quiet /srv/terraform || fail 'The workload SSD must be mounted at /srv/terraform.'
command -v aws > /dev/null || fail 'Install AWS CLI v2 with the terraform_cli Ansible role.'

staging_directory=$(mktemp -d /srv/terraform/backup-staging/retention.XXXXXXXXXX)
bucket=houston-terraform-state-backups
unique_id=$(python3 -I -c 'import uuid; print(uuid.uuid4())')
control_key="checks/retention/$unique_id.txt"
protected_key="backups/checks/retention/$unique_id.txt"
verified=false
cleanup() {
  result=$?
  if [[ $verified == true ]]; then
    rm -rf -- "$staging_directory"
  else
    printf 'Retention was not verified; private staging retained at %s\n' "$staging_directory" >&2
    printf 'Inspect only these disposable keys: %s and %s\n' "$control_key" "$protected_key" >&2
  fi
  exit "$result"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

printf 'Houston R2 retention probe: original\n' > "$staging_directory/original.txt"
printf 'Houston R2 retention probe: replacement\n' > "$staging_directory/replacement.txt"
r2_request() (
  # Scope R2 credentials/configuration to AWS CLI; Terraform keeps Garage access.
  unset AWS_SESSION_TOKEN AWS_SECURITY_TOKEN AWS_PROFILE AWS_DEFAULT_PROFILE
  export AWS_ACCESS_KEY_ID="$R2_ACCESS_KEY_ID" AWS_SECRET_ACCESS_KEY="$R2_SECRET_ACCESS_KEY"
  export AWS_CONFIG_FILE=/dev/null AWS_SHARED_CREDENTIALS_FILE=/dev/null
  export AWS_MAX_ATTEMPTS=1 AWS_RETRY_MODE=standard AWS_PAGER='' AWS_CLI_AUTO_PROMPT=off
  export AWS_REQUEST_CHECKSUM_CALCULATION=when_required AWS_RESPONSE_CHECKSUM_VALIDATION=when_required
  timeout 120 aws --endpoint-url "https://$R2_ACCOUNT_ID.r2.cloudflarestorage.com" --region auto \
    --cli-connect-timeout 10 --cli-read-timeout 120 s3api "$@" --bucket "$bucket"
)

expect_error() {
  local code=$1
  shift
  if r2_request "$@" > /dev/null 2> "$staging_directory/error"; then
    fail "R2 accepted an operation that must fail with $code."
  fi
  # Match the S3 code, not a generic permission, transport or CLI failure.
  grep --fixed-strings --quiet "An error occurred ($code) when calling the " "$staging_directory/error" || {
    cat "$staging_directory/error" >&2
    fail "R2 did not return the required S3 error: $code."
  }
}

read_original() {
  r2_request get-object --key "$1" "$staging_directory/response" > /dev/null
  cmp --silent "$staging_directory/original.txt" "$staging_directory/response" || fail 'Original probe bytes changed.'
}

# First prove the credential can overwrite and delete an unprotected object.
# Conditional creation and UUID keys prevent touching any existing object.
r2_request put-object --key "$control_key" --body "$staging_directory/original.txt" \
  --if-none-match '*' > /dev/null
read_original "$control_key"
# R2 limits writes to one per second for a given key; do not retry mutations.
sleep 2
r2_request put-object --key "$control_key" --body "$staging_directory/replacement.txt" > /dev/null
r2_request get-object --key "$control_key" "$staging_directory/response" > /dev/null
cmp --silent "$staging_directory/replacement.txt" "$staging_directory/response" || fail 'Control overwrite was not stored.'
sleep 2
r2_request delete-object --key "$control_key" > /dev/null
expect_error NoSuchKey get-object --key "$control_key" "$staging_directory/response"

r2_request put-object --key "$protected_key" --body "$staging_directory/original.txt" \
  --if-none-match '*' > /dev/null
read_original "$protected_key"
sleep 2
# No conditional header here: the rejection must come from Bucket Lock.
expect_error ObjectLockedByBucketPolicy put-object --key "$protected_key" --body "$staging_directory/replacement.txt"
read_original "$protected_key"
sleep 2
expect_error ObjectLockedByBucketPolicy delete-object --key "$protected_key"
read_original "$protected_key"

verified=true
printf 'Retention verified: overwrite and deletion rejected by Bucket Lock.\n'
printf 'Protected probe retained: s3://%s/%s\n' "$bucket" "$protected_key"
