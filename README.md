# Homelab

Infrastructure managed with Talos, Kubernetes, ArgoCD, Terraform, and Ansible.
Application endpoints are private; Admin and Home can reach Minecraft on TCP `30000`.
Home Assistant uses host networking for LAN discovery.

## Configuration

| Path | Scope |
| --- | --- |
| `apps/` | Home Assistant, Crafty Controller, and n8n |
| `system/` | ArgoCD, Cilium, certificates, storage, monitoring, and network policies |
| `talos/patches/` | Talos CNI and API configuration |
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

Generate Talos configuration with `--config-patch @talos/patches/cilium.yaml`,
`--config-patch @talos/patches/network.yaml` and
`--config-patch-control-plane @talos/patches/service-accounts.yaml`.
The Kubernetes API is `https://10.0.70.11:6443`; kubelet addresses use Servers VLAN 70.
The API uses a stable ServiceAccount issuer and audience independent of node IPs.
Bootstrap installs Cilium before ArgoCD; ArgoCD manages the remaining platform
and applications.
Cilium is managed separately so network recovery does not depend on GitOps.

## Operations

- [Private access, SSO, certificates, PVC backup/restore, and network policies](docs/security-runbook.md)
- [Security exceptions](docs/exception-register.md)
- [Houston configuration](infra/ansible/README.md)
- [Terraform: plans, approval, backend and recovery](terraform/README.md)
- [UniFi Terraform](terraform/unifi/README.md) and [network/WAN configuration](infra/unifi/README.md)

Commit Kubernetes secrets only as SealedSecrets. Credentials, device backups,
Terraform state, and generated Talos configuration stay outside Git.
