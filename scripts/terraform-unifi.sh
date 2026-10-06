#!/usr/bin/env bash
set +x
set -euo pipefail
umask 077

repo_directory=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)

# A separate code descriptor preserves stdin for Terraform's apply confirmation.
exec python3 /dev/fd/3 "$repo_directory" "$@" 3<<'PYTHON'
import json
import os
from pathlib import Path
import stat
import sys


def fail(message):
    raise SystemExit(message)


def private_file(path):
    try:
        info = path.lstat()
        parent = path.parent.stat()
    except OSError:
        fail("Required private input or certificate file is unavailable.")
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        fail("Private files must be regular, owned by the operator and mode 0600.")
    if parent.st_uid != os.getuid() or parent.st_mode & 0o077:
        fail("The private input directory must be operator-owned and mode 0700.")
    return path


root = Path(sys.argv[1])
arguments = sys.argv[2:]
allowed = {"init", "validate", "plan", "apply", "show", "output", "state", "import", "providers"}
if not arguments or arguments[0] not in allowed:
    fail("Usage: terraform-unifi.sh {init|validate|plan|apply|show|output|state|import|providers} [arguments]")

input_path = private_file(Path(os.environ.get("UNIFI_INPUT_FILE", root / ".secrets/unifi/variables.tfvars.json")).expanduser())
certificate_path = private_file(Path(os.environ.get("UNIFI_CA_CERT_FILE", input_path.parent / "controller-certificate.pem")).expanduser())
try:
    inputs = json.loads(input_path.read_text())
except (OSError, ValueError):
    fail("Private Terraform inputs must be valid JSON.")
if not isinstance(inputs, dict) or not isinstance(inputs.get("unifi_auth"), dict):
    fail("Private inputs must include the unifi_auth object.")

environment = dict(os.environ)
# The provider reads these environment overrides even with explicit false flags.
for key in list(environment):
    if key.startswith(("UNIFI_", "TF_VAR_", "TF_LOG", "TF_CLI_ARGS")) or key in {
        "AWS_SESSION_TOKEN", "AWS_SECURITY_TOKEN", "AWS_PROFILE", "AWS_DEFAULT_PROFILE"
    }:
        del environment[key]
for name, value in inputs.items():
    if name not in {"controller", "unifi_auth", "name_prefix", "networks"}:
        fail("Private inputs contain an unsupported Terraform variable.")
    environment["TF_VAR_" + name] = value if isinstance(value, str) else json.dumps(value)
environment["SSL_CERT_FILE"] = str(certificate_path.absolute())
environment["TF_WORKSPACE"] = "default"
environment["TF_IN_AUTOMATION"] = "true"

if not environment.get("AWS_ACCESS_KEY_ID") or not environment.get("AWS_SECRET_ACCESS_KEY"):
    fail("Load the Garage AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY before running Terraform.")
if not Path("/usr/local/bin/terraform").is_file():
    fail("Run on Houston through its locked /usr/local/bin/terraform wrapper.")

if arguments[0] == "init":
    if len(arguments) != 1:
        fail("The init command uses the fixed Garage backend configuration.")
    arguments += ["-input=false", "-lockfile=readonly", "-backend-config=../garage.s3.tfbackend"]

os.close(3)
os.execve("/usr/local/bin/terraform", ["terraform", "-chdir=" + str(root / "terraform/unifi"), *arguments], environment)
PYTHON
