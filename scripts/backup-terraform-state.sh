#!/usr/bin/env bash
# Run on Houston with Garage AWS_* credentials and separate R2_* credentials.
set +x
set -euo pipefail
umask 077

fail() {
  printf '%s\n' "$*" >&2
  exit 1
}

[[ $# == 2 ]] || fail "Usage: $0 TERRAFORM_DIRECTORY STATE_NAME (for example checks/garage-backend)"
terraform_directory=$1
state_name=$2
[[ $state_name =~ ^[a-z0-9][a-z0-9_-]*(/[a-z0-9][a-z0-9_-]*)*$ ]] || fail 'Invalid state name.'
[[ -d $terraform_directory ]] || fail 'Terraform directory does not exist.'
[[ ${R2_ACCOUNT_ID:-} =~ ^[a-f0-9]{32}$ ]] || fail 'Set R2_ACCOUNT_ID to the Cloudflare account ID.'
[[ ${R2_ACCESS_KEY_ID:-} =~ ^[a-f0-9]{32}$ ]] || fail 'Set R2_ACCESS_KEY_ID to the bucket-scoped R2 access key.'
[[ ${R2_SECRET_ACCESS_KEY:-} =~ ^[a-f0-9]{64}$ ]] || fail 'Set R2_SECRET_ACCESS_KEY to the R2 secret access key.'
[[ -n ${AWS_ACCESS_KEY_ID:-} && -n ${AWS_SECRET_ACCESS_KEY:-} ]] || fail 'Load the Garage AWS_* credentials first.'
mountpoint --quiet /srv/terraform || fail 'The workload SSD must be mounted at /srv/terraform.'

staging_directory=$(mktemp -d /srv/terraform/backup-staging/state.XXXXXXXXXX)
snapshot="$staging_directory/snapshot.tfstate"
verified=false
cleanup() {
  result=$?
  if [[ $verified == true ]]; then
    rm -rf -- "$staging_directory"
  else
    printf 'Backup was not verified; private staging retained at %s\n' "$staging_directory" >&2
  fi
  exit "$result"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# The stable wrapper holds the shared Houston lock while reading state.
/usr/local/bin/terraform -chdir="$terraform_directory" state pull > "$snapshot"

# Validate without printing state, which can contain secrets.
python3 - "$snapshot" <<'PYTHON'
import json
import sys
with open(sys.argv[1], encoding="utf-8") as source:
    state = json.load(source)
if not (isinstance(state, dict) and state.get("version") == 4
        and isinstance(state.get("serial"), int) and state["serial"] >= 0
        and isinstance(state.get("lineage"), str) and state["lineage"]
        and isinstance(state.get("resources"), list)):
    raise SystemExit("Not a supported Terraform state snapshot.")
PYTHON

bucket=houston-terraform-state-backups
stamp=$(date -u +%Y-%m-%dT%H-%M-%SZ)
unique_id=$(python3 -c 'import uuid; print(uuid.uuid4())')
key="backups/$state_name/$stamp-$unique_id.tfstate"
url="https://$R2_ACCOUNT_ID.r2.cloudflarestorage.com/$bucket/$key"
snapshot_sha256=$(sha256sum "$snapshot" | cut -d ' ' -f 1)

r2_request() {
  # Validated hex credentials reach curl through stdin, outside process arguments.
  printf 'user = "%s:%s"\n' "$R2_ACCESS_KEY_ID" "$R2_SECRET_ACCESS_KEY" |
    curl --disable --config - --aws-sigv4 aws:amz:auto:s3 \
      --proto '=https' --silent --show-error --fail \
      --connect-timeout 10 --max-time 120 "$@" "$url"
}

# Conditional PUT rejects an existing key, even outside its retention period.
# No automatic PUT retry: an ambiguous failure may already have stored the object.
r2_request --upload-file "$snapshot" \
  --header 'Content-Type: application/json' \
  --header 'If-None-Match: *' \
  --header "x-amz-content-sha256: $snapshot_sha256" \
  --output /dev/null

r2_request --output "$staging_directory/readback.tfstate"
cmp --silent "$snapshot" "$staging_directory/readback.tfstate" || fail 'R2 readback differs from the snapshot.'
verified=true
printf 'Verified R2 backup: s3://%s/%s\nSHA256: %s\n' "$bucket" "$key" "$snapshot_sha256"
