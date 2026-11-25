---
name: platform-sync
description: Work out which ArgoCD syncs, bootstrap runs, Terraform plans or Ansible runs a merged change still needs, and in what order. Use after a change to system/, talos/, infra/ansible/ or terraform/ merges, when a deployment did not take effect, or before telling the user a change is live.
---

# Deploying platform changes

`apps/`, `system/argocd/` (through `argocd-bootstrap`) and most platform
Applications sync automatically from `main`.
Everything below waits for an operator. The agent lists the steps; the user
runs them or approves each command (the guard hook asks for cluster changes).

## Find what is manual

```bash
for f in system/argocd/*.yaml; do
  yq -r 'select(.kind == "Application") |
    .metadata.name + " " + ((.spec.syncPolicy.automated != null) | tostring)' "$f"
done | sort -k2
```

`false` means manual sync. Map changed paths to those Applications through
`spec.source.path` in `system/argocd/`.

| Changed path | Needs |
| --- | --- |
| `system/argocd/` | nothing: `argocd-bootstrap` syncs it automatically and prunes removed Applications; `make -C system bootstrap` only on a fresh cluster |
| `system/cilium/` | `make -C system bootstrap-cilium`, then `cilium status --wait` |
| `system/network-policies/` | manual `network-policies` sync; review drops first |
| Gateways, MetalLB, Envoy Gateway | sync in order: `gateway-api-crds` → `envoy-gateway-crds` → `metallb-crds` → `network-policies` → `metallb` → `metallb-config` → `envoy-gateway` → `gateways` |
| `system/backups/`, backup operator | manual `backup-crds`, `backup-operator`, `backups` syncs after storage and credentials are ready |
| `system/vault/`, reloaders, `cert-manager-acme` | manual sync of that Application |
| `talos/patches/` | regenerate and apply machine configs per `docs/security-runbook.md#bootstrap-and-platform-changes` |
| `infra/ansible/` | `ansible-playbook playbooks/houston.yml --ask-become-pass` from `infra/ansible/`, after a `--check --diff` run |
| `terraform/<root>/` | Actions plan, reviewed with the `terraform-plan-review` skill, then approval |

## Verify

Read-only checks the agent may run with the user's `KUBECONFIG` (context
`homelab-prod`; confirm it with `kubectl config current-context`):

```bash
kubectl -n argocd get applications
kubectl -n argocd get application <name> -o jsonpath='{.status.sync.status} {.status.health.status}{"\n"}'
kubectl get gateways -A
```

A change is live when its Applications are `Synced` and `Healthy` at the
merged revision. For access problems, check UniFi DNS, router rules,
Gateway/HTTPRoute conditions and Cilium verdicts, in that order.
