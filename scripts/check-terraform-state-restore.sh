#!/usr/bin/env bash
# Rehearse recovery of the built-in Garage marker into a fresh check-only key.
set +x
set -euo pipefail
umask 077

fail() {
  printf '%s\n' "$*" >&2
  exit 1
}

[[ $# == 2 ]] || fail "Usage: $0 R2_OBJECT_KEY EXPECTED_SHA256"
key=$1
expected_sha256=$2
[[ $key =~ ^backups/checks/garage-backend/[0-9TZ-]+-[a-f0-9-]+\.tfstate$ ]] || fail 'Use a snapshot under backups/checks/garage-backend/.'
[[ $expected_sha256 =~ ^[a-f0-9]{64}$ ]] || fail 'Supply the SHA256 printed by the backup script.'
[[ ${R2_ACCOUNT_ID:-} =~ ^[a-f0-9]{32}$ ]] || fail 'Set R2_ACCOUNT_ID.'
[[ ${R2_ACCESS_KEY_ID:-} =~ ^[a-f0-9]{32}$ ]] || fail 'Set R2_ACCESS_KEY_ID.'
[[ ${R2_SECRET_ACCESS_KEY:-} =~ ^[a-f0-9]{64}$ ]] || fail 'Set R2_SECRET_ACCESS_KEY.'
[[ -n ${AWS_ACCESS_KEY_ID:-} && -n ${AWS_SECRET_ACCESS_KEY:-} ]] || fail 'Load the Garage AWS_* credentials first.'
mountpoint --quiet /srv/terraform || fail 'The workload SSD must be mounted at /srv/terraform.'

# Keep inherited Terraform options from redirecting this private rehearsal.
unset TF_DATA_DIR TF_WORKSPACE TF_CLI_ARGS TF_CLI_ARGS_init TF_CLI_ARGS_state TF_CLI_ARGS_plan TF_CLI_ARGS_output
repo_directory=$(cd -- "$(dirname -- "$0")/.." && pwd)
staging_directory=$(mktemp -d /srv/terraform/backup-staging/restore.XXXXXXXXXX)
snapshot="$staging_directory/snapshot.tfstate"
verified=false
cleanup() {
  result=$?
  if [[ $verified == true ]]; then
    rm -f -- "$snapshot" "$staging_directory/restored.tfstate"
  else
    printf 'Restore was not verified; private staging retained at %s\n' "$staging_directory" >&2
  fi
  exit "$result"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

url="https://$R2_ACCOUNT_ID.r2.cloudflarestorage.com/houston-terraform-state-backups/$key"
printf 'user = "%s:%s"\n' "$R2_ACCESS_KEY_ID" "$R2_SECRET_ACCESS_KEY" |
  curl --disable --config - --aws-sigv4 aws:amz:auto:s3 \
    --proto '=https' --silent --show-error --fail \
    --connect-timeout 10 --max-time 120 --output "$snapshot" "$url"
[[ $(sha256sum "$snapshot" | cut -d ' ' -f 1) == "$expected_sha256" ]] || fail 'Snapshot SHA256 does not match the backup result.'

# Accept only the completed, harmless marker example, never infrastructure state.
python3 -I - "$snapshot" <<'PYTHON'
import json
import sys
import uuid
with open(sys.argv[1], encoding="utf-8") as source:
    state = json.load(source)
marker = "Garage backend read/write verified"
try:
    assert state["version"] == 4 and type(state["serial"]) is int and state["serial"] >= 0
    assert isinstance(state["lineage"], str) and state["lineage"]
    assert state["outputs"] == {"backend_check": {"value": marker, "type": "string"}}
    assert len(state["resources"]) == 1
    resource = state["resources"][0]
    assert not resource.get("module")
    assert (resource["mode"], resource["type"], resource["name"]) == ("managed", "terraform_data", "backend_check")
    assert resource["provider"] == 'provider["terraform.io/builtin/terraform"]'
    assert len(resource["instances"]) == 1
    instance = resource["instances"][0]
    assert "index_key" not in instance and "deposed" not in instance and not instance.get("status")
    attributes = instance["attributes"]
    uuid.UUID(attributes["id"])
    assert attributes["input"] == attributes["output"] == {"value": marker, "type": "string"}
    assert attributes.get("store") is None and attributes.get("triggers_replace") is None
except (AssertionError, KeyError, TypeError, ValueError):
    raise SystemExit("Snapshot must contain the completed terraform_data.backend_check marker. Apply the example and create a new backup.") from None
PYTHON

restore_directory="$staging_directory/module"
mkdir "$restore_directory"
cp "$repo_directory/terraform/examples/garage-restore/main.tf" "$restore_directory/main.tf"
restore_key="checks/garage-restore/$(python3 -c 'import uuid; print(uuid.uuid4())')/terraform.tfstate"
terraform_command() {
  /usr/local/bin/terraform -chdir="$restore_directory" "$@"
}
terraform_command init -input=false -no-color \
  -backend-config="$repo_directory/terraform/garage.s3.tfbackend" \
  -backend-config="key=$restore_key"

# Confirm the actual initialized destination before writing any state.
python3 - "$restore_directory/.terraform/terraform.tfstate" "$restore_key" <<'PYTHON'
import json
import sys
with open(sys.argv[1], encoding="utf-8") as source:
    backend = json.load(source)["backend"]
config = backend["config"]
if not (backend["type"] == "s3" and config["bucket"] == "terraform-state"
        and config["key"] == sys.argv[2] and config["region"] == "garage"
        and config["endpoints"]["s3"] == "http://127.0.0.1:3900"):
    raise SystemExit("Restore destination is not the expected isolated Garage key.")
PYTHON

terraform_command state push "$snapshot"
terraform_command state pull > "$staging_directory/restored.tfstate"
python3 - "$snapshot" "$staging_directory/restored.tfstate" <<'PYTHON'
import json
import sys
states = []
for name in sys.argv[1:]:
    with open(name, encoding="utf-8") as source:
        states.append(json.load(source))
# A fresh backend can assign new lineage/serial metadata during state push.
if any(states[0][field] != states[1][field] for field in ("resources", "outputs")):
    raise SystemExit("Restored resources or outputs differ from the snapshot.")
PYTHON
terraform_command state list
terraform_command plan -input=false -detailed-exitcode -no-color
verified=true
printf 'Restore verified: terraform_data.backend_check\nGarage state key: %s\nPrivate restore workspace: %s\n' "$restore_key" "$restore_directory"
