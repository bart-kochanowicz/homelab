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

- Home Assistant is deployed in-cluster and supports LAN discovery.
- Crafty Controller is deployed in-cluster with a private administration UI.
- n8n is deployed in-cluster with private editor and webhook endpoints.

Application UIs are not published through a public tunnel. See the
[private access guide](docs/security-runbook.md#private-application-access).

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

## Terraform operations

Houston hosts the Garage backend, Terraform CLI, and a dedicated GitHub
Actions runner. The Cloudflare root configuration stores its state in Garage
at `prod/cloudflare/terraform.tfstate` and provisions a private R2 bucket with
90-day protection for snapshots. It manages only R2 storage and its settings.
Diagnostic check modules use separate state keys. See
[backend operations](terraform/BACKEND.md#verify-the-cloudflare-root).

The private [homelab-automation repository](https://github.com/bart-kochanowicz/homelab-automation)
runs production Terraform on Houston after a commit reaches `homelab/main`
and passes **Validate**. Each run verifies an R2 backup before applying its
saved plan and attempts another verified backup afterward. Public CI and
dispatch stay on GitHub-hosted runners.

See the [private automation guide](https://github.com/bart-kochanowicz/homelab-automation)
for trigger configuration and failure handling, and the
[R2 operations guide](terraform/R2_BACKUP.md) for manual backup and isolated
restore diagnostics.

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
