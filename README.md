# Homelab

Kubernetes homelab infrastructure managed with Talos, Terraform, ArgoCD, and
Kustomize. The repository is public, so all Kubernetes secrets are committed
only as SealedSecrets and local credentials are ignored.

## Hardware

- Lenovo ThinkCentre m720q i3-8100T/8GB/256GB
- Lenovo ThinkCentre m920q i5-8500T/32GB/512GB
- Dell Wyse 3040 (`houston-01`) for Terraform infrastructure management;
  see [its Ansible setup guide](infra/ansible/README.md).

## Software Requirements

- Kubernetes v1.34
- Talos Linux
- kubectl configured to access your cluster
- Helm, Terraform, Ansible, restic, and the tools in `aqua.yaml`

## Hosted Apps

- Home Assistant is deployed in-cluster and exposed through Cloudflare Tunnel.
- Crafty Controller is deployed in-cluster and exposed through Cloudflare Tunnel.
- n8n is deployed in-cluster and exposed through Cloudflare Tunnel with a protected editor at `n8n.thecavespace.com` and public webhooks at `n8n-webhook.thecavespace.com`.

Minecraft TCP `30000` remains publicly reachable through its NodePort. Home
Assistant retains host networking for LAN discovery.

## Bootstrap

```bash
make validate
make -C system setup-from-scratch
```

The `system/Makefile` installs Ansible on the machine running `make`.
`system/bootstrap.yaml` also runs there and uses that machine's Kubernetes
access to bootstrap ArgoCD.

Bootstrap order is Talos, Cilium, ArgoCD, then ArgoCD-managed platform and
applications. Cilium is deliberately installed outside ArgoCD so the network
does not depend on GitOps for recovery.

## Terraform state backups

Garage is Houston's primary Terraform backend. The existing Cloudflare
Terraform module also provisions a private R2 bucket with 90-day protection
for off-site snapshots. See [the R2 setup guide](terraform/R2_BACKUP.md).
Snapshot upload and restore verification are the next implementation steps.

## Security Operations

See [docs/security-runbook.md](docs/security-runbook.md) for:

- GitHub SSO activation and local-admin recovery
- Internal CA and secret rotation
- encrypted PVC backup and restore
- Cilium migration and Flannel rollback
- network-policy and host-firewall enforcement
- retained local-path PV cleanup
- maintenance cadence and recovery rehearsals

Documented compatibility exceptions are tracked in
[docs/exception-register.md](docs/exception-register.md).
Completed checks and pending tabletop exercises are tracked in
[docs/security-verification.md](docs/security-verification.md).

## Network Infrastructure

The UniFi gateway WAN configuration, LEOX ONT management-access restoration
script, smoke tests, and recovery checklist are documented in
[infra/unifi/README.md](infra/unifi/README.md). Device backups, GPON identities,
and WAN credentials are intentionally excluded from this public repository.
