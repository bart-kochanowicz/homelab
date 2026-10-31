# Platform operations

## Network and access

Cilium handles Kubernetes Services, pod policies and the Talos host firewall.
Envoy Gateway terminates HTTPS on two private gateways. MetalLB allocates and
announces their virtual IPs on the Servers VLAN:

| Gateway | VIP | Access |
| --- | --- | --- |
| Home | `10.0.70.200` | Home Assistant from Home, Admin and WireGuard |
| Admin | `10.0.70.201` | Administrative panels and webhooks from Admin and WireGuard |

Houston (`10.0.70.10`) may reach only Crafty's `/api/v2/servers` API and its
subpaths through Admin. Envoy checks source IP, hostname and path together;
API authentication remains required. Verify authorization before widening
Service or Cilium source ranges. SecurityPolicy resources belong to the platform.
Both gateways use the TCP peer address for client IP detection; forwarded
headers from clients are not trusted for access decisions.

UniFi provides private DNS and routes traffic between VLANs. Talos uses
`10.0.70.1` as upstream DNS so CoreDNS can resolve these records too.
`talos/patches/dns.yaml` is a JSON Patch: strategic merge appends resolvers
instead of replacing the list.

| Service | Address |
| --- | --- |
| Home Assistant | `https://ha.thecavespace.net` |
| Crafty | `https://crafty-controller.thecavespace.net` |
| ArgoCD | `https://argocd.thecavespace.net` |
| n8n editor | `https://n8n.thecavespace.net` |
| n8n webhooks | `https://n8n-webhook.thecavespace.net/` |
| Grafana | `https://grafana.thecavespace.net` |
| Minecraft Java | `atm.mc.thecavespace.net` |

Minecraft uses private A/SRV records pointing to the worker on TCP `30000`.
Home, Admin and WireGuard clients can connect. There is no public DNS record or
WAN port forwarding. The NodePort uses `externalTrafficPolicy: Local`; only the
node running Crafty accepts game connections.

HTTPS listeners live in [system/gateways](../system/gateways/); routes live with
their applications. Envoy proxy egress and backend ingress must both allow the
backend port. Prometheus can scrape ArgoCD on `8083` and Grafana on `3000`.

Home Assistant uses host networking. Namespace policies do not isolate it;
Cilium host rules allow n8n and the Home proxy to reach TCP `8123`. Those rules
apply to every process listening on that node port. Host egress is unrestricted.

```bash
kubectl get gateways -A
kubectl -n private-home get service envoy-private-home
kubectl -n private-admin get service envoy-private-admin
```

For access problems, check UniFi DNS, router rules, Gateway/HTTPRoute conditions
and Cilium verdicts, in that order. Use fresh connections when checking policy
changes. Host `PolicyAuditMode` logs verdicts without enforcing drops and resets
when the Cilium agent restarts. Finish the policy review before restarting agents.

## Bootstrap and platform changes

Talos configuration uses the patches listed in the [root README](../README.md#bootstrap).
Cilium is bootstrap-managed so recovery does not depend on ArgoCD:

```bash
make -C system bootstrap-cilium
cilium status --wait
make -C system bootstrap
```

Cilium replaces kube-proxy and reaches the API through KubePrism on
`localhost:7445`. Talos has `cluster.proxy.disabled: true`. Keep
`bpf.hostLegacyRouting: true` while CoreDNS uses Talos host DNS. Returning to
kube-proxy requires restoring its Talos configuration and Service handling
before disabling Cilium replacement; a Helm rollback alone is insufficient.

After namespaces and cert-manager are available, sync the gateway components in
dependency order:

`gateway-api-crds` → `envoy-gateway-crds` → `metallb-crds` →
`network-policies` → `metallb` → `metallb-config` → `envoy-gateway` → `gateways`.

CRD Applications own their definitions separately from controller charts.
Gateway API CRDs and frontend certificates are protected from pruning and deletion.
Frontend certificates must be Ready before `gateways` is synced.
`network-policies`, `cert-manager-acme` and the gateway components require manual sync.
Changes in `system/argocd/` need bootstrap or an `argocd-bootstrap` sync.

MetalLB is the only VIP allocator and announcer; Cilium L2 announcements and
default LB IPAM are disabled. VIP requests use EnvoyProxy Service annotations.
Gateway `spec.addresses` creates Service `externalIPs` instead. Proxy Services
use `externalTrafficPolicy: Local` to preserve client addresses. MetalLB's node
selectors and `eno1` interface must match replacement nodes; speakers also
override the control-plane exclusion.

Admin wildcard listeners use HTTP/1.1. ArgoCD alone enables HTTP/2 with an exact
frontend certificate, preventing browser connection coalescing between panels.

## Certificates

Cert-manager issues application and gateway certificates through Let's Encrypt
using Cloudflare DNS-01. DNS challenges need public TXT/SOA resolution but no
inbound WAN access. Certificates use rotating ECDSA keys; renewal is scheduled
from the issued lifetime. Staging certificates are for tests and are not browser-trusted.
Public certificates expose their names in Certificate Transparency logs.

`cert-manager-acme` owns the issuers, gateway wildcard certificates and exact
ArgoCD frontend certificate. Application certificates live with their workloads;
the ArgoCD backend Certificate belongs to `cert-manager-ca`.

Envoy verifies backend hostnames against system CAs:

| Backend | HTTPS port | TLS Secret | TLS hostname | Certificate reload |
| --- | --- | --- | --- | --- |
| Home Assistant | `8123` | `home-assistant-backend-tls` | `ha.thecavespace.net` | Reloader restarts HA |
| Crafty | `8443` | `crafty-backend-tls` | `crafty-controller.thecavespace.net` | Native reload |
| ArgoCD | `8080` | `argocd-server-tls` | `argocd.thecavespace.net` | Native reload |
| n8n | `5678` | `n8n-backend-tls` | `n8n.thecavespace.net` | Reloader restarts n8n |
| Grafana | `3000` | `grafana-backend-tls` | `grafana-backend.thecavespace.net` | Native reload every 30 seconds |

HA and n8n renewals briefly interrupt those applications. Their Reloader instances
are namespace-scoped and require manual Application sync. ArgoCD ignores only
the reload hash environment variable.
Crafty shares its pod with the game; changing its mount restarts both. Mount TLS
Secrets as whole directories, without `subPath`, so file updates reach the process.

ArgoCD's native gRPC path uses the HTTP/2 `argocd-gateway-grpc` Service; UI,
Dex and gRPC-Web use the normal Service. Grafana's provisioning sidecars call
HTTPS through a loopback alias for its backend name. Prometheus uses that same
name for TLS verification. n8n's editor and webhook routes allow long requests
and WebSockets; direct n8n-to-HA calls use `https://ha-backend.thecavespace.net:8123`.

```bash
kubectl get certificates -A
cmctl status certificate private-home-wildcard -n private-home
cmctl status certificate grafana-backend -n monitoring
```

### Cloudflare token rotation

The `cert-manager/cloudflare-dns01-token` Secret needs DNS Edit and Zone Read for
`thecavespace.net`. The token is shared with Terraform/R2; rotate all consumers
together. Save its replacement without a trailing newline in the ignored file,
with mode `600`:

```bash
kubectl create secret generic cloudflare-dns01-token -n cert-manager \
  --from-file=api-token=.secrets/cloudflare-dns01-token --dry-run=client -o json |
  kubeseal --controller-name=sealed-secrets-controller \
    --controller-namespace=sealed-secrets --scope strict --format yaml \
    > system/cert-manager-acme/sealed-cloudflare-token.yaml
```

Commit the SealedSecret and sync `cert-manager-acme`. Cert-manager owns temporary
challenge records. An internal CA issuer also exists in `system/cert-manager-ca/`;
keep its offline key under `.secrets/` with a separate backup. CA rotation requires
distributing the replacement public trust before removing the old CA.

## ArgoCD login

GitHub SSO grants admin access to `bart-kochanowicz`; local admin is disabled.
OAuth uses `https://argocd.thecavespace.net` with callback
`https://argocd.thecavespace.net/api/dex/callback`. ArgoCD server pods must resolve
and reach that address for Dex discovery and signing keys.

```bash
export GITHUB_OAUTH_CLIENT_ID=...
export GITHUB_OAUTH_CLIENT_SECRET=...
./scripts/generate-argocd-sso-secret.sh
```

The resulting SealedSecret patches OAuth keys into `argocd-secret`, preserving
its other credentials. Commit it and sync ArgoCD. For SSO recovery, cluster-admin
access can temporarily enable `admin.enabled` in `argocd-cm` and restart the
server. Disable local admin again after recovery.

## Backups and storage

[Application backups](backups.md) use K8up and encrypted restic repositories on
Houston's SSD. HA, n8n and Grafana are copied daily without stopping applications;
the Crafty panel is copied weekly. Minecraft ATM10 8.3 has a separate weekly ZIP
backup on the worker's SATA disk; the game stops during that copy.
The backup guide lists sources, schedules, retention, credentials and restore
commands. Application backups have no configured offsite replication; R2 covers
Terraform state only. In-place recovery requires an explicit maintenance window
and protection from ArgoCD self-heal.

`system/backups/values.yaml` selects source claims explicitly. Keep these aligned
with application mounts and manually sync the `backups` ArgoCD Application after
changes.

Namespaces and PVCs have ArgoCD `Prune=false,Delete=false`; ApplicationSets
preserve their resources. Namespace deletion still cascades to workloads and PVCs.
Local-path volumes use `Retain`, directory mode `0770` and application-specific
ownership. Before removing retained data, verify a backup, the PV's node/path and
that no pod uses its PVC. For intentional cleanup, change only that PV's reclaim
policy to `Delete`, then delete its unused PVC; the provisioner removes its directory.

`local-path` reserves the worker's SATA at `/var/mnt/minecraft` for Crafty backups.
Its setup hook rejects other SATA claims; neither storage class provisions on other nodes.
The default class, `local-path-nvme`, stores worker volumes under `/var/mnt/nvme`, sharing Talos's
NVMe `/var` filesystem. PVC sizes do not enforce filesystem quotas; claims
bind when their first consumer is scheduled. The default class applies only
to claims without an explicit storage class; existing claims keep their disks.

Home Assistant uses `home-assistant-data-nvme` (32Gi); n8n uses `n8n-data-nvme`
(20Gi); Grafana uses `grafana-data-nvme` (10Gi). These claims use NVMe, and their
backups are stored on Houston.

Prometheus (50Gi) and Alertmanager (5Gi) also use NVMe. Their StatefulSet claims
are retained on scaling and deletion. Changing claim templates requires pausing
operator reconciliation and recreating the StatefulSets during a maintenance window.

Crafty stores servers, panel configuration, logs and imports in the shared
`crafty-data-nvme` claim (120Gi), mounted through separate subdirectories.
Only `/crafty/backups` uses the SATA-backed `crafty-data` claim. Both are local
volumes; a worker failure makes both unavailable.

The worker requires `talos/patches/worker-nvme.yaml`: Talos exposes `/var/mnt`
read-only to kubelet, so the NVMe directory needs its own writable bind mount.
For an existing worker, apply during a maintenance window; kubelet restarts:

```bash
talosctl -n 10.0.70.12 patch machineconfig \
  --patch @talos/patches/worker-nvme.yaml --mode=no-reboot
```

## Container image scanning

Run `make scan-images` to render application and platform manifests, including
ArgoCD's bootstrap chart, and scan their unique images with the pinned Trivy.
The inventory includes init containers, Helm hooks, custom-resource image fields
and Prometheus Operator's default config reloader. Scans use registry images for
`linux/amd64`; no cluster credentials or Docker daemon are needed.

Reports include HIGH/CRITICAL vulnerabilities with available fixes. A fixable
CRITICAL vulnerability or a scan error fails the command after all images have
been attempted. Inventory/rendering errors and an empty inventory also fail.
Results are in `.cache/image-scan/images.txt` and `reports/` beneath that directory.
The `Image Scan` workflow runs for relevant PRs, weekly and on manual dispatch;
its `image-scan` artifact retains the inventory and JSON/text reports for 14 days,
including failed scans. `make validate` keeps configuration and secret checks
separate from registry downloads. Talos-managed control-plane/CoreDNS images and
Minecraft JARs are outside this repository's rendered image inventory.

## Monitoring and credentials

Prometheus collects metrics; Grafana provides dashboards and the Alertmanager
view. [Email notifications](../system/monitoring/README.md) use Brevo for incident,
recovery and weekly delivery-check messages. K8up backup alerts cover failures,
missing successes, daily copies older than 36 hours and weekly Crafty panel
copies older than eight days. [Minecraft backup alerts](../system/logging/README.md)
use Crafty logs to detect failures and eight days without a successful copy.

Credentials and state belong in private directories with mode `700`, files with
mode `600`, and encrypted backups. Commit Kubernetes credentials as SealedSecrets.
Terraform state remains sensitive even when outputs are marked sensitive.
Compatibility exceptions are listed in [exception-register.md](exception-register.md).

Back up [SealedSecrets controller keys](sealed-secrets-recovery.md) independently
of the cluster. Without them, Git's encrypted manifests cannot recover credentials,
including the passwords needed to read application backups.

Branch protection requires PRs, resolved conversations, the current `validate`
check and linear history. Force pushes and branch deletion are blocked; required
review approvals are zero. Configuration command:

```bash
CONFIRM_BRANCH_PROTECTION=yes ./scripts/configure-branch-protection.sh
```
