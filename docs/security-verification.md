# Security Verification Record

This record captures dated operational verification. Results describe the
configuration tested on each recorded date. Verify private application access
after configuring its LAN entry point, then append new live results.

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

## October 4, 2026 — UniFi PR 01 read-only baseline

Scope: documentation and inventory; no live configuration changes, backup
execution, Terraform state operations or workload restarts.

| Check | Result | Evidence |
| --- | --- | --- |
| UniFi inventory | Partial | Authenticated UI: UCG-Fiber 5.1.33, Network 10.6.106, two switches and U7 Lite Online; current LAN 192.168.1.0/24, Allow All, mDNS Auto. |
| Physical paths | Partial | Gateway port 1 → five-port switch; its port 3 → eight-port switch; gateway port 4 → AP. Complete native/tagged profiles and labels pending. |
| Houston | Passed for read-only host checks | SSH: 192.168.1.165/24 via 192.168.1.1; Terraform 1.16.4, ext4 mount, Garage/runner active and loopback-only S3 listener. No backend recovery test performed. |
| Existing Kubernetes endpoint | Unresolved | Configured 192.168.100.86:6443 timed out; current cluster health and node roles unknown. |
| Operator-reported candidate node | Unresolved | 192.168.1.217 on eight-port switch port 7; Talos 50000 and Kubernetes 6443 refused connections. Port 8 client has no IPv4 reported in UniFi. |
| Route/CIDR conflicts | Pending | Legacy LAN and Houston routes checked; employer VPN, gateway routes and live cluster CIDRs not verified. |
| Controller TLS/API, wired recovery and backups | Pending | Browser access is available; trusted Houston API access and current UniFi/etcd/PVC recovery evidence remain required. June results are historical. |

See [network-inventory.md](../infra/unifi/docs/network-inventory.md) for remaining
gates. [PR 01 (#54)](https://github.com/bart-kochanowicz/homelab/pull/54) is a
draft, with no merged/deployed commit. Local checks passed for 22 file links,
Markdown whitespace/final newlines and staged diff whitespace. Full local
validation stopped on missing `shellcheck`;
[GitHub Validate](https://github.com/bart-kochanowicz/homelab/actions/runs/37227659249)
was pending when this entry was written. Verify the latest PR head's required
check before merge. Do not advance to PR 02 until its live gates pass.

## Rehearsal Procedure

For each quarterly tabletop:

1. Record the date, participants, and current Git commit.
2. Follow the relevant runbook procedure without executing destructive steps.
3. Confirm credentials, tools, backups, patches, and out-of-band access exist.
4. Record gaps and open a focused remediation issue or pull request.
5. Replace the pending entry above with the rehearsal date only after completion.
