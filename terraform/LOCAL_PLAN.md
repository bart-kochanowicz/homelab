# Local plans on macOS

After setup, open the SSH tunnel and run `terraform plan` inside either root.
Terraform automatically reads `terraform.tfvars` and the backend settings
saved by `init`. No wrapper or per-session environment variables are needed.

## One-time setup

From the repository root, install the tools in `aqua.yaml` with
[aqua](https://aquaproj.github.io/docs/install), plus Ansible. Houston needs its
[host configuration](../infra/ansible/README.md) and existing deployment state.
Configure a verified `houston-01` SSH alias for `capcom` with your authorized key:

```sshconfig
Host houston-01
  HostName <houston-ip>
  User capcom
  IdentityFile ~/.ssh/id_ed25519_homelab
  IdentitiesOnly yes
```

Provision and download the shared read-only Garage profile:

```bash
(cd infra/ansible && ansible-playbook playbooks/local-plan.yml --ask-become-pass)
umask 077
mkdir -p .secrets/terraform
scp houston-01:/srv/terraform/workspaces/garage-readonly.credentials .secrets/terraform/garage.credentials
chmod 600 .secrets/terraform/garage.credentials
```

Choose `terraform/unifi` or `terraform/cloudflare`. In that directory, prepare
and edit the ignored local inputs. Keep provider credentials in this file:

```bash
cp -n terraform.tfvars.example terraform.tfvars
chmod 600 terraform.tfvars
```

| Root | Inputs |
| --- | --- |
| `cloudflare` | Account ID and management API token with R2 read access; S3 keys are separate. |
| `unifi` | Local credentials or API key; `controller.url=https://localhost:18443` and your site. |

UniFi also requires Houston access to `192.168.1.1` and the verified
[controller certificate in Keychain](unifi/CERTIFICATE.md).

## Terminal 1: tunnel

Keep this session open; wait for `Local plan session ready`. It holds Houston's
shared lock and forwards Garage and UniFi to loopback. Cloudflare uses only Garage.

```bash
ssh -T -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=15 -o ServerAliveCountMax=3 \
  -L 127.0.0.1:13900:127.0.0.1:3900 \
  -L 127.0.0.1:18443:192.168.1.1:443 \
  houston-01 'flock --exclusive /run/houston-terraform/operation.lock bash -c "echo Local plan session ready; read -r"'
```

## Initialize each root once

With the tunnel open, run from the chosen root directory:

```bash
terraform init -reconfigure -input=false -lockfile=readonly \
  -backend-config=../garage.s3.tfbackend \
  -backend-config=../garage.local.s3.tfbackend
```

This records the tunnel endpoint, read-only profile and credential-file path
in that root's ignored `.terraform/` metadata. Credentials stay in their private
file. Repeat for a fresh checkout or changed backend settings. Use a shell
without `TF_DATA_DIR`, `TF_WORKSPACE`, AWS credential or Terraform CLI/log overrides.

## Terminal 2: plan

```bash
cd terraform/unifi
terraform plan
```

Use `terraform/cloudflare` for Cloudflare. Run `init` again after module/provider
changes, with the backend settings above. Keep the default workspace and TLS
verification enabled. Local access is for plans; apply runs through
[Actions approval](README.md#plan-and-apply).

Stop Terraform if SSH disconnects. Press Enter in terminal 1 when finished.
