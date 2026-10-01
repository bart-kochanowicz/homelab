# Off-site Terraform state backup storage

## Purpose and configuration

Garage is the primary backend on Houston's SSD. Cloudflare R2 provides storage
outside the host so state snapshots can survive an SSD or host failure.
The existing Cloudflare module manages three R2 resources using the already
pinned provider version `5.17.0`:

| Resource | Desired setting |
| --- | --- |
| Bucket | `houston-terraform-state-backups`, Standard storage, `weur` location hint |
| Managed public domain | `r2.dev` access disabled |
| Bucket Lock | Objects under `backups/` protected from deletion and overwrite for 90 days |

The location is a best-effort hint, not a jurisdiction guarantee. No custom
public domain or Worker binding is created for this bucket. Keep it private:
Terraform state can contain credentials and other sensitive values.

The upload script uses a UTC timestamp and a random UUID for every snapshot,
for example `backups/prod/cloudflare/2026-10-01T12-00-00Z-<uuid>.tfstate`. Never
reuse a snapshot key. Only the `backups/` prefix is protected by this rule.

Ninety days is the minimum protection period measured from each object's age.
It is not an expiration policy: there is no automatic deletion or storage
class transition. Objects remain stored after the lock expires. The bucket
and lock configuration also have Terraform `prevent_destroy` guards.

[Bucket Lock](https://developers.cloudflare.com/r2/buckets/bucket-locks/)
prevents object deletion and overwriting, but an administrator with bucket
configuration permissions can change or remove its rules. The provisioning
credential must therefore remain separate from the future upload credential.
The resources use the pinned provider's
[bucket](https://github.com/cloudflare/terraform-provider-cloudflare/blob/v5.17.0/docs/resources/r2_bucket.md),
[managed domain](https://github.com/cloudflare/terraform-provider-cloudflare/blob/v5.17.0/docs/resources/r2_managed_domain.md),
and [lock](https://github.com/cloudflare/terraform-provider-cloudflare/blob/v5.17.0/docs/resources/r2_bucket_lock.md)
schemas.

## Provision and verify

Enable R2 on the existing Cloudflare account if it is not already enabled.
The existing Terraform `cloudflare_api_token` needs the account permission
`Workers R2 Storage Write` in addition to its Tunnel, Access, and DNS
permissions. Keep its value in the existing secret variable store.
This is a Cloudflare management API token, not a Garage or R2 S3 access key.

Run this step through the existing Terraform root configuration and its
existing remote state, including the existing HCP Terraform workspace if
that is where the Cloudflare resources are managed. A fresh Houston checkout
without that backend configuration does not have the existing Cloudflare
state. The isolated Garage example is only a backend check.

Review the full plan. The intended additions are:

- `module.cloudflare.cloudflare_r2_bucket.terraform_state_backups`
- `module.cloudflare.cloudflare_r2_managed_domain.terraform_state_backups`
- `module.cloudflare.cloudflare_r2_bucket_lock.terraform_state_backups`

The expected summary is `3 to add, 0 to change, 0 to destroy`. Resolve any
unrelated changes before approving the run. The new output is
`terraform_state_backup_bucket = "houston-terraform-state-backups"`.

After applying, inspect the R2 bucket's Settings in the Cloudflare dashboard:

- Public access through `r2.dev` is disabled and there are no custom domains.
- The enabled lock rule covers `backups/`, with a 90-day age condition.
- A subsequent Terraform plan reports no changes.

A restore rehearsal and verification of overwrite/deletion rejection are
still required before placing important state in Garage. The upload step
below verifies a snapshot by downloading and comparing its bytes; it does
not restore a Terraform backend.

## Upload credentials

Create a separate R2 S3 credential with `Object Read & Write`, scoped only to
this bucket. It must not have Admin or bucket configuration permissions.
Save its Access Key ID and Secret Access Key in your password manager. Keep
them outside Git. These permissions support bucket scoping; do not assume
they restrict the credential to a prefix. See [R2 authentication](https://developers.cloudflare.com/r2/api/tokens/).

## Upload and read back an isolated snapshot

Apply the [Ansible staging setup](../infra/ansible/README.md#step-10--prepare-state-backup-staging)
first. Run the commands below in Bash, from the current repository checkout
on Houston's SSD. Initialization needs Garage credentials too. Applying this
example creates only the built-in marker, or leaves an existing marker
unchanged.

Enter the separate R2 credential at prompts so its values do not enter shell
history. Commands below assume Bash:

```bash
set +x
umask 077
AWS_ACCESS_KEY_ID=$(sudo sed -n 's/^GARAGE_DEFAULT_ACCESS_KEY=//p' /srv/terraform/garage/s3-bootstrap.env)
AWS_SECRET_ACCESS_KEY=$(sudo sed -n 's/^GARAGE_DEFAULT_SECRET_KEY=//p' /srv/terraform/garage/s3-bootstrap.env)
: "${AWS_ACCESS_KEY_ID:?Garage access key was not loaded}"
: "${AWS_SECRET_ACCESS_KEY:?Garage secret key was not loaded}"
export AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY
unset AWS_SESSION_TOKEN AWS_SECURITY_TOKEN AWS_PROFILE AWS_DEFAULT_PROFILE

/usr/local/bin/terraform -chdir=terraform/examples/garage-backend init -backend-config=../../garage.s3.tfbackend
/usr/local/bin/terraform -chdir=terraform/examples/garage-backend apply

read -r -p 'Cloudflare account ID: ' R2_ACCOUNT_ID
read -r -s -p 'R2 Access Key ID: ' R2_ACCESS_KEY_ID; printf '\n'
read -r -s -p 'R2 Secret Access Key: ' R2_SECRET_ACCESS_KEY; printf '\n'
export R2_ACCOUNT_ID R2_ACCESS_KEY_ID R2_SECRET_ACCESS_KEY

./scripts/backup-terraform-state.sh terraform/examples/garage-backend checks/garage-backend

unset R2_ACCOUNT_ID R2_ACCESS_KEY_ID R2_SECRET_ACCESS_KEY
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY
```

The script calls `/usr/local/bin/terraform state pull`, which acquires the
shared Houston process lock. It reads the state as it exists at that point;
a subsequent Terraform operation can run while that snapshot is uploaded.
This is a manual snapshot tool, not yet an apply-and-backup workflow.
The state name selects the R2 path only; it does not choose the Terraform
backend or workspace. Supply the matching initialized root directory.

The script validates the state JSON without displaying it, sends a signed
HTTPS PUT to R2 with `If-None-Match: *`, and downloads the result for byte
comparison. [R2 supports this conditional PUT](https://developers.cloudflare.com/r2/api/s3/api/).
The existing `curl` tool supplies [AWS Signature V4 authentication](https://curl.se/docs/manpage.html#--aws-sigv4);
no AWS CLI or AWS account is required. Credentials are passed to curl on
stdin, not in command-line arguments. Upload errors exit nonzero. PUT is not
automatically retried because a failed response can follow a successful write.

Expect `Verified R2 backup: s3://...` and a SHA256 hash. In the R2 dashboard,
check that the named object exists under `backups/checks/garage-backend/`.
Running the script again creates a separate object rather than overwriting
one. Successful runs remove staging; the R2 snapshots remain protected by
the bucket's lock rule. Readback verification is a check of upload/download,
not a completed restore rehearsal.

## Rehearse an isolated restore

Run `scripts/check-terraform-state-restore.sh` on Houston to recover the
completed example marker from an R2 snapshot into a fresh Garage state key.
The script accepts only `backups/checks/garage-backend/` objects containing
`terraform_data.backend_check`. If the snapshot is from an empty/destroyed
example, apply the example and create a new backup first.

In Bash, load Garage credentials again if you previously unset them:

```bash
set +x
umask 077
AWS_ACCESS_KEY_ID=$(sudo sed -n 's/^GARAGE_DEFAULT_ACCESS_KEY=//p' /srv/terraform/garage/s3-bootstrap.env)
AWS_SECRET_ACCESS_KEY=$(sudo sed -n 's/^GARAGE_DEFAULT_SECRET_KEY=//p' /srv/terraform/garage/s3-bootstrap.env)
: "${AWS_ACCESS_KEY_ID:?Garage access key was not loaded}"
: "${AWS_SECRET_ACCESS_KEY:?Garage secret key was not loaded}"
export AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY
unset AWS_SESSION_TOKEN AWS_SECURITY_TOKEN AWS_PROFILE AWS_DEFAULT_PROFILE

read -r -p 'Cloudflare account ID: ' R2_ACCOUNT_ID
read -r -s -p 'R2 Access Key ID: ' R2_ACCESS_KEY_ID; printf '\n'
read -r -s -p 'R2 Secret Access Key: ' R2_SECRET_ACCESS_KEY; printf '\n'
export R2_ACCOUNT_ID R2_ACCESS_KEY_ID R2_SECRET_ACCESS_KEY

read -r -p 'R2 object key (backups/checks/garage-backend/...tfstate): ' RESTORE_OBJECT_KEY
read -r -p 'SHA256 printed by the backup script: ' RESTORE_SHA256
./scripts/check-terraform-state-restore.sh "$RESTORE_OBJECT_KEY" "$RESTORE_SHA256"
```

Use the object key from the successful backup output, without the
`s3://houston-terraform-state-backups/` prefix, and its printed SHA256 hash.
Keep the hash with your verification notes so a later restore can check the
selected snapshot independently of R2. This rehearsal verifies the transfer
and state recovery; it is not a cryptographic authenticity signature.

The script creates a private workspace under SSD backup staging and downloads
the R2 snapshot through signed HTTPS. It checks SHA256 and the example marker
before initializing the copied `examples/garage-restore` configuration at
`checks/garage-restore/<uuid>/terraform.tfstate`. Each invocation has a fresh
key and private Terraform metadata. It verifies the initialized bucket, key,
region, and loopback endpoint before `state push`. Every Terraform command
uses the Houston wrapper. Inherited workspace/data-directory/command options
are cleared for this rehearsal.

[State push](https://developer.hashicorp.com/terraform/cli/commands/state/push)
restores the snapshot without disabling Terraform's safety checks. No
`apply`, migration, or force flag is used. The fresh destination can receive
new lineage/serial metadata, so verification compares resource attributes,
IDs, and outputs, then requires `plan -detailed-exitcode` to return `0`.
The source Garage state and the R2 object are not modified.

Expect `terraform_data.backend_check`, a plan with no changes, and
`Restore verified: terraform_data.backend_check`. Record the printed Garage
key and private workspace as evidence of the rehearsal. Success removes the
temporary snapshot copies and retains the workspace for inspection. Failure
returns nonzero and retains private files for troubleshooting.

To clean up this disposable rehearsal, set `RESTORE_DIRECTORY` to the exact
private workspace printed by the script. With Garage credentials still
loaded, run:

```bash
/usr/local/bin/terraform -chdir="$RESTORE_DIRECTORY" destroy
```

Approve only deletion of `terraform_data.backend_check`. The empty rehearsal
state object remains in Garage. Remove the printed private staging directory
only after it contains no needed files. Each future rehearsal uses a new key.
When finished, clear the credentials:

```bash
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY
unset R2_ACCOUNT_ID R2_ACCESS_KEY_ID R2_SECRET_ACCESS_KEY
unset RESTORE_OBJECT_KEY RESTORE_SHA256 RESTORE_DIRECTORY
```

A successful rehearsal checks restore of the built-in example only. Recovery
of real infrastructure requires its matching configuration and provider
versions, review of any plan against the existing resources, and deliberate
selection of the destination backend. This script rejects infrastructure
snapshots. Retention overwrite/deletion rejection and the trusted runner
workflow are separate checks still to complete.

## Recovery and removal

If snapshot upload or readback fails, the script reports the retained private
staging directory on the SSD. Keep it until the backup is safely recovered.
Check credentials, network access, and R2 settings; another run pulls a fresh
snapshot under a new key. An interrupted PUT may have created an R2 object
although verification failed. Use the R2 dashboard to inspect it before any
manual recovery. Remove only your retained staging directory after preserving
its needed snapshot. The script never deletes R2 objects.

If provisioning fails, check R2 activation and the Terraform token's account
permissions, then review a new plan and retry. If the managed domain or lock
configuration drifts, review and apply Terraform to restore the settings.
Changing the lock policy can affect existing snapshots, so review it before
applying.

Before removing this storage, preserve and verify any needed snapshots in
another off-site location. Removal requires an explicit reviewed change to
the `prevent_destroy` guards, a deliberate change to the lock rules, and
emptying the bucket before deletion. Do not use root-wide `terraform destroy`
as cleanup for the backup bucket: that root also manages Tunnel, Access, and
DNS resources.
