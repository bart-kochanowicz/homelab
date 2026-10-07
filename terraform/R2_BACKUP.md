# Terraform state backups in R2

Garage is the primary backend. R2 stores verified off-site snapshots in
private `houston-terraform-state-backups`:

| Resource | Configuration |
| --- | --- |
| Bucket | Standard storage, `weur` location hint. |
| Managed domain | Public `r2.dev` access disabled. |
| Bucket Lock | `backups/` protected from overwrite and deletion for 90 days. |

The bucket and lock have `prevent_destroy` guards. Keep their resource blocks:
removing a block removes its guard. Objects remain stored after protection
expires; no automatic cleanup is configured. Bucket Lock does not prevent an
administrator from changing its rules. The pinned provider does not refresh
the managed-domain setting, so also inspect the bucket settings.

State can contain secrets. Keep snapshots private and pair each unique object
key with the SHA256 from its successful receipt.

## Credentials

Production workflows use the private repository's
[Actions secrets](https://github.com/bart-kochanowicz/homelab-automation#github-configuration).
For manual operations, use Bash in a private checkout on Houston:

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
Bucket scoping does not restrict prefixes. The separate provisioning token
needs **Workers R2 Storage Write**. Store keys in a password manager.

## Production snapshot

With credentials loaded and [the Cloudflare root initialized](BACKEND.md#verify-the-production-root):

```bash
./scripts/backup-terraform-state.sh terraform/cloudflare prod/homelab
/usr/local/bin/terraform -chdir=terraform/unifi init -input=false -lockfile=readonly \
  -backend-config=../garage.s3.tfbackend
./scripts/backup-terraform-state.sh terraform/unifi prod/unifi
```

The first argument selects the initialized root and workspace; the second
selects the snapshot prefix. A successful receipt contains
`s3://houston-terraform-state-backups/backups/prod/<root>/<timestamp>-<uuid>.tfstate`
and `SHA256: …`.

The script pulls state through the shared Terraform lock, validates JSON,
uploads with `If-None-Match: *`, and compares downloaded bytes. Credentials
reach curl through stdin. An ambiguous PUT is not retried: it may have stored
the object. Success removes private staging; failure prints its retained path.
Verified upload alone does not prove recovery.

## Rehearse an isolated restore

The diagnostic uses only `terraform_data.backend_check` in a separate Garage
key. With credentials loaded:

```bash
/usr/local/bin/terraform -chdir=terraform/examples/garage-backend init \
  -backend-config=../../garage.s3.tfbackend
/usr/local/bin/terraform -chdir=terraform/examples/garage-backend apply
./scripts/backup-terraform-state.sh terraform/examples/garage-backend checks/garage-backend

read -r -p 'R2 object key (backups/checks/garage-backend/...tfstate): ' RESTORE_OBJECT_KEY
read -r -p 'Backup SHA256: ' RESTORE_SHA256
./scripts/check-terraform-state-restore.sh "$RESTORE_OBJECT_KEY" "$RESTORE_SHA256"
```

Approve only the marker and use its matching receipt. The object key excludes
the `s3://houston-terraform-state-backups/` prefix. Restore rejects production
snapshots and empty diagnostic states. It checks SHA256 and marker contents,
verifies the fresh `checks/garage-restore/<uuid>/terraform.tfstate` backend,
pushes state with Terraform safety checks, compares resources and outputs,
and requires an unchanged plan.

Success prints `Restore verified: terraform_data.backend_check` and the private
workspace path. Downloaded copies are removed; the workspace remains. Failure
retains staging. For cleanup, set `RESTORE_DIRECTORY` to the printed module path
and run as its owner:

```bash
/usr/local/bin/terraform -chdir="$RESTORE_DIRECTORY" destroy
```

Approve only marker deletion. Preserve needed files before removing that
staging directory; the empty diagnostic state object remains in Garage.
Runner-owned workspaces require sudo as `runner-svc`, preserving only the two
Garage credential variables. This diagnostic proves recovery of the marker;
production recovery needs matching configuration/providers and a reviewed
destination backend.

## Verify rejection of overwrite and deletion

With R2 credentials loaded:

```bash
./scripts/check-r2-retention.sh
```

The unprotected `checks/retention/` control must allow overwrite and deletion.
The `backups/checks/retention/` probe must reject both and keep original bytes.
Only HTTP 403/409 with `ObjectLockedByBucketPolicy` proves enforcement.

Success prints `Retention verified: overwrite and deletion rejected by Bucket Lock.`
and removes the control and staging. The protected tiny probe remains for at
least 90 days; do not weaken the rule to delete it. Failure prints both keys
and retains files for inspection. In bucket settings, verify the enabled
90-day `backups/` rule, disabled `r2.dev`, and absence of public custom domains.

## GitHub Actions workflows

A successful **Validate** push on `homelab/main` triggers production apply in
private [homelab-automation](https://github.com/bart-kochanowicz/homelab-automation).
It verifies the commit/backend, saves a plan, verifies a pre-apply snapshot,
applies, and attempts a post-apply snapshot. Manual UniFi dispatch selects
`terraform_root=unifi` and `operation=plan` or `apply`.

Private jobs run on Houston without sudo and use the shared wrapper.
Workflow concurrency serializes jobs; the host lock covers each Terraform
command. Avoid intervening manual changes, which invalidate a saved plan.
Dispatch, secrets and failure instructions belong in the private guide.

## Recovery

Preserve failed staging until the cause is understood and current state is
backed up. A pre-apply backup failure stops apply; a failed post-apply backup
does not undo it. Inspect state before retrying. Rebuild a lost host through
Ansible and recover matching state from verified snapshots. Do not
automatically overwrite state after a failed apply.

Removing backup storage requires preserving snapshots elsewhere, deliberately
changing lifecycle guards and lock rules, then emptying the bucket.

After manual operations:

```bash
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY
unset R2_ACCOUNT_ID R2_ACCESS_KEY_ID R2_SECRET_ACCESS_KEY
unset TF_VAR_cloudflare_api_token
unset RESTORE_OBJECT_KEY RESTORE_SHA256 RESTORE_DIRECTORY
```
