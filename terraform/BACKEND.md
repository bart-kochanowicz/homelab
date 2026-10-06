# Terraform state in Garage

Houston stores state in the `terraform-state` bucket on Garage at
`http://127.0.0.1:3900`. Shared connection settings are in
[`garage.s3.tfbackend`](garage.s3.tfbackend); each root has its own key:

| Root | State key |
| --- | --- |
| Cloudflare (`terraform/`) | `prod/homelab/terraform.tfstate` |
| UniFi (`terraform/unifi/`) | `prod/unifi/terraform.tfstate` |
| Backend diagnostic (`examples/garage-backend`) | `checks/garage-backend/terraform.tfstate` |
| Restore diagnostic (`examples/garage-restore`) | `checks/garage-restore/<uuid>/terraform.tfstate` |

Run write operations on Houston through `/usr/local/bin/terraform`. Garage 2.4.1
[lacks native S3 locking](https://github.com/deuxfleurs-org/garage/blob/v2.4.1/doc/book/reference-manual/known-issues.md),
so the wrapper serializes commands with a shared host lock. See
[host configuration](../infra/ansible/README.md#terraform-and-locking).
Read-only [local UniFi plans](unifi/LOCAL_PLAN.md) hold this same lock over SSH.

Keep checkouts in `/srv/terraform/workspaces` (`0700 capcom:capcom`). Supply
Garage credentials through `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`
using [the credential instructions](R2_BACKUP.md#credentials). Backend files
and `-backend-config` arguments must contain no secrets: Terraform stores
them in local metadata.

## Verify the production root

Cloudflare inputs come from `TF_VAR_*` or a private `variables.tfvars` based
on [`variables.tfvars.example`](variables.tfvars.example). The management
token is separate from Garage and R2 S3 credentials.

From the repository root on Houston, with Garage credentials loaded:

```bash
set +x
export TF_VAR_cloudflare_account_id=f572e035612c37b4ae02d5f64e0f04e1
read -r -s -p 'Cloudflare management API token: ' TF_VAR_cloudflare_api_token
printf '\n'
export TF_VAR_cloudflare_api_token

/usr/local/bin/terraform -chdir=terraform init -input=false -backend-config=garage.s3.tfbackend
/usr/local/bin/terraform -chdir=terraform validate
/usr/local/bin/terraform -chdir=terraform state list
/usr/local/bin/terraform -chdir=terraform plan -input=false -detailed-exitcode
```

For file inputs, add `-var-file=variables.tfvars` to `plan`. An existing
deployment must have its matching `module.cloudflare.*` state; unexpected
recreation requires checking the backend. Plan exit codes are `0` for no
changes, `2` for changes, and `1` for an error. Production apply and backup
automation live in [the private workflows](R2_BACKUP.md#github-actions-workflows).

## Verify the isolated backend

The diagnostic uses a built-in `terraform_data.backend_check` marker without
external providers or infrastructure. With Garage credentials loaded:

```bash
/usr/local/bin/terraform -chdir=terraform/examples/garage-backend init -backend-config=../../garage.s3.tfbackend
/usr/local/bin/terraform -chdir=terraform/examples/garage-backend apply
/usr/local/bin/terraform -chdir=terraform/examples/garage-backend output -raw backend_check
/usr/local/bin/terraform -chdir=terraform/examples/garage-backend plan -detailed-exitcode
```

Review the plan and approve only the marker. Its output is
`Garage backend read/write verified`; the final plan must return `0`.
[Backup and restore diagnostics](R2_BACKUP.md#rehearse-an-isolated-restore)
use this same isolated state. Remove it when no longer needed:

```bash
/usr/local/bin/terraform -chdir=terraform/examples/garage-backend destroy
```

This leaves an empty diagnostic state object. If `init` fails, inspect the
Garage service, bucket, and credentials. If Terraform waits on the lock,
inspect `lslocks` and active processes; never delete the lock file.
