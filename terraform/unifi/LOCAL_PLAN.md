# Local UniFi plans

Use the Terraform version pinned in `aqua.yaml` and the committed provider lock
file. Local plans read production state and query UniFi; apply runs on Houston
through [Actions](README.md).

## Prerequisites

Run commands from a checkout of this repository on macOS. Install aqua, Ansible
and GitHub CLI; OpenSSH, OpenSSL and Python 3 must be available. Run `aqua install`
and add aqua's tool directory to `PATH` as described in its
[installation guide](https://aquaproj.github.io/docs/install).
Authenticate `gh auth login` with access to the private automation repository.

Houston must have its [host configuration](../../infra/ansible/README.md) applied.
Keep the production state for existing deployments; if Houston was rebuilt,
follow [state recovery](../R2_BACKUP.md#recovery) before planning.
Restore the operator SSH key or authorize a new key through an existing admin
connection. Configure `~/.ssh/config`, replacing `<houston-ip>` with its address:

```sshconfig
Host houston-01
  HostName <houston-ip>
  User capcom
  IdentityFile ~/.ssh/id_ed25519_homelab
  IdentitiesOnly yes
```

Verify Houston's SSH host key through a trusted record or local console, then
check `ssh houston-01 true`. Houston must reach the controller at `192.168.1.1`.

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
`unifi_auth`. Restore the dedicated local UniFi account from a password manager,
or create a local-only account with access to read Network configuration through
the console's administrator settings. A cloud-only UI login is not a local API
credential. GitHub cannot return the stored `UNIFI_AUTH` secret.

Create the private input file without overwriting an existing one:

```bash
cp -n terraform/unifi/variables.tfvars.json.example .secrets/unifi/variables.tfvars.json
chmod 600 .secrets/unifi/variables.tfvars.json
```

Edit its username and password in a local editor. `.secrets/` is ignored by Git.

## Controller certificate

The gateway generates its certificate; the Mac needs only the public certificate,
not a new certificate or the gateway's private key. For an enrolled controller,
download the approved certificate from the private automation repository:

```bash
gh api repos/bart-kochanowicz/homelab-automation/actions/variables/UNIFI_CA_CERT_PEM \
  --jq '.value' > .secrets/unifi/controller-certificate.pem
openssl x509 -in .secrets/unifi/controller-certificate.pem -noout -fingerprint -sha256 -dates
openssl x509 -in .secrets/unifi/controller-certificate.pem -noout -text
```

The repository variable is the approved certificate record. Check validity dates
and the `localhost` subject alternative name required by the tunnel below.

For first enrollment or a certificate replacement, obtain a candidate from the
controller through Houston:

```bash
mkdir -p .cache
ssh houston-01 'openssl s_client -connect 192.168.1.1:443 -servername unifi.local </dev/null 2>/dev/null' \
  | openssl x509 -outform PEM -out .cache/unifi-controller-candidate.pem
openssl x509 -in .cache/unifi-controller-candidate.pem -noout -fingerprint -sha256 -dates
openssl x509 -in .cache/unifi-controller-candidate.pem -noout -text
```

Verify its SHA-256 fingerprint through the console certificate viewer over a
trusted administration connection or a trusted certificate backup. Check dates
and the `localhost` SAN; successful download alone does not establish trust.
After verification, register this public certificate for Actions and the Mac:

```bash
gh variable set UNIFI_CA_CERT_PEM --repo bart-kochanowicz/homelab-automation \
  < .cache/unifi-controller-candidate.pem
cp .cache/unifi-controller-candidate.pem .secrets/unifi/controller-certificate.pem
```

On macOS, the provider uses Keychain for certificate trust. Add the approved
certificate for SSL to `localhost`, authorizing the macOS prompt if requested:

```bash
security add-trusted-cert -r trustRoot -p ssl -s localhost \
  -k "$HOME/Library/Keychains/login.keychain-db" \
  .secrets/unifi/controller-certificate.pem
security verify-cert -c .secrets/unifi/controller-certificate.pem -p ssl -s localhost
```

Verification must succeed before planning. Repeat enrollment and update Actions
and Keychain trust when the gateway certificate changes or expires.

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
