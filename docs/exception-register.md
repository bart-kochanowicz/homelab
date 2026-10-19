# Security exceptions

| Component | Exception | Reason | Controls | Review |
| --- | --- | --- | --- | --- |
| Home Assistant | Host networking, root, writable filesystem, privileged PSS | LAN discovery and upstream runtime | Private LAN, Cilium host firewall, baseline audit/warn, dropped capabilities, seccomp | Quarterly |
| Crafty Controller | Root, writable filesystem, privilege escalation, default capabilities | Wrapper uses `sudo`; Minecraft data ownership | Private UI, tokenless ServiceAccount, seccomp, pinned image, explicit NodePort policy | Quarterly and when direct non-root startup is supported |
| local-path-provisioner | Privileged namespace/helper | Node filesystem access | Scoped RBAC, pinned images, retained volumes, mode `0770`, workload ownership | Quarterly |
| Monitoring | Privileged PSS namespace | Host-level monitoring | Dedicated namespace, ArgoCD resource allowlist, private access | Quarterly |
| Envoy Gateway | Secret reads, Service writes (`KSV-0041`, `KSV-0056`) | TLS and proxy management | Pinned images, namespace-scoped RBAC, manual sync; rendered controller chart only | 2026-12-31 |
| MetalLB | Host network, NET_RAW, own webhook CA writes, status-CRD verbs; secret-named envs contain references | ARP and controller operation | Pinned images, bounded pools/nodes, host firewall, regression guards; rendered chart only | 2026-12-31 |
