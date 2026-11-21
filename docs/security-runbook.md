# Platform operations

## Inventory

The cluster has one control plane and one worker on Servers VLAN 70. Houston
runs Terraform, Garage state storage and encrypted backup repositories.

| Host | Kubernetes name | Address |
| --- | --- | --- |
| `control-plane-01` | `talos-p5e-e9e` | `10.0.70.11` |
| `worker-01` | `talos-2jn-7he` | `10.0.70.12` |
| `houston-01` | — | `10.0.70.10` |

Cluster hardware: ThinkCentre m720q (i3-8100T, 8 GB RAM, 256 GB SSD) and m920q
(i5-8500T, 32 GB RAM, 512 GB SSD). Houston is a Dell Wyse 3040.
The Kubernetes API is `https://10.0.70.11:6443`; the kubeconfig context is `homelab-prod`.

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
| Vault | `https://vault.thecavespace.net` |
| Minecraft Java | `atm.mc.thecavespace.net` |

Minecraft uses private A/SRV records pointing to the worker on TCP `30000`.
Home, Admin and WireGuard clients can connect. There is no public DNS record or
WAN port forwarding. The NodePort uses `externalTrafficPolicy: Local`; only the
node running Crafty accepts game connections.

Crafty's HTTPS readiness probe checks `/api/v2/crafty/check` on the panel port.
It controls panel routing only: the Minecraft Service publishes not-ready endpoints
so a panel failure does not remove the game's backend. No startup or liveness probe
restarts the shared container. Minecraft startup remains manual. Deployment changes
still restart the shared pod; apply them while the game is stopped.

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

### MQTT broker

Mosquitto ([apps/mosquitto](../apps/mosquitto/)) receives battery, power, button,
uptime and snapshot messages from the RH-PD10 front-door camera and serves Home
Assistant's MQTT integration. It is the only service in Servers that an IoT
device may reach.

| Item | Value |
| --- | --- |
| Address | `mqtt.thecavespace.net`, `10.0.70.202`, TCP `1883`; plain MQTT without TLS |
| Allocation | MetalLB pool `mosquitto`, bound to the `mosquitto` Service in its namespace |
| Allowed sources | Camera `10.0.50.190` and the Home Assistant worker `10.0.70.12`, in the Service source ranges, the Cilium pod policy and the router |
| Router | Terraform rule `camera-mqtt`: only `10.0.50.190` to the VIP on TCP `1883`, with stateful replies |
| Users | `home-assistant` reads and writes every topic; `front-door-camera` writes `doorview/front-door-camera/#` and its own `sensor`, `binary_sensor` and `event` discovery topics only |

Anonymous access is disabled. The password file is the SealedSecret
`mosquitto-secret` (key `passwd`) in `apps/mosquitto/sealed-secret.yaml`; the pod
stays in `CreateContainerConfigError` without it. To create or rotate it, generate
the file locally with `mosquitto_passwd` (`-c` for the first user; avoid `-b` outside
a throwaway shell) and seal a Secret with `stringData.passwd` through
[Sealed Secrets Web](../system/sealed-secrets-web/README.md). Keep the camera
password for the camera's own configuration; never commit it.

#### Motion snapshots

After motion the camera publishes a 1920 by 1080 JPEG (about 120 to 170 KB, up to about
250 KB at higher quality) to
`doorview/front-door-camera/snapshot`, which its ACL already allows. Home Assistant
declares a `mqtt` `image` entity for that topic in `apps/home-assistant/configmap.yaml`
and does not call the camera: Home Assistant opens no connection to IoT for this, so
the router needs no rule and the camera's web interface, which grants root to any
login, stays unreachable. The entity is declared by hand because the ACL permits no
`homeassistant/image/...` discovery topic; leave the ACL as it is.

The broker's `max_packet_size` is 524288 bytes (512 KiB), about twice the largest
expected picture. It is the only size limit set: `message_size_limit`,
`max_inflight_bytes` and `max_queued_bytes` default to unlimited, and the broker holds one
retained message per topic with persistence off, so the 64Mi pod limit is ample. A
larger packet is rejected and disconnects the camera, so raise the limit before the
camera sends bigger pictures. Home Assistant's MQTT client and `image` entity set no
size limit that matters at this size, and the phone's attachment limit for images is
far above it (about 10 MB, from third-party sources; Apple's table was not checked).
The broker reads its configuration at start: after syncing a change run
`kubectl -n mosquitto rollout restart deployment/mosquitto`; the camera reconnects and republishes.

The automation `front_door_motion_notification` reacts to `Motion` turning on. If the
image entity has not updated within 5 seconds before the motion, it waits up to 20
seconds for it, then sends a phone notification through the mobile app with the image
(or a text-only message when none arrives). It then holds a one-minute cooldown; motion
during the wait or cooldown starts no second run. The phone downloads the image from
Home Assistant through `/api/image_proxy/`, which requires its login. Tapping either
notification opens the [events dashboard](#events-dashboard).

A second automation, `front_door_snapshot_archive`, saves the picture that follows each
motion to `/config/media/front-door/YYYY-MM-DD_HH-MM-SS.jpg` on the Home Assistant PVC,
named by the time the image arrived in Home Assistant's configured time zone, using the
`image.snapshot` action; it needs no token or secret. It is independent of the
notification, so a failed write (full disk, permissions) is only logged under
**Settings > System > Logs** and never delays or suppresses the notification.

The camera publishes snapshots with the MQTT retain flag, so Home Assistant receives
the last picture again after every restart or broker reconnect, and the image entity
cannot tell it from a new one (Home Assistant exposes no retain flag to automations). The
archive therefore saves a picture only when `Motion` turned from `off` to `on` and the
image was updated within 5 seconds before or 20 seconds after it, the rule the
notification uses. A replay is preceded by `unavailable`/`unknown` and does not start
the automation, and the broker keeps no retained messages across its own restart.
Failure modes: a picture that arrives more than 20 seconds after motion, or without a
motion event, is not archived; a replay within that window after a real motion would
be saved again under its own, equally recent, name; two motions sharing one picture
rewrite one file.

The directory is a Home Assistant media folder (`media_dirs: front_door`), so the
pictures are in **Media > My media > front_door** and under `/media/front_door/` only
for a logged-in user. Never store them in `/config/www`: its `/local/` URL is served
without authentication. Every Home Assistant user, not only administrators, can open
the archive, and it is a record of who came to the door; keep access to Home Assistant
and its PVC limited accordingly. Defining `media_dirs` replaces the default `local`
folder, which this deployment does not mount. The directory must exist when Home
Assistant starts, otherwise the core configuration is invalid and Home Assistant starts
in recovery mode, so the deployment's init container creates it.

Snapshots older than 90 days are deleted by `front_door_snapshot_retention` at 04:15
and when Home Assistant starts, through the `front_door_snapshot_cleanup` shell
command; change `retention_days` there to change the retention. It runs `find` only in
`/config/media/front-door`, at depth one, on regular files named like the snapshots
(never symlinks or other names), so an empty or missing directory is not an error and
nothing outside the archive is touched. Files can live up to a day longer than the
retention. The archive adds about the size of each picture (150 KB at 1920 by 1080, up
to 250 KB) per motion, so it holds roughly 150 KB times motions per day times 90: 50
motions a day come to about 700 MB, far below the 32Gi volume. The age is the file's
modification time, which is when the picture was saved and matches the time in its name.

The archive is excluded from the K8up backup of `home-assistant-data-nvme`
(`excludePaths` in `system/backups/values.yaml`): backing it up would keep deleted
photos of the door in the restic repository for up to three months, the longest
monthly retention, so a photo could outlive the 90-day retention by that long. The
90 days therefore apply only to the live volume. Consequently a restored Home
Assistant starts with an empty archive. To clear it early, delete the files in
**Media** (the delete action) or run
`kubectl -n home-assistant exec deployment/home-assistant -- sh -c 'rm -f /config/media/front-door/*.jpg'`.
Deleting the directory itself needs a pod restart.

The automation notifies the `iphone_bart` mobile app (`notify.mobile_app_iphone_bart`);
a different or additional phone needs its own service name (Developer tools > Actions,
filter `mobile_app`). The entity ids are `binary_sensor.front_door_camera_motion` and
`image.front_door_camera_snapshot`; the image id follows from the entity name, so
confirm it in Developer tools > States after the first sync. `configuration.yaml` is
mounted with `subPath`, so after syncing run
`kubectl -n home-assistant rollout restart deployment/home-assistant`; the sync of a
change to the init container restarts the pod itself. Then check that Home Assistant
did not start in recovery mode and that **Developer tools > Actions** lists
`image.snapshot`, trigger a motion, and confirm a JPEG in **Media > front_door**
whose name matches your local time (the time zone is set in **Settings > System >
General**).

Roll out in this order, reviewing each step: apply the UniFi Terraform plan (DNS
record and `camera-mqtt`), then sync `app-namespaces`, the `applications` project
(`system/argocd`), `metallb-config` and the network policies, which are all manual.
The ApplicationSet then creates the `mosquitto` application. Add the Home Assistant
MQTT integration in the UI: broker `mqtt.thecavespace.net`, port `1883`, user
`home-assistant`.

```bash
kubectl -n mosquitto get pods,service
kubectl -n mosquitto logs deployment/mosquitto
```

An init container copies the password file and ACL into memory-backed storage owned by
the broker, because Mosquitto refuses the symlinks that Secret and ConfigMap volumes
use. Rotate a password by regenerating the file, resealing it, committing the result and running
`kubectl -n mosquitto rollout restart deployment/mosquitto`; then update the
camera's configuration. The broker keeps no persistence, so a restart drops
retained messages. The camera republishes its discovery and state when it
reconnects.

The password crosses the IoT VLAN unencrypted, so treat it as low-value and unique
to this broker. Verify two assumptions on first use, because they depend on the
live cluster: that Home Assistant, which uses host networking, can reach the VIP
from its worker, and that the camera's address survives to the pod under
`externalTrafficPolicy: Local` so that the pod policy matches it.

##### Events dashboard

Tapping the motion notification, or **Front door** in the sidebar, opens
`/front-door/events`: the archived snapshots as a list of events, newest first, grouped
by day, each with its time, its kind (today only **Motion**) and the picture. Tapping a
picture opens it full size; swipe or use the arrows to move between events. The
first page holds the 30 newest events and **Show older events** adds 30 more; the
drop-down lists every day in the archive with its event count and shows that day only.
The default dashboard stays in the UI; this one is declared in the repository.

- `apps/home-assistant/front-door/front-door.yaml` is the dashboard, registered under
  `lovelace.dashboards` in `configmap.yaml` (YAML mode, in the sidebar for every user,
  not only administrators) and mounted read-only at `/config/dashboards`. The dashboard
  URL needs a hyphen, so changing the `front-door` key changes the notification URL.
- `apps/home-assistant/front-door/front-door-events-card.js` is the card, about 360
  lines (a third of them CSS) written for this repository. It lists `media-source://media_source/front_door`
  through the `media_source/browse_media` WebSocket command. The time of an event is
  the time in the file name, which is Home Assistant's time zone, shown as written
  whatever the zone of the phone; it is when the picture arrived, not the motion
  itself. Each picture is resolved through `media_source/resolve_media` only when it is
  within about 400 px of the screen, which returns a signed
  `/media/front_door/...?authSig=` URL valid for 24 hours; **Refresh** signs them again.
  Without a login (or with a tampered signature) the same path returns 401.
- Home Assistant has no thumbnails for media files, so a tile is the full picture
  (100 to 250 KB). The first screen loads about a dozen of them and the rest load as
  you scroll, so a page costs a few megabytes on mobile data, not the whole archive.

The card is delivered through two ConfigMaps that Kustomize generates from those files.
Their names carry a content hash, so a change to the card or the dashboard rolls the pod
on sync. `/local` serves `/config/www` without authentication, so the card's directory
(`/config/www/front-door`, a read-only mount of a ConfigMap, not the PVC) holds only that
script, which contains no data and loads nothing from the internet; pictures never go
there and the dashboard file is not under it. `frontend.extra_module_url` loads the
script on every page. Home Assistant caches `/local` for 31 days, so the URL ends in
`?v=` plus the first 16 hex digits of the script's SHA-256, which a test checks:
after editing the card run
`sha256sum apps/home-assistant/front-door/front-door-events-card.js | cut -c1-16`
and put the result in `configuration.yaml`.

Why a card of our own: built-in cards cannot do this. `picture` and `picture-entity`
do not resolve `media-source://`, markdown templates cannot list files or sign URLs
(the `/media` URL needs a signature that only the WebSocket API gives, and an image
tag cannot send a bearer token), and the logbook shows no pictures. A sensor that
lists files (`command_line` or `folder`) would still leave the signature problem or
force the pictures into `/local`.

Community cards were read about, not run against this Home Assistant version:
`TarheelGrad1998/GalleryCard` parses the date from the file name, but its author
archived it in 2024 with no licence and it shows one picture with a strip of
thumbnails, not a list by day (its date search needs date-named folders);
`pennisiandrea/media-explorer-card` and `markaggar/ha-media-card` are maintained and
MIT-licensed, but are a folder browser and a slideshow viewer, with no event time, kind or
day grouping. Any of them would also be a third-party bundle running with the full
session of the logged-in user, which would have to be pinned by SHA-256, shipped by an
init container and reviewed again on each update; a card the repository owns is small
enough to review. The cost is that this card is ours to maintain when Home Assistant's
frontend changes; it uses only `callWS`, `hassUrl`, `locale` and `config.time_zone`.

To add a kind of event (for example a doorbell button): give it its own media folder
under `media_dirs` and an archive automation like `front_door_snapshot_archive` that
names the files `YYYY-MM-DD_HH-MM-SS.jpg`, extend `front_door_snapshot_cleanup` and
`excludePaths` in `system/backups/values.yaml` to that folder (the retention and the
backup exclusion only know `front-door`), then add a `sources` entry with a `label`,
an `icon` and the `media_content_id` to `front-door.yaml`. The card merges all sources
by time.

After syncing run `kubectl -n home-assistant rollout restart deployment/home-assistant`
unless the pod was recreated by the sync (a change to the card or the dashboard is),
then open `/front-door/events` while logged in, check that **Front door** is in the
sidebar and trigger a motion to see the notification open it. Check the pictures are
private with `curl -sk -o /dev/null -w '%{http_code}' https://ha.thecavespace.net/media/front_door/<file>.jpg`,
which must print `401`. Open **Settings > Dashboards** if the entry is missing.

Limits: the whole listing is read each time the dashboard opens, about 300 bytes per
picture, so 50 motions a day for 90 days (4500 files) is 1.4 MB of JSON before WebSocket
compression and took about 0.2 s to build in a test; a much busier camera would
warrant subfolders per month. The event list is not live: it updates on open, on
**Refresh** and when the page becomes visible again. Anyone with a Home Assistant login
sees every picture, as in the Media browser. The card was exercised in Chromium
(Brave) emulating a phone, not in the iOS Companion app, so confirm that on the phone
after the first rollout.

## Bootstrap and platform changes

Install the tools in [`aqua.yaml`](../aqua.yaml), plus Talos and Ansible with
the Kubernetes Python client. Commands run from the repository root and use
the current `KUBECONFIG`; verify its context before deploying:

```bash
kubectl config current-context
```

For new Talos machine configurations, use these `talosctl gen config` patch flags.
Review node-specific disks and interfaces before applying generated configurations.

| Scope / flag | Patch under `talos/patches/` | Purpose |
| --- | --- | --- |
| Both: `--config-patch` | `cilium.yaml` | Disable the default CNI and kube-proxy |
| Both: `--config-patch` | `network.yaml` | Servers VLAN node addresses and API endpoint |
| Both: `--config-patch` | `dns.yaml` | Replace DNS resolvers using JSON Patch |
| Control plane: `--config-patch-control-plane` | `service-accounts.yaml` | API ServiceAccount issuer and audience |
| Control plane: `--config-patch-control-plane` | `node-control-plane.yaml` | Readable monitoring alias |
| Worker: `--config-patch-worker` | `node-worker.yaml` | Readable monitoring alias |
| Worker: `--config-patch-worker` | `worker-nvme.yaml` | Writable NVMe bind mount for kubelet |
| Control plane: `--config-patch-control-plane` | `logging-control-plane.yaml` | Service and kernel log forwarding |
| Worker: `--config-patch-worker` | `logging-worker.yaml` | Service and kernel log forwarding |

Pass each file as `@talos/patches/<file>`. Keep `dns.yaml` as JSON Patch;
strategic merge appends resolvers instead of replacing them. The API issuer and
audience are independent of node addresses. Generated configurations contain
credentials and must stay outside Git. For recovery, use the
[saved configurations and cluster secrets](talos-etcd-recovery.md) instead of
generating a new cluster identity.

Use the pinned Helm and Kustomize tools; Helm 4 requires Kustomize 5.8 or newer.
Render locally with `kustomize build`, including `--enable-helm` where needed.
Cilium is bootstrap-managed so recovery does not depend on ArgoCD. Once Talos
and the Kubernetes API are ready, install Cilium before ArgoCD:

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
Synchronize matching Prometheus Operator CRDs before updating monitoring; see
the [monitoring guide](../system/monitoring/README.md#alerts).

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
| Sealed Secrets Web | `8443` | `sealed-secrets-web-backend-tls` | `sealed-secrets.thecavespace.net` | Envoy watches the Secret volume |

Home Assistant imports `http:` YAML once into `/config/.storage/http`. On a fresh
configuration, verify HTTPS access and confirm the imported settings in
**Settings > System > Network > HTTP server** within five minutes. An unconfirmed
configuration reverts to plain HTTP, breaking Envoy backend TLS and the HTTPS
probes. Later HTTP/proxy changes belong in that UI; YAML changes are ignored
after import. Keep port `8123`, the mounted `/etc/home-assistant/tls/` certificate
and key paths, and the configured trusted proxies. See the
[upstream HTTP configuration guide](https://www.home-assistant.io/integrations/http/).

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
together. Use [Sealed Secrets Web](../system/sealed-secrets-web/README.md) to
seal the `api-token` key for Secret `cloudflare-dns01-token` in `cert-manager`,
without a trailing newline, and save it to
`system/cert-manager-acme/sealed-cloudflare-token.yaml`.

Commit the SealedSecret and sync `cert-manager-acme`. Cert-manager owns temporary
challenge records. An internal CA issuer also exists in `system/cert-manager-ca/`;
keep its offline key under `.secrets/` with a separate backup. CA rotation requires
distributing the replacement public trust before removing the old CA.

## ArgoCD login

GitHub SSO grants admin access to `bart-kochanowicz`; local admin is disabled.
OAuth uses `https://argocd.thecavespace.net` with callback
`https://argocd.thecavespace.net/api/dex/callback`. ArgoCD server pods must resolve
and reach that address for Dex discovery and signing keys.

Use [Sealed Secrets Web](../system/sealed-secrets-web/README.md) to seal the
`dex.github.clientID` and `dex.github.clientSecret` keys for `argocd-secret` in
`argocd`. Preserve `sealedsecrets.bitnami.com/patch: "true"` on both the
SealedSecret and its Secret template in `system/argocd/argocd-sso-sealed-secret.yaml`.
This patches the OAuth keys without replacing other credentials. Commit it and
sync ArgoCD. For SSO recovery, cluster-admin
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

Home Assistant's `configuration.yaml` is managed in Git. Integrations, accounts
and UI-managed automations live on its PVC. An init container creates missing
automation, script and scene files without overwriting existing settings.

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

## Dependency scanning

Run `make validate-dependencies` to scan the root `uv.lock` with the pinned Trivy,
including development and transitive dependencies. `make validate` includes this
check. HIGH/CRITICAL vulnerabilities fail it even when no fix is available;
missing, empty or unanalyzed lockfiles and scanner errors also fail.

The full JSON report is saved to `.cache/dependency-scan/report.json`. The
`Validate` and weekly/manual `Dependency Scan` workflows retain it as the
`dependency-scan` artifact for 14 days, including failed checks. Only the lockfile
is scanned; local environments and credentials are outside this scan's scope.

## Container image scanning

Run `make scan-images` to render application and platform manifests, including
ArgoCD's bootstrap chart, and scan their unique images with the pinned Trivy.
The inventory includes init containers, Helm hooks, custom-resource image fields,
storage helper pods and Prometheus Operator's default config reloader. Scans use
registry images for `linux/amd64`; no cluster credentials or Docker daemon are needed.
Trivy tries the registry mirrors in `.trivy-images.yaml` before the source registry.

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
