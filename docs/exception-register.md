# Security Exception Register

| Component | Exception | Reason | Compensating control | Review |
| --- | --- | --- | --- | --- |
| Home Assistant | `hostNetwork`, root, writable root filesystem, privileged PSS enforcement | LAN discovery protocols require host networking; the upstream image currently runs as root | Cloudflare Access, staged Cilium host firewall, baseline audit/warn, dropped capabilities, seccomp | Quarterly |
| Crafty Controller | Root and writable root filesystem | Upstream image and managed Minecraft files require current ownership model | Cloudflare Access for UI, dedicated ServiceAccount without token, dropped capabilities, seccomp, explicit NodePort policy | Quarterly |
| Crafty TLS | Cloudflared `no_tls_verify` | Crafty currently serves a self-signed certificate without the homelab CA | Cloudflare Access and namespace policy; replace with trusted internal certificate | Monthly |
| local-path-provisioner | Privileged namespace/helper access | Host-path volume creation requires node filesystem access | Exact RBAC verbs, pinned images, retained volumes, mode `0770`, restricted ownership | Quarterly |
| Monitoring | Privileged PSS namespace | Node exporters and cluster monitoring need host-level access | Dedicated namespace, explicit ArgoCD project allowlist, no public ingress | Quarterly |
| ArgoCD local admin | Temporarily enabled | SSO credentials and denial tests require external OAuth setup | Cloudflare Access; disable in a separate commit immediately after SSO verification | Before next release |
