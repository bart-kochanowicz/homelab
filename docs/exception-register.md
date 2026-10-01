# Security Exception Register

| Component | Exception | Reason | Compensating control | Review |
| --- | --- | --- | --- | --- |
| Home Assistant | `hostNetwork`, root, writable root filesystem, privileged PSS enforcement | LAN discovery protocols require host networking; the upstream image currently runs as root | Cloudflare Access, enforced Cilium host firewall, baseline audit/warn, dropped capabilities, seccomp | Quarterly |
| Crafty Controller | Root, writable root filesystem, privilege escalation, and image-default capabilities | The upstream wrapper uses `sudo` to switch to its runtime user; managed Minecraft files require the current ownership model | Cloudflare Access for UI, dedicated ServiceAccount without token, RuntimeDefault seccomp, fixed image digest, explicit NodePort policy | Quarterly and when the image supports direct non-root startup |
| Crafty TLS | Cloudflared `no_tls_verify` | Crafty currently serves a self-signed certificate without the homelab CA | Cloudflare Access and namespace policy; replace with trusted internal certificate | Monthly |
| local-path-provisioner | Privileged namespace/helper access | Host-path volume creation requires node filesystem access | Exact RBAC verbs, pinned images, retained volumes, mode `0770`, restricted ownership | Quarterly |
| Monitoring | Privileged PSS namespace | Node exporters and cluster monitoring need host-level access | Dedicated namespace, explicit ArgoCD project allowlist, no public ingress | Quarterly |

## Trivy exception review — 2026-10-01

The 17 existing path-scoped rules in `.trivyignore.yaml` expired on
2026-09-30. Their check IDs, file scopes, and reasons are retained after
reviewing the current source and rendered manifests. Their next expiry is
2026-12-31, following the quarterly review cadence in the security runbook.

| Scope | Reviewed configuration | Reason retained |
| --- | --- | --- |
| Home Assistant | Digest-pinned image `2026.6.3`, host networking, dropped capabilities, no API token mount | LAN discovery still uses host networking; retain the existing writable-root compatibility exception for this image. |
| Crafty Controller | Digest-pinned image `4.10.4`, upstream wrapper, persistent data mounts, no API token mount | Retain the existing writable-root compatibility exception for the pinned image and wrapper. |
| ArgoCD ConfigMap | `$dex.github.clientSecret` reference | This is a reference to a Kubernetes Secret, not a plaintext credential. |
| cert-manager and Sealed Secrets | Charts `v1.20.2` and `2.17.7`, rendered controller RBAC and webhook resources | Controllers still need Secret access; cert-manager still installs its webhook and discovers networking resources. |
| Cilium | Chart `1.19.3`, Talos capabilities, host networking, mounts, ports, and controller RBAC | Retain the existing node-networking exceptions. ConfigMap matches concern policy-secret setting names and flags, not secret values. |
| Monitoring | Chart `79.4.1`, rendered node-exporter access and Prometheus Operator RBAC | Retain the existing host visibility, runtime-context, filesystem, discovery, and CRD-access exceptions for these pinned components. |

This review covers repository configuration and scanner output. It does not
claim a new runtime compatibility test for the application images or charts.
Renewals must retain narrow file scopes and be reviewed again before expiry.
