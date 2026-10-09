# Terraform

| Root | Manages | Garage state key |
| --- | --- | --- |
| [cloudflare](cloudflare/) | Private R2 state backups | `prod/homelab/terraform.tfstate` |
| [unifi](unifi/) | UniFi LANs, Wi-Fi and switch ports | `prod/unifi/terraform.tfstate` |

Deployable roots live in `terraform/<name>/`; reusable modules in `modules/<name>/`.
UniFi modules separate networks, port profiles, devices and Wi-Fi; Cloudflare uses R2.
Use the Terraform version in `aqua.yaml` and committed provider locks.

## Plan and apply

After successful main validation, the [Terraform workflow](https://github.com/bart-kochanowicz/homelab/actions/workflows/terraform-dispatch.yaml)
creates private plans on Houston. Review the linked logs, then select
**Review deployments → Approve and deploy** to apply those saved plans.
Manual runs select `all`, `cloudflare` or `unifi`; IDs are passed automatically.
Changed source/state or expired plans require a new plan and approval.
Credentials and runner configuration live in [homelab-automation](https://github.com/bart-kochanowicz/homelab-automation#github-configuration).

- [Local plans on macOS](LOCAL_PLAN.md)
- [Backups, diagnostics and recovery](R2_BACKUP.md)
- Validation without infrastructure access: `make validate` from the repository root.

## Backend

Garage uses `terraform-state` at `http://127.0.0.1:3900` on Houston, with shared
settings in [garage.s3.tfbackend](garage.s3.tfbackend). `init` needs this file via
`-backend-config`; `.tfvars` supplies provider/resource inputs, not backend settings.

Garage has no native S3 locking. Houston's `/usr/local/bin/terraform` holds the
[shared host lock](../infra/ansible/README.md#terraform-and-locking); local plans
hold it over SSH. Never delete the lock file. Keep credentials outside backend
configuration and Git; state and saved plans can contain secrets.
