# State backups and recovery

Garage is primary; private R2 bucket `houston-terraform-state-backups` stores
verified snapshots. Bucket Lock protects `backups/` from overwrite/deletion for
90 days; objects remain afterward. Bucket and lock have `prevent_destroy`.
Keep resource blocks and lock rules; preserve snapshots elsewhere before removal.
The provider does not refresh `r2.dev`: verify it is disabled and no public
custom domains exist. Snapshots contain secrets; retain each receipt's key and SHA256.

Actions verifies backups before and after apply. A failed pre-backup stops apply;
a failed post-backup does not undo it. See [plan and apply](README.md#plan-and-apply).

## Credentials

Manual commands below run in **Bash on Houston**, from a private repository checkout
under `/srv/terraform/workspaces`. Production jobs use [Actions secrets](https://github.com/bart-kochanowicz/homelab-automation#github-configuration).
Load Garage and bucket-scoped R2 **Object Read & Write** credentials:

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

R2 S3 keys are separate from the Cloudflare management token used to provision
storage (**Workers R2 Storage Write**). Store credentials in a password manager.

## Production snapshot

With credentials loaded:

```bash
/usr/local/bin/terraform -chdir=terraform/cloudflare init -input=false -lockfile=readonly \
  -backend-config=../garage.s3.tfbackend && \
./scripts/backup-terraform-state.sh terraform/cloudflare prod/homelab
/usr/local/bin/terraform -chdir=terraform/unifi init -input=false -lockfile=readonly \
  -backend-config=../garage.s3.tfbackend && \
./scripts/backup-terraform-state.sh terraform/unifi prod/unifi
```

Success prints the unique R2 object key and SHA256 after byte-for-byte readback.
An ambiguous upload is not retried; it may have succeeded. Failure retains private
staging and prints its path. Keep it until the cause is understood.

## Isolated restore check

This creates only `terraform_data.backend_check`, never production resources.
With credentials loaded, review and approve only the diagnostic marker:

```bash
/usr/local/bin/terraform -chdir=terraform/examples/garage-backend init \
  -backend-config=../../garage.s3.tfbackend && \
/usr/local/bin/terraform -chdir=terraform/examples/garage-backend apply && \
./scripts/backup-terraform-state.sh terraform/examples/garage-backend checks/garage-backend

read -r -p 'R2 object key (backups/checks/garage-backend/...tfstate): ' RESTORE_OBJECT_KEY
read -r -p 'Matching receipt SHA256: ' RESTORE_SHA256
./scripts/check-terraform-state-restore.sh "$RESTORE_OBJECT_KEY" "$RESTORE_SHA256"
```

The key excludes `s3://houston-terraform-state-backups/`. The script rejects
production/empty snapshots, verifies the hash, restores to a fresh
`checks/garage-restore/<uuid>/terraform.tfstate`, compares resources/outputs and
requires an unchanged plan. Success prints the retained private workspace path;
failure retains staging. This checks the marker, not production recovery.

For cleanup, set `RESTORE_DIRECTORY` to that printed module path and run as its
owner. Review and approve only marker deletion; preserve needed files before
removing staging. Runner-owned workspaces require sudo as `runner-svc`, preserving
only the two Garage credential variables. Empty state objects remain in Garage.

```bash
/usr/local/bin/terraform -chdir="$RESTORE_DIRECTORY" destroy
/usr/local/bin/terraform -chdir=terraform/examples/garage-backend destroy
```

## Retention check

With R2 credentials loaded, run `./scripts/check-r2-retention.sh`. It must allow
control overwrite/deletion and reject both for the protected probe with
`ObjectLockedByBucketPolicy`. Success prints `Retention verified`; the protected
probe remains for at least 90 days. Failure retains keys/staging for inspection.
Do not weaken Bucket Lock to remove probes.

## Recovery

Back up current state and inspect failures before retrying; never automatically
overwrite state after failed apply. Rebuild a lost Houston through
[Ansible](../infra/ansible/README.md), then recover matching state from a verified
snapshot using the matching configuration/providers and a reviewed destination
backend. Production state replacement requires explicit confirmation.
Update Actions secrets if Garage keys change. Clear credentials after operations:

```bash
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY R2_ACCOUNT_ID R2_ACCESS_KEY_ID R2_SECRET_ACCESS_KEY
unset RESTORE_OBJECT_KEY RESTORE_SHA256 RESTORE_DIRECTORY
```
