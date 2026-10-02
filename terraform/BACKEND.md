# Terraform state in Garage

## Desired configuration

Houston uses the S3-compatible Garage service at `http://127.0.0.1:3900`.
The bucket is `terraform-state` and its S3 region is `garage`.
`garage.s3.tfbackend` contains the shared, non-secret backend settings.
Each root module defines its own state key:

| Configuration | State key |
| --- | --- |
| Cloudflare root (`backend.tf`) | `prod/cloudflare/terraform.tfstate` |
| Isolated backend check (`examples/garage-backend`) | `checks/garage-backend/terraform.tfstate` |
| Restore rehearsal (`examples/garage-restore`, through the script) | `checks/garage-restore/<uuid>/terraform.tfstate` |

Credentials come from `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` in the
process environment. Do not put them in backend files or `-backend-config`
arguments: Terraform persists backend configuration in its local metadata.
The connection settings follow the [Terraform S3 backend documentation](https://developer.hashicorp.com/terraform/language/backend/s3).
Path-style addressing targets Garage directly; the `skip_*` settings avoid
AWS-only credential, account, metadata, and region lookups. Upload checksum
verification remains enabled.

Native S3 locking is disabled because Garage 2.4.1 [does not support the
conditional writes required for it](https://github.com/deuxfleurs-org/garage/blob/v2.4.1/doc/book/reference-manual/known-issues.md).
Run every command on Houston through `/usr/local/bin/terraform`, which holds
the shared host process lock. Direct access through the versioned binary or
another machine bypasses that lock. The host setup is described in
[the Ansible guide](../infra/ansible/README.md#step-9--serialize-terraform-commands-on-houston).

The tracked `backend.tf` configures the Cloudflare root with Terraform
`~> 1.16.4` and the production key shown above. Shared connection settings
remain in `garage.s3.tfbackend`. The [private workflows](R2_BACKUP.md#github-actions-workflows)
exercise a separate built-in check marker; they do not operate on the
Cloudflare root. Each new infrastructure root needs its own backend key and
matching backup and recovery procedure.

## Operator workspace on the SSD

The `terraform_cli` Ansible role creates `/srv/terraform/workspaces`, owned
by `capcom` with mode `0700`. Keep manual checkouts and Terraform metadata
there. The runner uses `/srv/terraform/runner/work` on the same SSD.

As `capcom` on Houston, clone this repository into that private workspace:

```bash
umask 077
cd /srv/terraform/workspaces
git clone https://github.com/bart-kochanowicz/homelab.git
cd homelab
```

Use an existing current checkout there if one is already present.

## Verify the Cloudflare root

Run production commands only on Houston through `/usr/local/bin/terraform`.
Provide the Garage `AWS_*` credentials as shown below. Keep Cloudflare inputs
in a private `terraform/variables.tfvars` file or process environment, using
`TF_VAR_<variable_name>` for Terraform variables. The repository ignores both
`*.tfvars` and `*.tfvars.json`; neither credentials nor state belong in Git.
The [input definitions](variables.tf) describe the required values. The
Cloudflare management token is separate from Garage and R2 S3 credentials.

From the repository root, initialize the shared backend settings and
validate the configuration:

```bash
/usr/local/bin/terraform -chdir=terraform init -input=false -backend-config=garage.s3.tfbackend
/usr/local/bin/terraform -chdir=terraform validate
/usr/local/bin/terraform -chdir=terraform state list
/usr/local/bin/terraform -chdir=terraform plan -input=false -var-file=variables.tfvars -detailed-exitcode
```

For an existing deployment, the initialized backend must contain its matching
state before planning. Verify the expected `module.cloudflare.*` addresses.
A missing or incorrect state can make Terraform propose recreating resources;
stop and check the backend rather than approving that plan. An unchanged
configuration should return exit code `0`; exit code `2` means changes and
`1` means an error. Review every proposed change before an apply.

Capture a verified production snapshot with the existing upload script and
separate R2 credentials:

```bash
./scripts/backup-terraform-state.sh terraform prod/cloudflare
```

Expect an object under `backups/prod/cloudflare/` and its SHA256 receipt.
The restore rehearsal script accepts only the built-in check marker. Recovery
of Cloudflare state requires its matching configuration and providers and a
reviewed destination backend. The private test workflows remain independent
of this production root.

## Verify the isolated backend

From the repository root on Houston, load the existing root-only Garage
credentials into the current shell without displaying them:

```bash
set +x
AWS_ACCESS_KEY_ID=$(sudo sed -n 's/^GARAGE_DEFAULT_ACCESS_KEY=//p' /srv/terraform/garage/s3-bootstrap.env)
AWS_SECRET_ACCESS_KEY=$(sudo sed -n 's/^GARAGE_DEFAULT_SECRET_KEY=//p' /srv/terraform/garage/s3-bootstrap.env)
: "${AWS_ACCESS_KEY_ID:?Garage access key was not loaded}"
: "${AWS_SECRET_ACCESS_KEY:?Garage secret key was not loaded}"
export AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY
unset AWS_SESSION_TOKEN AWS_SECURITY_TOKEN AWS_PROFILE AWS_DEFAULT_PROFILE
```

The [built-in `terraform_data` resource](https://developer.hashicorp.com/terraform/language/resources/terraform-data)
records a marker in state without provisioning infrastructure or downloading
an external provider. Initialize its backend, review the plan, and approve
only the creation of `terraform_data.backend_check`:

```bash
/usr/local/bin/terraform -chdir=terraform/examples/garage-backend init -backend-config=../../garage.s3.tfbackend
/usr/local/bin/terraform -chdir=terraform/examples/garage-backend validate
/usr/local/bin/terraform -chdir=terraform/examples/garage-backend plan
/usr/local/bin/terraform -chdir=terraform/examples/garage-backend apply
/usr/local/bin/terraform -chdir=terraform/examples/garage-backend state list
/usr/local/bin/terraform -chdir=terraform/examples/garage-backend output -raw backend_check
/usr/local/bin/terraform -chdir=terraform/examples/garage-backend plan -detailed-exitcode
```

Expect the marker `Garage backend read/write verified`, one state resource,
and exit code `0` from the final plan. These checks read the marker back from
Garage and confirm there is no remaining change. Every command uses the same
host lock. The check state key is separate from the Cloudflare reference key.

When finished, clear the credentials from the current shell:

```bash
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY
```

## Recovery and removal

If initialization fails, check the Garage service and bucket, then reload the
credentials and retry `init`. The credentials file must remain root-only.
If a command waits on the process lock, inspect `lslocks` and the active
Terraform commands; do not delete the lock file.

To remove the check resource, reload credentials and run:

```bash
/usr/local/bin/terraform -chdir=terraform/examples/garage-backend destroy
```

Approve only the removal of `terraform_data.backend_check`. This leaves an
empty check state in Garage; it does not remove the bucket or the Cloudflare
state. The private checkout can be removed once it contains no needed local
files. Removing the example from Git alone does not delete stored state.
