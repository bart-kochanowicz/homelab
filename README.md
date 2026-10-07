# Homelab

Infrastructure managed with Talos, Kubernetes, ArgoCD, Terraform, and Ansible.
Application endpoints are private; Minecraft is exposed on TCP `30000`.
Home Assistant uses host networking for LAN discovery.

## Configuration

| Path | Scope |
| --- | --- |
| `apps/` | Home Assistant, Crafty Controller, and n8n |
| `system/` | ArgoCD, Cilium, certificates, storage, monitoring, and network policies |
| `talos/patches/cilium.yaml` | Talos CNI configuration |
| `terraform/cloudflare/` | Cloudflare R2 backup storage; Garage state at `prod/homelab/terraform.tfstate` |
| `terraform/unifi/` | UniFi LAN configuration; Garage state at `prod/unifi/terraform.tfstate` |
| `infra/ansible/` | Houston: Garage, Terraform CLI, and private Actions runner |
| `infra/unifi/` | Network architecture and Netia/LEOX WAN configuration |

Terraform roots live in `terraform/<name>/`; reusable modules live in
`terraform/modules/<name>/`. Each root has its own backend and state.

Hardware: Lenovo ThinkCentre m720q (i3-8100T, 8 GB, 256 GB), m920q
(i5-8500T, 32 GB, 512 GB), and Dell Wyse 3040 (`houston-01`).

## Bootstrap and validation

Use Kubernetes v1.34, Talos, Helm, Terraform, Ansible, yamllint, and the tools in
`aqua.yaml`. Bootstrap runs locally using the current `KUBECONFIG`.

```bash
make validate
make -C system setup-from-scratch
```

Generate Talos configuration with the Cilium patch first. Bootstrap installs
Cilium before ArgoCD; ArgoCD manages the remaining platform and applications.
Cilium is managed separately so network recovery does not depend on GitOps.

## Operations

- [Private access, SSO, certificates, PVC backup/restore, and network policies](docs/security-runbook.md)
- [Security exceptions](docs/exception-register.md)
- [Houston configuration](infra/ansible/README.md)
- [Terraform backend](terraform/BACKEND.md) and [R2 backup/restore](terraform/R2_BACKUP.md)
- [UniFi Terraform](terraform/unifi/README.md) and [network/WAN configuration](infra/unifi/README.md)

Production Terraform runs on Houston through the private
[homelab-automation repository](https://github.com/bart-kochanowicz/homelab-automation).
Public CI validates configuration and dispatches automation; each production
apply verifies an R2 backup before applying its saved plan and attempts another
verified backup afterward.

Commit Kubernetes secrets only as SealedSecrets. Credentials, device backups,
Terraform state, and generated Talos configuration stay outside Git.
