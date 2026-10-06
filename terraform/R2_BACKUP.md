# Terraform state backups in R2

## Purpose and configuration

Garage on Houston's SSD is the primary Terraform backend. Cloudflare R2 holds
verified off-site snapshots in the private `houston-terraform-state-backups`
bucket. The production Terraform root currently manages these three R2 resources:

| Resource | Desired setting |
| --- | --- |
| Bucket | Standard storage, `weur` location hint. |
| Managed domain | Public `r2.dev` access disabled. |
| Bucket Lock | `backups/` protected from overwrite and deletion for 90 days. |

The provider is pinned to 5.17.0. The bucket and lock have `prevent_destroy`
guards. Keep their resource blocks in configuration; removing a block also
removes its lifecycle guard. The location is a best-effort hint, not a
jurisdiction guarantee.
No custom public domain, Worker binding, expiration, or automatic object
cleanup is configured. Objects remain stored after protection expires.

Snapshots have unique keys such as
`backups/prod/homelab/<UTC-timestamp>-<uuid>.tfstate`. Terraform state can
contain secrets; keep the bucket private and keep object keys paired with
the SHA256 from the corresponding successful receipt.

[Bucket Lock](https://developers.cloudflare.com/r2/buckets/bucket-locks/)
protects objects but does not stop an administrator from changing the rules.
Keep the Cloudflare management credential separate from the bucket-scoped
S3 upload credential. Inspect bucket settings as well as Terraform plans;
the pinned provider does not refresh the managed-domain setting from the API.

## Credentials

Production workflows receive credentials from the private repository's
Actions secrets. See the [automation guide](https://github.com/bart-kochanowicz/homelab-automation#github-configuration)
for their names and permissions.

For manual operations, use Bash on Houston from the private checkout on the
SSD. Load Garage credentials without displaying them, then enter the separate
R2 S3 keys at hidden prompts:

```bash
set +x
umask 077
AWS_ACCESS_KEY_ID=$(sudo sed -n 's/^GARAGE_DEFAULT_ACCESS_KEY=//p' /srv/terraform/garage/s3-bootstrap.env)
AWS_SECRET_ACCESS_KEY=$(sudo sed -n 's/^GARAGE_DEFAULT_SECRET_KEY=//p' /srv/terraform/garage/s3-bootstrap.env)
: "${AWS_ACCESS_KEY_ID:?Garage access key was not loaded}"
: "${AWS_SECRET_ACCESS_KEY:?Garage secret key was not loaded}"
export AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY
unset AWS_SESSION_TOKEN AWS_SECURITY_TOKEN AWS_PROFILE AWS_DEFAULT_PROFILE

export R2_ACCOUNT_ID=f572e035612c37b4ae02d5f64e0f04e1
read -r -s -p 'R2 Access Key ID: ' R2_ACCESS_KEY_ID
printf '\n'
read -r -s -p 'R2 Secret Access Key: ' R2_SECRET_ACCESS_KEY
printf '\n'
export R2_ACCESS_KEY_ID R2_SECRET_ACCESS_KEY
```

The R2 S3 credential needs **Object Read & Write**, scoped to this bucket.
It does not need bucket configuration permissions; bucket scoping does not
imply prefix scoping. Store it in a password manager. The provisioning token
uses **Workers R2 Storage Write** and is separate from both S3 key pairs.

## Production snapshot

Initialize each root through [Cloudflare backend operations](BACKEND.md#verify-the-production-root)
or [UniFi operations](unifi/README.md), then run:

```bash
./scripts/backup-terraform-state.sh terraform prod/homelab
./scripts/backup-terraform-state.sh terraform/unifi prod/unifi
```

Successful receipts report `Verified R2 backup: s3://…/backups/prod/<root>/…`
and `SHA256: …`, where `<root>` is `homelab` or `unifi`.
The second argument chooses the R2 snapshot prefix, not the backend: the first
argument must point to the initialized production root and correct workspace.

The script pulls state through Houston's locked Terraform wrapper, validates
its JSON structure without printing it, uploads with `If-None-Match: *`, then
downloads and compares the bytes. Credentials reach curl over stdin rather
than process arguments. Failed or ambiguous PUTs are not automatically retried.
Successful runs remove private staging; failures retain it and print its path.
Upload verification does not itself prove that state can be restored.

## Upload and read back an isolated snapshot

The disposable diagnostic state contains only `terraform_data.backend_check`.
It has its own Garage key, separate from production. With the credentials
above loaded, initialize and review this example:

```bash
/usr/local/bin/terraform -chdir=terraform/examples/garage-backend init \
  -backend-config=../../garage.s3.tfbackend
/usr/local/bin/terraform -chdir=terraform/examples/garage-backend plan
/usr/local/bin/terraform -chdir=terraform/examples/garage-backend apply
./scripts/backup-terraform-state.sh terraform/examples/garage-backend checks/garage-backend
```

Approve only the built-in check marker. Expect a verified receipt under
`backups/checks/garage-backend/`. Use the matching receipt for the restore
rehearsal below. The [Ansible staging setup](../infra/ansible/README.md#workspaces-and-backup-staging)
provides private SSD storage and required tools.

## Rehearse an isolated restore

This diagnostic restores only a completed check marker into a fresh Garage
key. It rejects production infrastructure snapshots and empty/destroyed check
states. Load the credentials above, then provide a matching key and hash:

```bash
read -r -p 'R2 object key (backups/checks/garage-backend/...tfstate): ' RESTORE_OBJECT_KEY
read -r -p 'Backup SHA256: ' RESTORE_SHA256
./scripts/check-terraform-state-restore.sh "$RESTORE_OBJECT_KEY" "$RESTORE_SHA256"
```

The object key excludes `s3://houston-terraform-state-backups/`. The script
checks SHA256 and the marker before initializing a new
`checks/garage-restore/<uuid>/terraform.tfstate` destination. It verifies
backend settings, pushes the snapshot with Terraform safety checks intact,
compares resource attributes, IDs, and outputs, and requires an unchanged plan.
The original Garage state and R2 object remain unchanged.

Expect `Restore verified: terraform_data.backend_check`, the fresh Garage key,
and a private workspace path. Success removes downloaded snapshot copies
and keeps the workspace for inspection. Failure keeps private staging.

For deliberate cleanup, set `RESTORE_DIRECTORY` to the exact printed module
workspace and run, as the account that owns it:

```bash
/usr/local/bin/terraform -chdir="$RESTORE_DIRECTORY" destroy
```

Approve only deletion of `terraform_data.backend_check`. For runner-owned
workspaces, use sudo as `runner-svc`, preserving only the two Garage credential
variables. After preserving needed files, remove only that specific staging
directory. The empty rehearsal state object remains in Garage.

A successful diagnostic proves restore of the check marker only. Production
recovery needs the matching configuration and provider versions, a deliberately
selected backend, and review against existing infrastructure.

## Verify rejection of overwrite and deletion

With the R2 credentials loaded:

```bash
./scripts/check-r2-retention.sh
```

The script creates two disposable UUID-named probes. Its unprotected control
under `checks/retention/` must allow overwrite and deletion. Its protected
probe under `backups/checks/retention/` must reject both operations and retain
the original bytes. HTTP 403 or 409 counts only with the exact
`ObjectLockedByBucketPolicy` error; a generic conflict, permission failure,
or network error is not proof of retention.

Expect `Retention verified: overwrite and deletion rejected by Bucket Lock.`
Success removes the local staging and unprotected control. The protected tiny
probe remains under the existing 90-day rule; do not weaken protection to
remove it. Failed runs print their two exact keys and retain local files.
Inspect those keys before cleanup because an interrupted request can take effect.

This test checks enforcement at the time of the run. It does not wait for
expiry or prove that an administrator cannot change the policy. Inspect the
bucket's Settings for the enabled `backups/` rule with age 90 days, disabled
`r2.dev`, and no custom public domains.

## GitHub Actions workflows

A successful **Validate** push run on `homelab/main` triggers production apply
in the private [homelab-automation repository](https://github.com/bart-kochanowicz/homelab-automation).
That workflow verifies the commit and production backend, saves a Terraform
plan, verifies a pre-apply snapshot, applies, then attempts a post-apply
snapshot. Production receipts use `backups/prod/homelab/`.

Public CI and dispatch use GitHub-hosted runners. Trusted operations run on
Houston without sudo and use the shared Terraform wrapper. Workflow concurrency
serializes private jobs; the host lock covers each Terraform command, not the
whole sequence. Avoid intervening manual state changes: Terraform rejects a
saved plan if state changes after planning.

The private repository also provides manual marker backup, apply, and restore
diagnostics under `checks/`. They preserve production state. Trigger, secret,
retry, and failure instructions live in the
[private operations guide](https://github.com/bart-kochanowicz/homelab-automation).

## Recovery and removal

After a failed backup, preserve retained staging until the failure is
understood and current state is safely backed up. A new attempt uses a new
object key. The upload script never deletes R2 objects or restores state.
A pre-apply backup failure stops production apply. After a failed apply, the
workflow attempts another backup; a post-apply backup failure does not undo
an apply. Inspect the result and capture current state before retrying.

Rebuild a lost host through Ansible before restoring production state. Restore
requires matching code/provider versions, verified recovery material, and a
reviewed destination backend. Never automatically overwrite state after a
failed apply.

Removing backup storage requires preserving snapshots elsewhere, deliberately
changing the `prevent_destroy` guards and lock rules, and emptying the bucket.
Ordinary `terraform destroy` is blocked by those guards.

When manual operations are finished, clear credentials from the shell:

```bash
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY
unset R2_ACCOUNT_ID R2_ACCESS_KEY_ID R2_SECRET_ACCESS_KEY
unset RESTORE_OBJECT_KEY RESTORE_SHA256 RESTORE_DIRECTORY
```

References: [R2 authentication](https://developers.cloudflare.com/r2/api/tokens/),
[S3 API](https://developers.cloudflare.com/r2/api/s3/api/),
[error codes](https://developers.cloudflare.com/r2/api/error-codes/),
[Terraform state push](https://developer.hashicorp.com/terraform/cli/commands/state/push).
