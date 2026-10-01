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
original_sha256=$(sha256sum "$staging_directory/original.txt" | cut -d ' ' -f 1)
replacement_sha256=$(sha256sum "$staging_directory/replacement.txt" | cut -d ' ' -f 1)

r2_request() {
  local key=$1
  shift
  # Credentials go through stdin, never curl arguments. HTTP errors are checked
  # below; TLS, connection and timeout failures still return nonzero here.
  response_status=$(
    printf 'user = "%s:%s"\n' "$R2_ACCESS_KEY_ID" "$R2_SECRET_ACCESS_KEY" |
      curl --disable --config - --aws-sigv4 aws:amz:auto:s3 \
        --proto '=https' --silent --show-error \
        --connect-timeout 10 --max-time 120 \
        --output "$staging_directory/response" --write-out '%{http_code}' \
        "$@" "https://$R2_ACCOUNT_ID.r2.cloudflarestorage.com/$bucket/$key"
  )
}

expect_status() {
  [[ $response_status == "$1" ]] || fail "$2: unexpected HTTP $response_status."
}

expect_error() {
  python3 -I - "$staging_directory/response" "$1" <<'PYTHON'
import sys
import xml.etree.ElementTree as ET
try:
    error = ET.parse(sys.argv[1]).getroot()
except ET.ParseError:
    raise SystemExit("R2 did not return a valid XML error.")
if error.tag != "Error" or error.findtext("Code") != sys.argv[2]:
    raise SystemExit("R2 did not return the required S3 error code.")
PYTHON
}

expect_locked() {
  # R2 documents 403, but its S3 endpoint also returns 409 for this error.
  # A generic conflict or permission denial is not evidence of Bucket Lock.
  [[ $response_status == 403 || $response_status == 409 ]] || fail "$1: unexpected HTTP $response_status."
  expect_error ObjectLockedByBucketPolicy
}

read_original() {
  r2_request "$1"
  expect_status 200 'Read original probe'
  cmp --silent "$staging_directory/original.txt" "$staging_directory/response" || fail 'Original probe bytes changed.'
}

# First prove the credential can overwrite and delete an unprotected object.
# Conditional creation and UUID keys prevent touching any existing object.
r2_request "$control_key" --upload-file "$staging_directory/original.txt" \
  --header 'If-None-Match: *' --header "x-amz-content-sha256: $original_sha256"
expect_status 200 'Create unprotected control'
read_original "$control_key"
# R2 limits writes to one per second for a given key; do not retry mutations.
sleep 2
r2_request "$control_key" --upload-file "$staging_directory/replacement.txt" \
  --header "x-amz-content-sha256: $replacement_sha256"
expect_status 200 'Overwrite unprotected control'
r2_request "$control_key"
expect_status 200 'Read overwritten control'
cmp --silent "$staging_directory/replacement.txt" "$staging_directory/response" || fail 'Control overwrite was not stored.'
sleep 2
r2_request "$control_key" --request DELETE
expect_status 204 'Delete unprotected control'
r2_request "$control_key"
expect_status 404 'Read deleted control'
expect_error NoSuchKey

r2_request "$protected_key" --upload-file "$staging_directory/original.txt" \
  --header 'If-None-Match: *' --header "x-amz-content-sha256: $original_sha256"
expect_status 200 'Create protected probe'
read_original "$protected_key"
sleep 2
# No conditional header here: the rejection must come from Bucket Lock.
r2_request "$protected_key" --upload-file "$staging_directory/replacement.txt" \
  --header "x-amz-content-sha256: $replacement_sha256"
expect_locked 'Overwrite protected probe'
read_original "$protected_key"
sleep 2
r2_request "$protected_key" --request DELETE
expect_locked 'Delete protected probe'
read_original "$protected_key"

verified=true
printf 'Retention verified: overwrite and deletion rejected by Bucket Lock.\n'
printf 'Protected probe retained: s3://%s/%s\n' "$bucket" "$protected_key"
