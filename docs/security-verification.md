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
| Existing Kubernetes endpoint / control plane | Initially unreachable; recovered separately below | Operator console confirms control plane 192.168.100.86/24; initial requests from the current LAN timed out. |
| Worker identity | Operator-confirmed; API unresolved | Operator's console identifies worker 192.168.1.217/24; UniFi maps that IP to eight-port switch port 7. Talos 50000 refused connections. Direct-cable recovery later identifies port 8 as the control plane. |
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

## October 4, 2026 — Separately authorized direct-cable API recovery

The operator connected Ethernet directly to the control plane. No UniFi/WAN,
node address, disk, bootstrap or workload configuration changes were made.
A temporary Talos NTP override was applied and then removed without reboot;
configuration values match the private pre-recovery backup.

| Check | Result | Evidence |
| --- | --- | --- |
| Direct operator path | Passed; temporary | Workstation en8 alias 192.168.100.250/24 reaches control plane 192.168.100.86; earlier /32 alias plus manual host route failed. Cable/alias remain for recovery; /24 temporarily intercepts workstation ONT-space traffic. |
| Control-plane identity | Passed | Authenticated Talos v1.11.1; direct ARP matches private mapping for eight-port switch port 8. |
| Startup cause | Confirmed | etcd/kubelet/trustd waited for time sync; Cloudflare NTP DNS lookup failed with the legacy gateway configuration. |
| Time recovery | Passed; temporary override reverted | Direct-link relay forwarded synchronized Cloudflare NTP replies, restricted to control-plane source; TimeStatus became synchronized and services started. Original time configuration restored; no remaining relay dependency in machine configuration. Permanent DNS/NTP connectivity remains unresolved. |
| Kubernetes API | Passed on direct cable | Existing kubeconfig and TLS verification; all `/readyz?verbose` checks pass, including etcd; `/readyz` still returns `ok` after NTP rollback. |
| Etcd snapshot | Local backup verified; recovery gate partial | 24,985,632 bytes, revision 35,756,184, 921 keys; SHA-256 receipt and local copy verified. Stored with private machine config under ignored owner-only `.backups/talos-recovery-2026-10-04/`. Independent off-workstation copy and restore rehearsal pending. |
| Kubernetes ranges | Passed for cluster collision checks | API confirms node pod CIDRs 10.244.1.0/24 and 10.244.2.0/24 and ServiceCIDR 10.96.0.0/12; no overlap with proposed LAN/VPN ranges. Other route/reservation checks remain pending. |
| Worker / applications | Unresolved; API records stale | Worker stored InternalIP 192.168.100.56, last Ready heartbeat August 4; operator console reports 192.168.1.217. Stored Running phases do not establish current health. |
| Storage placement / PVC backups | Partial | All six Bound local-path PVs, including HA, have affinity to the worker; live data unverified. Backup-success Lease last renewed June 14; no fresh PVC backup executed. |

Do not reboot before permanent network/DNS/NTP recovery. Stop the temporary
relay after rollback; retain the direct cable/alias until a verified replacement
operator path exists. The [runbook](../infra/unifi/docs/network-runbook.md#direct-cable-talos-recovery)
records alias cleanup. PR 01 remains draft and PR 02 must not begin yet.
