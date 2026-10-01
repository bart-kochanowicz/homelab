#!/usr/bin/env bash
# Probe a prerequisite for Terraform S3 locking using a disposable object.
set -euo pipefail
umask 077

access_key=${AWS_ACCESS_KEY_ID:-${GARAGE_DEFAULT_ACCESS_KEY:-}}
secret_key=${AWS_SECRET_ACCESS_KEY:-${GARAGE_DEFAULT_SECRET_KEY:-}}
endpoint=${GARAGE_S3_ENDPOINT:-http://127.0.0.1:3900}
bucket=terraform-state
region=garage

if [[ -z "$access_key" || -z "$secret_key" ]]; then
  echo 'Supply Garage credentials through the environment; never put them in arguments.' >&2
  exit 1
fi
# Restrict curl config values to the characters used by Garage access keys.
if [[ ! "$access_key" =~ ^[[:alnum:]]+$ || ! "$secret_key" =~ ^[[:alnum:]/+=]+$ ]]; then
  echo 'Credentials contain unsupported characters.' >&2
  exit 1
fi
if [[ ! "$endpoint" =~ ^http://127\.0\.0\.1:[0-9]+$ ]]; then
  echo 'This probe requires a loopback Garage endpoint.' >&2
  exit 1
fi

command -v curl >/dev/null
probe_dir=$(mktemp -d "${TMPDIR:-/tmp}/garage-lock-check.XXXXXXXX")
key="compatibility-checks/locking/$(basename "$probe_dir")"
object_url="$endpoint/$bucket/$key"
created=false

request() {
  # Pass credentials over stdin so they do not appear in curl's process arguments.
  printf 'user = "%s:%s"\n' "$access_key" "$secret_key" |
    curl --config - --aws-sigv4 "aws:amz:$region:s3" \
      --silent --show-error --connect-timeout 5 --max-time 15 \
      --output "$probe_dir/response" --write-out '%{http_code}' \
      "$@" "$object_url"
}

cleanup() {
  local result=$? delete_status
  trap - EXIT
  if [[ "$created" == true ]]; then
    delete_status=$(request --request DELETE) || delete_status=000
    if [[ "$delete_status" != 204 && "$delete_status" != 200 ]]; then
      echo "Cleanup failed (HTTP $delete_status): remove only $bucket/$key manually." >&2
      result=1
    fi
  fi
  rm -rf -- "$probe_dir"
  exit "$result"
}
trap cleanup EXIT

printf '%s\n' 'first-lock' > "$probe_dir/first"
printf '%s\n' 'second-lock' > "$probe_dir/second"
first_status=$(request --request PUT --header 'If-None-Match: *' \
  --data-binary "@$probe_dir/first")
if [[ "$first_status" != 200 ]]; then
  echo "Initial conditional PUT failed (HTTP $first_status); compatibility is unverified." >&2
  exit 1
fi
created=true

second_status=$(request --request PUT --header 'If-None-Match: *' \
  --data-binary "@$probe_dir/second")
if [[ "$second_status" != 412 ]]; then
  echo "FAIL: repeated conditional PUT returned HTTP $second_status; expected 412." >&2
  echo 'Do not rely on Terraform use_lockfile with this endpoint.' >&2
  exit 1
fi

echo 'Sequential conditional-write check passed; this does not prove concurrent locking safety.'
