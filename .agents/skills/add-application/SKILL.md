---
name: add-application
description: Add, rename or remove a Kubernetes application under apps/, with its namespace, ArgoCD project entry, network policies, private hostname, gateway listener, backups, monitoring, tests and docs. Use when a new service is deployed to the cluster, an app gets a web UI or stateful data, or an app is retired.
---

# Kubernetes applications

The `apps-generator` ApplicationSet turns each `apps/<name>/` into an
Application deployed to namespace `<name>`. The app directory holds only kinds
the `applications` project whitelists (ConfigMap, PVC, Service, ServiceAccount,
Deployment, CronJob, SealedSecret, Certificate, HTTPRoute, BackendTLSPolicy).
Everything else lives in `system/` and reaches the cluster through a platform
Application, several of which sync only by hand.

Start by reading the closest existing app: `mosquitto` (LoadBalancer VIP, no
UI), `n8n` (UI, PVC, backups) or `webos-dev-mode` (CronJob only). Then run
`git grep -n '<closest-app>' -- ':!apps/<closest-app>'` to list its touchpoints;
the table below is the usual set.

| Need | Files |
| --- | --- |
| Always | `apps/<name>/kustomization.yaml` with the `app.kubernetes.io/managed-by: argocd` label; namespace in `system/app-namespaces/namespaces.yaml` (`Prune=false,Delete=false`, restricted Pod Security unless justified); destination in the `applications` project in `system/argocd/projects.yaml`; `KUSTOMIZE_DIRS` in `Makefile` |
| Network | `default-deny` plus least-privilege allow policies in `system/network-policies/` and its `kustomization.yaml`; DNS egress to `kube-dns`; namespace as a `platform` project destination, because `network-policies` deploys through it |
| Web UI | listener in `system/gateways/private-home.yaml` or `private-admin.yaml`; namespace in `system/envoy-gateway/values.yaml` watch list; app `Certificate`, `HTTPRoute`, `BackendTLSPolicy`; gateway egress and app ingress on the backend port; private DNS record in `terraform/unifi/dns.tf` and its tests |
| VIP | pool and advertisement in `system/metallb-config/`; UniFi firewall rules if other VLANs connect |
| Secrets | `sealed-secret.yaml` (use the `seal-secret` skill) and its path in `.gitleaks.toml` |
| Data | PVC with `Prune=false,Delete=false`; entry in `system/backups/values.yaml`; backup credentials SealedSecret in `system/backups/`; namespace as a `backups` project destination; restic user in `infra/ansible/roles/restic_server`; namespace lists in `system/monitoring/security-alerts.yaml`; row in `docs/backups.md` |
| Alerts | rules in `system/monitoring/security-alerts.yaml` with fixtures in `tests/monitoring-rules.test.yaml` |
| Image exceptions | configuration findings in `.trivyignore.yaml` or `.kube-linter.yaml`; CRITICAL image CVEs without an upstream fix in `.trivyignore-images.yaml` (purl-scoped, expiring); each recorded in `docs/exception-register.md` |

## Rules

- Hostnames are `<name>.thecavespace.net`, private only. Never add Cloudflare
  DNS or a tunnel route.
- Pin images by tag and digest (`image: repo:1.2.3@sha256:...`); Renovate
  updates them.
- Run as non-root with `RuntimeDefault` seccomp, no privilege escalation,
  dropped capabilities and `automountServiceAccountToken: false` unless the
  app needs the API.
- Use `strategy: Recreate` for single-replica apps with a ReadWriteOnce PVC.

## Steps

1. If the app adds or changes a guarantee in `openspec/specs/`, start with the
   `openspec-propose` skill.
2. Write the app directory and every touchpoint the app needs from the table.
3. Add `tests/networking/test_<name>.py` on `GatewayTestCase` from
   `tests/networking/support.py`. Assert the pod security context, the pinned
   image, the network policy peers and ports, and the route or VIP.
4. Document the endpoint in `docs/security-runbook.md` and the app in the
   README layout table.
5. Run `make validate`. Use the `verifier` subagent for focused checks first.

## Deploy

After merge, ArgoCD creates the Application. Tell the user which manual steps
remain, in order: confirm the automated `app-namespaces` and `argocd-bootstrap`
syncs applied the namespace and project changes, sync `network-policies`, then `metallb-config`,
`envoy-gateway` and `gateways` for listener or VIP changes, and `backups`
for backup changes. UniFi DNS and firewall changes need a reviewed Terraform
plan; Houston's restic user needs the Ansible playbook.

## Remove

Delete the app directory and its touchpoints. ArgoCD keeps the namespace and
PVCs because of their sync options; deleting them is destructive cleanup and
needs the user's explicit confirmation after a final backup.
