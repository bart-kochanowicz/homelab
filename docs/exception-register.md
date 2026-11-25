# Security exceptions

| Component | Exception | Reason | Controls | Review |
| --- | --- | --- | --- | --- |
| Home Assistant | Host networking, root, writable filesystem, privileged PSS | LAN discovery and upstream runtime | Private LAN, Cilium host firewall, baseline audit/warn, dropped capabilities, seccomp | Quarterly |
| Crafty Controller | Root, writable filesystem, privilege escalation, default capabilities | Wrapper uses `sudo`; Minecraft data ownership | Private UI, tokenless ServiceAccount, seccomp, pinned image, explicit NodePort policy | Quarterly and when direct non-root startup is supported |
| local-path-provisioner | Privileged namespace/helper | Node filesystem access | Scoped RBAC, pinned images, retained volumes, mode `0770`, workload ownership | Quarterly |
| Monitoring | Privileged PSS namespace | Host-level monitoring | Dedicated namespace, ArgoCD resource allowlist, private access | Quarterly |
| K8up | Namespaced pod execution (`KSV-0053`) | Streams prepared archives to restic | Pinned controller, tokenless preparation pods, read-only PVCs, isolated network; aggregated user roles and legacy cleanup hook removed | 2026-12-31 |
| Envoy Gateway | Secret reads, Service writes (`KSV-0041`, `KSV-0056`) | TLS and proxy management | Pinned images, namespace-scoped RBAC, manual sync; rendered controller chart only | 2026-12-31 |
| MetalLB | Host network, NET_RAW, own webhook CA writes, status-CRD verbs; secret-named envs contain references | ARP and controller operation | Pinned images, bounded pools/nodes, host firewall, regression guards; rendered chart only | 2026-12-31 |
| Crafty Controller image | Fixable CRITICAL CVEs in 4.11.1 (PyJWT, Pillow, AnyIO, kernel headers) | Newest upstream release still bundles them | Private panel (Admin, WireGuard), pinned digest; per-package entries in `.trivyignore-images.yaml` | 2026-12-31 |
| Home Assistant image | Fixable CRITICAL CVEs in 2026.11.3 (Authlib, OpenSSH client tools) | Newest upstream release still ships them | Private UI (Home, Admin, WireGuard), no SSH server, pinned digest; per-package entries | 2026-12-31 |
| DOODS2 person detector | Fixable CRITICAL CVEs in 1.3.3 (Python libraries, kernel headers) | No upstream release after 1.3.3 | Node loopback only, non-root, read-only root filesystem, no credentials; per-package entries | 2026-12-31 |
| webos-dev-mode image | Fixable CRITICAL CVEs in 0.0.1 (OpenSSL, Go standard library) | No upstream release after 0.0.1 | Non-root, read-only root filesystem, no ServiceAccount token; no egress policy yet; the OpenSSL CVE affects 32-bit systems only. Replacement and egress limits in [#237](https://github.com/bart-kochanowicz/homelab/issues/237) | 2026-12-31 |
| K8up image | Fixable CRITICAL CVE in v2.16.1 OpenSSH client tools | Newest upstream release; K8up does not use SSH | Restic over HTTPS to Houston, pinned digest; per-package entries | 2026-12-31 |
| Front-door camera MQTT | IoT-initiated connection to Servers | The battery camera pushes events; Home Assistant cannot poll a device that may sleep | One source address, one VIP, TCP `1883` only, stateful replies, per-user ACLs, no anonymous access, a matching Cilium pod policy and Service source ranges, Terraform tests that pin the rule | Quarterly |
