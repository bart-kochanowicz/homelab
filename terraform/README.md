# Terraform

| Root | Resources | Garage state key |
| --- | --- | --- |
| [cloudflare](cloudflare/) | Private R2 state backups and Brevo DNS | `prod/homelab/terraform.tfstate` |
| [unifi](unifi/) | LANs, Wi-Fi, ports, DNS, firewall and VPN | `prod/unifi/terraform.tfstate` |

Deployable roots live in `terraform/<name>/`; shared modules live in `modules/`.
Each root has its own state. Tool versions come from `aqua.yaml` and committed
provider lock files.

## Plan and apply

Successful `main` validation starts the
[Terraform workflow](https://github.com/bart-kochanowicz/homelab/actions/workflows/terraform-dispatch.yaml).
Houston creates plans in the private automation repository. Review the linked
plan logs, then use **Review deployments → Approve and deploy** to apply those
saved plans. Manual runs select `all`, `cloudflare` or `unifi`. Changed source,
changed state or an expired plan requires a new plan and approval.

The runner reads [private Actions credentials](https://github.com/bart-kochanowicz/homelab-automation#github-configuration).
Local plans use read-only Garage access; deployment runs through Actions.

- [Local plans on macOS](LOCAL_PLAN.md)
- [State backups and recovery](R2_BACKUP.md)
- `make validate` checks configuration without infrastructure access.

## Storage and DNS

Garage stores state in `terraform-state` on Houston at `http://127.0.0.1:3900`.
Initialization reads [garage.s3.tfbackend](garage.s3.tfbackend) through
`-backend-config`. Root `.tfvars` files supply provider inputs, not backend settings.
State and saved plans contain credentials and belong outside Git.

Garage has no native S3 locking. Houston's Terraform wrapper and local SSH
sessions hold the [shared host lock](../infra/ansible/README.md#terraform-and-locking).
Do not delete its lock file.

Cloudflare DNS contains Brevo verification, DKIM and DMARC records for email.
DKIM CNAMEs remain DNS-only. DMARC `p=none` collects reports without requesting
rejection of unauthenticated messages. Private service names are managed in UniFi.
