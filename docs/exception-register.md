# Security Exception Register

| Component | Exception | Reason | Compensating control | Review |
| --- | --- | --- | --- | --- |
| Home Assistant | `hostNetwork`, root, writable root filesystem, privileged PSS enforcement | LAN discovery protocols require host networking; the upstream image currently runs as root | Cloudflare Access, staged Cilium host firewall, baseline audit/warn, dropped capabilities, seccomp | Quarterly |
| Crafty Controller | Root, writable root filesystem, privilege escalation, and image-default capabilities | The upstream wrapper uses `sudo` to switch to its runtime user; managed Minecraft files require the current ownership model | Cloudflare Access for UI, dedicated ServiceAccount without token, RuntimeDefault seccomp, fixed image digest, explicit NodePort policy | Quarterly and when the image supports direct non-root startup |
| Crafty TLS | Cloudflared `no_tls_verify` | Crafty currently serves a self-signed certificate without the homelab CA | Cloudflare Access and namespace policy; replace with trusted internal certificate | Monthly |
| local-path-provisioner | Privileged namespace/helper access | Host-path volume creation requires node filesystem access | Exact RBAC verbs, pinned images, retained volumes, mode `0770`, restricted ownership | Quarterly |
| Monitoring | Privileged PSS namespace | Node exporters and cluster monitoring need host-level access | Dedicated namespace, explicit ArgoCD project allowlist, no public ingress | Quarterly |
