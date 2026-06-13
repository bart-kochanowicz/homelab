# Homelab

Kubernetes homelab infrastructure managed with Talos, Terraform, ArgoCD, and
Kustomize. The repository is public, so all Kubernetes secrets are committed
only as SealedSecrets and local credentials are ignored.

## Hardware

- Lenovo ThinkCentre m720q i3-8100T/8GB/256GB
- Lenovo ThinkCentre m920q i5-8500T/32GB/512GB

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

Bootstrap order is Talos, Cilium, ArgoCD, then ArgoCD-managed platform and
applications. Cilium is deliberately installed outside ArgoCD so the network
does not depend on GitOps for recovery.

## Security Operations

See [docs/security-runbook.md](docs/security-runbook.md) for:

- GitHub SSO activation and local-admin recovery
- Internal CA and secret rotation
- encrypted PVC backup and restore
- Cilium migration and Flannel rollback
- network-policy and host-firewall enforcement
- retained local-path PV cleanup

Documented compatibility exceptions are tracked in
[docs/exception-register.md](docs/exception-register.md).
