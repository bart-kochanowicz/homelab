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

The future upload step will use a distinct UTC timestamp for every snapshot,
for example `backups/prod/cloudflare/2026-10-01T12-00-00Z.tfstate`. Never reuse a
snapshot key. Only the `backups/` prefix is protected by this rule.

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

Snapshot upload and a restore rehearsal are separate steps. This bucket
alone does not create backups. Before placing important state in Garage,
verify upload, rejection of overwrite/deletion, and recovery using an
isolated state key.

## Credentials for the later upload step

Create a separate R2 S3 credential with `Object Read & Write`, scoped only to
this bucket, when implementing the upload step. It must not have Admin or
bucket configuration permissions. Keep it in a secret store outside Git.
These permissions support bucket scoping; do not assume they restrict the
credential to a prefix. See [R2 authentication](https://developers.cloudflare.com/r2/api/tokens/).

## Recovery and removal

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
