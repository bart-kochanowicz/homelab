# Local UniFi plans

Use the Terraform version pinned in `aqua.yaml` and the committed provider lock
file. Local plans read production state and query UniFi; apply runs on Houston
through [Actions](README.md).

## Credentials

Provision Garage's `cavespace-local-plan` key from the repository root:

```bash
(cd infra/ansible && ansible-playbook playbooks/local-plan.yml --ask-become-pass)
umask 077
mkdir -p .secrets/unifi
scp houston-01:/srv/terraform/workspaces/garage-readonly.credentials .secrets/unifi/garage.credentials
chmod 600 .secrets/unifi/garage.credentials
```

The key has bucket-wide read access to `terraform-state`, without write,
ownership or bucket-creation permissions. UniFi API permissions come from
`unifi_auth`. Keep `.secrets/unifi/variables.tfvars.json` private, with
`unifi_auth` in the format described by `variables.tf`.
Store the verified controller certificate as
`.secrets/unifi/controller-certificate.pem`. `.secrets/` is ignored by Git.

On macOS, the provider uses Keychain for certificate trust. Verify the certificate
fingerprint against the controller, then trust it for SSL to `localhost`:

```bash
openssl x509 -in .secrets/unifi/controller-certificate.pem -noout -fingerprint -sha256
security add-trusted-cert -r trustRoot -p ssl -s localhost \
  -k "$HOME/Library/Keychains/login.keychain-db" \
  .secrets/unifi/controller-certificate.pem
```

## SSH session

Keep this command running in a separate terminal. Wait for `Local plan session
ready` before running Terraform; press Enter to close after the plan finishes.

```bash
ssh -T -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=15 -o ServerAliveCountMax=3 \
  -L 127.0.0.1:13900:127.0.0.1:3900 \
  -L 127.0.0.1:18443:192.168.1.1:443 \
  houston-01 'flock --exclusive /run/houston-terraform/operation.lock bash -c "echo Local plan session ready; read -r"'
```

The session holds the same lock as Houston's Terraform wrapper. Garage and
controller traffic use SSH forwards bound to loopback. The certificate includes
`localhost`; TLS verification stays enabled. Stop the plan if SSH disconnects.

## Terraform

Run from the repository root in the second terminal:

```bash
set +x
umask 077
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN AWS_SECURITY_TOKEN
unset AWS_DEFAULT_PROFILE TF_LOG TF_LOG_PATH TF_LOG_PROVIDER
unset UNIFI_USERNAME UNIFI_PASSWORD UNIFI_API_KEY UNIFI_API UNIFI_INSECURE UNIFI_SITE
unset UNIFI_CLOUD_CONNECTOR UNIFI_HARDWARE_ID
export AWS_SHARED_CREDENTIALS_FILE="$PWD/.secrets/unifi/garage.credentials"
export AWS_PROFILE=cavespace-local-plan
export TF_DATA_DIR="$PWD/.cache/terraform-unifi-local"
export TF_WORKSPACE=default
mkdir -p "$TF_DATA_DIR"
chmod 700 "$TF_DATA_DIR"

terraform -chdir=terraform/unifi init -reconfigure -input=false -lockfile=readonly \
  -backend-config=../garage.s3.tfbackend \
  -backend-config='endpoints={s3="http://127.0.0.1:13900"}'
terraform -chdir=terraform/unifi plan -input=false -detailed-exitcode \
  -var-file=../../.secrets/unifi/variables.tfvars.json \
  -var='controller={url="https://localhost:18443",site="default"}'
```

Exit codes: `0` means no changes, `2` means changes, `1` means failure. Plans
reflect the current checkout and live state; Actions builds its own reviewed
plan from validated `main`. Keep the default workspace and do not run local
apply, import, refresh or state mutations. Avoid saving plans containing secrets.

After the plan, close SSH and clear the session configuration:

```bash
unset AWS_SHARED_CREDENTIALS_FILE AWS_PROFILE TF_DATA_DIR TF_WORKSPACE
```
