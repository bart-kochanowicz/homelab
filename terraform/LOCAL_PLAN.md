# Local plans on macOS

Run commands from the repository root. Install the tools in `aqua.yaml` with
[aqua](https://aquaproj.github.io/docs/install), plus Ansible. Houston needs its
[host configuration](../infra/ansible/README.md); a rebuilt host also needs
[state recovery](R2_BACKUP.md#recovery).

## One-time setup

Configure `~/.ssh/config` with Houston's address and your authorized key.
Verify its host key through a trusted record or local console.

```sshconfig
Host houston-01
  HostName <houston-ip>
  User capcom
  IdentityFile ~/.ssh/id_ed25519_homelab
  IdentitiesOnly yes
```

Provision the shared read-only Garage profile:

```bash
(cd infra/ansible && ansible-playbook playbooks/local-plan.yml --ask-become-pass)
umask 077
mkdir -p .secrets/terraform
scp houston-01:/srv/terraform/workspaces/garage-readonly.credentials .secrets/terraform/garage.credentials
chmod 600 .secrets/terraform/garage.credentials
```

Choose `unifi` or `cloudflare`, copy its example and edit the private JSON file.
These files are ignored by Git; GitHub cannot return stored Actions secrets.

```bash
terraform_root=unifi
umask 077
mkdir -p ".secrets/$terraform_root"
cp -n "terraform/$terraform_root/variables.tfvars.json.example" ".secrets/$terraform_root/variables.tfvars.json"
chmod 600 ".secrets/$terraform_root/variables.tfvars.json"
```

| Root | Private inputs |
| --- | --- |
| `cloudflare` | Account ID and management API token with R2 read access; S3 keys are separate. |
| `unifi` | Local credentials or API key; keep `controller.url=https://localhost:18443` and select your site. |

For UniFi, Houston must reach `192.168.1.1`; enroll its
[certificate in Keychain](unifi/CERTIFICATE.md) before planning.

## Terminal 1: keep the SSH session open

Wait for `Local plan session ready`. This holds Houston's shared lock and
forwards Garage (`13900`) and UniFi (`18443`) to loopback; Cloudflare uses only Garage.

```bash
ssh -T -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=15 -o ServerAliveCountMax=3 \
  -L 127.0.0.1:13900:127.0.0.1:3900 \
  -L 127.0.0.1:18443:192.168.1.1:443 \
  houston-01 'flock --exclusive /run/houston-terraform/operation.lock bash -c "echo Local plan session ready; read -r"'
```

## Terminal 2: init and plan

From the repository root, set `terraform_root` to `unifi` or `cloudflare`:

```bash
set +x
umask 077
terraform_root=unifi
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
  -backend-config='endpoints={s3="http://127.0.0.1:13900"}' && \
terraform -chdir="terraform/$terraform_root" plan -input=false -detailed-exitcode \
  -var-file="../../.secrets/$terraform_root/variables.tfvars.json"
```

Each root has separate local metadata and its own [state key](README.md).
The backend file supplies the bucket; the endpoint override selects the SSH tunnel.
A bare `init` without these settings asks for the missing S3 bucket.
Exit codes: `0` no changes, `2` changes, `1` failure.

Stop Terraform if SSH disconnects. Use this read-only Garage key only for plans;
apply runs through Actions using its own reviewed plan. Keep TLS verification
enabled and avoid saving plans containing secrets.

When finished, press Enter in terminal 1 and clear terminal 2:

```bash
unset AWS_SHARED_CREDENTIALS_FILE AWS_PROFILE TF_DATA_DIR TF_WORKSPACE terraform_root
```
