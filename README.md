# Homelab

Private services on a two-node Talos Kubernetes cluster. ArgoCD deploys the
applications; Cilium handles networking and firewall policies. Envoy Gateway and
MetalLB provide separate Home and Admin HTTPS entry points. Terraform manages
UniFi and Cloudflare; Ansible manages Houston, the Terraform host.

Home Assistant uses host networking for LAN discovery. Minecraft is available
only from Home, Admin and WireGuard, on TCP `30000`.

## Repository layout

| Path | Contents |
| --- | --- |
| `apps/` | Home Assistant, Crafty Controller and n8n |
| `system/` | ArgoCD, networking, certificates, storage and monitoring |
| `talos/patches/` | Talos networking and API configuration |
| `terraform/cloudflare/` | R2 backup storage and email DNS |
| `terraform/unifi/` | LANs, Wi-Fi, switch ports, DNS, firewall and VPN |
| `terraform/modules/` | Reusable Terraform modules |
| `infra/ansible/` | Houston's Garage storage, Terraform CLI and private Actions runner |
| `infra/unifi/` | Network layout and Netia/LEOX WAN configuration |

Hardware: ThinkCentre m720q (i3-8100T, 8 GB RAM, 256 GB SSD), m920q
(i5-8500T, 32 GB RAM, 512 GB SSD), and Dell Wyse 3040 (`houston-01`).

## Bootstrap

Install the tools in `aqua.yaml`, plus Talos, Ansible and yamllint. Commands use
the current `KUBECONFIG`. The Kubernetes API is `https://10.0.70.11:6443`.

Generate Talos configuration with `--config-patch @talos/patches/cilium.yaml`,
`--config-patch @talos/patches/network.yaml` and
`--config-patch-control-plane @talos/patches/service-accounts.yaml`.
Use `--config-patch-worker @talos/patches/worker-nvme.yaml` for the worker's
NVMe storage mount.
Apply `talos/patches/dns.yaml` as JSON Patch. Nodes use Servers VLAN 70; the API's
ServiceAccount issuer and audience are independent of node addresses.

```bash
make validate
make -C system setup-from-scratch
```

`make validate` checks configuration without deploying it. Bootstrap installs
Cilium before ArgoCD; Cilium stays bootstrap-managed for network recovery.

## Operations

- [Private access, certificates, SSO, storage and backups](docs/security-runbook.md)
- [Security exceptions](docs/exception-register.md)
- [Houston](infra/ansible/README.md)
- [Terraform plans, deployment and state backups](terraform/README.md)
- [UniFi configuration](terraform/unifi/README.md) and [network layout](infra/unifi/README.md)

Commit Kubernetes credentials as SealedSecrets. Plaintext credentials, device
backups, Terraform state and generated Talos configuration stay outside Git.
