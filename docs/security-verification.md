# Security Verification Record

This record captures operational verification of the security remediation.
Update it after material architecture changes or scheduled rehearsals.

## June 14, 2026

| Control | Result | Evidence |
| --- | --- | --- |
| Repository validation | Passed | Local and GitHub `validate` checks passed, including Terraform, YAML, ShellCheck, Kustomize, Helm, kubeconform, kube-linter, Trivy, and gitleaks history. |
| ArgoCD identity | Passed | GitHub SSO works for `bart-kochanowicz`; a second GitHub identity has no permissions; local admin is disabled. |
| Origin trust | Passed | Cloudflared validates ArgoCD with the internal CA and reports no origin TLS errors. |
| PVC backup and restore | Passed | Crafty, Home Assistant, and n8n backups completed; all three restore tests reproduced data; the success Lease was updated. |
| Cilium migration | Passed | Two agents, Envoy, operator, and Hubble Relay are healthy; all cluster pods are Cilium-managed. |
| Application policies | Passed | Required application paths work and unauthorized cross-namespace traffic is denied. |
| Host firewall | Passed | Kubernetes and Talos management, Home Assistant discovery, Cloudflare routes, n8n webhooks, and public Minecraft work; direct LAN access to kubelet and node-exporter is denied. |
| GitOps state | Passed | All ArgoCD Applications are Synced and Healthy after enforcement. |
| Backup recovery rehearsal | Passed | Non-destructive restores were completed for every protected PVC. |
| ArgoCD local-admin recovery | Tabletop pending | Review enable, restart, login, and disable procedure without changing the live cluster. |
| Cilium rollback | Tabletop pending | Review Flannel patch, node order, out-of-band access, and backup availability without executing rollback. |

## Rehearsal Procedure

For each quarterly tabletop:

1. Record the date, participants, and current Git commit.
2. Follow the relevant runbook procedure without executing destructive steps.
3. Confirm credentials, tools, backups, patches, and out-of-band access exist.
4. Record gaps and open a focused remediation issue or pull request.
5. Replace the pending entry above with the rehearsal date only after completion.
