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
| Existing Kubernetes endpoint / control plane | Unresolved connectivity | Operator's console confirms control plane 192.168.100.86/24. Configured Kubernetes request and authenticated Talos request timed out. Health and hostnames pending. |
| Worker identity | Operator-confirmed; API unresolved | Operator's console identifies worker 192.168.1.217/24; UniFi maps that IP to eight-port switch port 7. Talos 50000 refused connections. Port 8 client remains unidentified. |
| Operator-reported console gateways | Clarified | Control plane gateway 192.168.100.1; worker gateway 192.168.1.1. These are gateway fields, not duplicate node IPs. |
| Private configuration / address ranges | Partial | Original private configs: control plane eno1 192.168.100.86/24, wg0 10.0.0.1/24; configured pods 10.244.0.0/16 and services 10.96.0.0/12. No overlap with target ranges in these files; live CIDRs remain unverified. |
| Route/CIDR conflicts | Pending | Legacy LAN and Houston routes checked; employer VPN, gateway routes and live cluster CIDRs not verified. |
| Controller TLS/API, wired recovery and backups | Pending | Browser access is available; trusted Houston API access and current UniFi/etcd/PVC recovery evidence remain required. June results are historical. |
| Houston controller TLS | Unresolved | Read-only curl to https://192.168.1.1 returned certificate verification error 60 for a self-signed certificate. No insecure bypass or trust-store changes were made. |

See [network-inventory.md](../infra/unifi/docs/network-inventory.md) for remaining
gates. [PR 01 (#54)](https://github.com/bart-kochanowicz/homelab/pull/54) is a
draft, with no merged/deployed commit. Local checks passed for 22 file links,
Markdown whitespace/final newlines and staged diff whitespace. Full local
validation stopped on missing `shellcheck`;
[GitHub Validate](https://github.com/bart-kochanowicz/homelab/actions/runs/37227726402)
passed the full repository checks for `fdaf1c2`. Verify the latest PR head's
required check before merge. Do not advance to PR 02 until its live gates pass.

## Rehearsal Procedure

For each quarterly tabletop:

1. Record the date, participants, and current Git commit.
2. Follow the relevant runbook procedure without executing destructive steps.
3. Confirm credentials, tools, backups, patches, and out-of-band access exist.
4. Record gaps and open a focused remediation issue or pull request.
5. Replace the pending entry above with the rehearsal date only after completion.
