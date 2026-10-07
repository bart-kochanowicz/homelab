# Local Terraform plans

Cloudflare and UniFi plans run natively on macOS against Houston's Garage state.
Use the Terraform version pinned in `aqua.yaml` and the committed provider locks.
Apply runs on Houston through the approved
[Actions workflow](https://github.com/bart-kochanowicz/homelab/actions/workflows/terraform-dispatch.yaml).
Run all commands below from the repository root, not `terraform/` or a root module.

## Prerequisites

Install aqua and Ansible; OpenSSH must be available. Run `aqua install` and add
its tool directory to `PATH` as described in the
[installation guide](https://aquaproj.github.io/docs/install).
UniFi certificate enrollment also uses GitHub CLI, OpenSSL and Python 3;
authenticate `gh auth login` with access to the private automation repository.

Houston needs its [host configuration](../infra/ansible/README.md).
For a rebuilt host, recover existing deployment state through
[state recovery](R2_BACKUP.md#recovery) before planning.
Restore or authorize the operator SSH key and configure `~/.ssh/config`,
replacing `<houston-ip>` with Houston's address:

```sshconfig
Host houston-01
  HostName <houston-ip>
  User capcom
  IdentityFile ~/.ssh/id_ed25519_homelab
  IdentitiesOnly yes
```

Verify Houston's SSH host key through a trusted record or local console,
then check `ssh houston-01 true`.

## Garage credentials

Provision the shared `cavespace-local-plan` reader and copy its private profile:

```bash
(cd infra/ansible && ansible-playbook playbooks/local-plan.yml --ask-become-pass)
umask 077
mkdir -p .secrets/terraform
scp houston-01:/srv/terraform/workspaces/garage-readonly.credentials .secrets/terraform/garage.credentials
chmod 600 .secrets/terraform/garage.credentials
```

The key reads the entire `terraform-state` bucket, including both roots,
without write, ownership or bucket-creation permissions. Provider API credentials
are separate. GitHub cannot return stored Actions secrets. Private input files
and credentials under `.secrets/` are ignored by Git.

## Provider inputs

Prepare the root you intend to plan. Edit private files in a local editor;
never put tokens or passwords in command arguments.

### Cloudflare

```bash
umask 077
mkdir -p .secrets/cloudflare
cp -n terraform/cloudflare/variables.tfvars.json.example .secrets/cloudflare/variables.tfvars.json
chmod 600 .secrets/cloudflare/variables.tfvars.json
```

Set `cloudflare_account_id` and `cloudflare_api_token` using your password manager
or a dedicated Cloudflare management API token that can read the R2 configuration.
Garage and R2 S3 access keys are not Cloudflare management API tokens.

### UniFi

```bash
umask 077
mkdir -p .secrets/unifi
cp -n terraform/unifi/variables.tfvars.json.example .secrets/unifi/variables.tfvars.json
chmod 600 .secrets/unifi/variables.tfvars.json
```

Set `unifi_auth` to the dedicated local UniFi credentials or API key.
A cloud-only UI login is not a local API credential. Keep `controller.url`
as `https://localhost:18443` and `controller.site` as the target Network site.
Houston must reach the controller at `192.168.1.1`.
Enroll and verify its [certificate in Keychain](unifi/CERTIFICATE.md)
before planning. Cloudflare does not require this certificate.

## SSH session

Keep this command running in the first terminal. Wait for `Local plan session
ready` before running Terraform; press Enter to close when finished.

```bash
ssh -T -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=15 -o ServerAliveCountMax=3 \
  -L 127.0.0.1:13900:127.0.0.1:3900 \
  -L 127.0.0.1:18443:192.168.1.1:443 \
  houston-01 'flock --exclusive /run/houston-terraform/operation.lock bash -c "echo Local plan session ready; read -r"'
```

This holds Houston's shared Terraform lock. Port `13900` forwards Garage for
both roots; `18443` is used only by UniFi. Forwarded ports bind to loopback.
Stop the plan if SSH disconnects. UniFi TLS verification stays enabled.

## Init and plan

In the second terminal, from the repository root, choose `unifi` or `cloudflare`:

```bash
set +x
umask 077
terraform_root=unifi # or cloudflare
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN AWS_SECURITY_TOKEN
unset AWS_DEFAULT_PROFILE TF_LOG TF_LOG_PATH TF_LOG_PROVIDER
unset UNIFI_USERNAME UNIFI_PASSWORD UNIFI_API_KEY UNIFI_API UNIFI_INSECURE UNIFI_SITE
unset UNIFI_CLOUD_CONNECTOR UNIFI_HARDWARE_ID
export AWS_SHARED_CREDENTIALS_FILE="$PWD/.secrets/terraform/garage.credentials"
export AWS_PROFILE=cavespace-local-plan
export TF_DATA_DIR="$PWD/.cache/terraform-${terraform_root}-local"
export TF_WORKSPACE=default
mkdir -p "$TF_DATA_DIR"
chmod 700 "$TF_DATA_DIR"

terraform -chdir="terraform/$terraform_root" init -reconfigure -input=false -lockfile=readonly \
  -backend-config=../garage.s3.tfbackend \
  -backend-config='endpoints={s3="http://127.0.0.1:13900"}'
terraform -chdir="terraform/$terraform_root" plan -input=false -detailed-exitcode \
  -var-file="../../.secrets/$terraform_root/variables.tfvars.json"
```

Each root uses its own metadata directory and state key:

| Root | Garage state key |
| --- | --- |
| `cloudflare` | `prod/homelab/terraform.tfstate` |
| `unifi` | `prod/unifi/terraform.tfstate` |

`init` does not discover `.tfbackend` files automatically. The first
`-backend-config` supplies the bucket and shared settings; the second selects
the local tunnel instead of Houston's port. Input `.tfvars` files configure
providers and resources, not the backend. A bare `init` in a fresh metadata
directory asks for the missing S3 bucket.

Plan exit codes: `0` means no changes, `2` means changes, `1` means failure.
Local plans reflect your checkout and live state; Actions creates its own
reviewed plan from validated `main`. Keep the default workspace and do not run
local apply, import, refresh or state mutations. Avoid saving plans containing
secrets. Close SSH after planning and clear the terminal configuration:

```bash
unset AWS_SHARED_CREDENTIALS_FILE AWS_PROFILE TF_DATA_DIR TF_WORKSPACE terraform_root
```
