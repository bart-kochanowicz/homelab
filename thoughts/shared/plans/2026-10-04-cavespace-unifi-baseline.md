# Cavespace UniFi Baseline: Sequential Implementation Plan

Date: 2026-10-04

Status: Draft PR 01 (#54) opened; documentation checks passed, live inventory
and recovery gates remain pending. No Terraform apply or live migration has
been completed.

## Objective and delivery rules

Implement the operator's **Homelab Network Segmentation — Architecture Handoff**:
seven active LAN VLANs, three visible SSIDs, password-based Home/IoT/Guest
segmentation, permanent MacBook administration, and Guest AirPlay to selected
Home receivers. Retain the previously agreed admin-only remote WireGuard goal.

This revision supersedes the earlier four-SSID, `10.77.*`, Management VLAN 10,
and Talos VLAN 20 design. VLAN 70 now contains all servers, including Houston;
VLAN 90 contains network infrastructure only. VLAN 70 is not a public DMZ.

Prepare and merge one implementation PR at a time. Deploy and verify the
merged stage before opening the next PR. All repository documentation,
comments, commit messages, PR titles/descriptions, and verification records
must be in English. Conversation with the operator is in Polish.

This document is a plan, not authorization to execute a live migration.
Working WAN/GPON configuration is outside implementation scope.

## Repository assessment and changes from the previous plan

| Area | Repository evidence | Required change |
| --- | --- | --- |
| UniFi | `infra/unifi` currently contains WAN documentation and a LEOX runtime script; no UniFi Terraform root exists | Add an isolated root and import existing LAN objects before managing them |
| Terraform | `terraform/main.tf` manages Cloudflare R2; Terraform is `~> 1.16.4` | Preserve the R2 root and add the UniFi provider/root separately |
| State | Garage on Houston at `http://127.0.0.1:3900`; production key `prod/homelab/terraform.tfstate` | Use `prod/unifi/terraform.tfstate` and matching private backups |
| Execution | Houston's wrapper locks each Terraform command; public CI dispatches private R2 apply after validated main pushes | Keep the lock and existing dispatch; do not automatically include UniFi in that apply |
| Cluster policies | Cilium host firewall trusts legacy `192.168.100.0/24`; Minecraft TCP 30000 has broad source access; n8n can reach the old LAN | Prepare additive migration paths, then remove broad legacy permissions |
| GitOps | Application manifests auto-sync from main; the network-policy Application requires manual sync; Cilium is bootstrap-managed | State the actual deployment boundary for every PR |
| Home Assistant | `hostNetwork: true`, no explicit node selector, persistent local-path data | Verify/pin the current PV-bound node; HA follows its node's IP in Servers |
| Storage | Local-path configuration names `talos-2jn-7he` and `/var/mnt/minecraft` | Preserve node names, disks, mounts, and PV/PVC affinity |
| Monitoring | Prometheus/Grafana manifests are already tracked | Inventory what is live; do not assume exact UniFi scrape/exporter endpoints |
| Old architecture | Four SSIDs; guest reserved only; Houston and Talos in different VLANs | Three SSIDs; Guest active; Houston, Talos, HA, NAS and monitoring together in Servers 70 |

The operator confirmed **UCG-Fiber** in response to the hardware discrepancy;
this corrects the previous plan's Cloud Gateway Ultra assumption. Record exact
hardware/software versions and cabling in PR 01 rather than deriving migration
commands or throughput claims from the old plan. Two managed UniFi switches, one U7 Lite,
Houston, one control plane and one worker remain the inventory starting point.

### Working WAN dependency

Preserve Netia GPON → LEOX LXT-010S-H → gateway, VLAN 35/PPPoE, O5 registration,
and the separate LEOX WAN-side management route/SNAT/persistence mechanism.
Do not move LEOX into Management VLAN 90. Do not modify WAN interfaces, `eth6`,
PPPoE, GPON identities, or `infra/unifi/scripts/leox-management.sh`.

The WAN guide still describes `/24`, while the tracked script uses `/32` plus
a host route and SNAT. Record the observed working state during inventory;
this segmentation rollout must not repair or reinstall that mechanism.
Keep `192.168.100.0/24` out of the new LAN address plan. Prove WAN and LEOX
continuity after each gateway policy/provisioning change without changing
those interfaces. Application forwarding cleanup is separate from preserving
PPPoE and the LEOX management SNAT rule.

Retain the proven Admin-to-LEOX management path. LAN trust policies must also
protect the WAN-side ONT management destination from Work/Home/IoT/Guest;
an Internet allow or Management-zone deny alone may not protect that route.
Use source/destination LAN policy without changing its WAN route or SNAT.

## Accepted target architecture

### Networks and names

Use the handoff's VLAN IDs, subnets, and `.1` gateways. Space-themed internal
names preserve the established naming convention; `cavespace-` prefixes SSIDs.
`capcom` remains the Houston account, never a network/SSID name.

| VLAN | Role | Internal name | IPv4 subnet | Clients / access |
| --- | --- | --- | --- | --- |
| 30 | Work | endeavour | 10.0.30.0/24 | Employer-owned devices; cavespace-endeavour |
| 40 | Home | orbit | 10.0.40.0/24 | Personal devices, iPhone, HomePod, Apple TV; Orbit HOME key |
| 50 | IoT | stardust | 10.0.50.0/24 | Generic, less trusted IoT; Orbit IOT key |
| 60 | Guest | comet | 10.0.60.0/24 | Visitors; Orbit GUEST key |
| 70 | Servers | launchpad | 10.0.70.0/24 | Houston, Talos/Kubernetes, NAS, HA, monitoring, future LoadBalancer addresses |
| 80 | Admin | apollo | 10.0.80.0/24 | Owner's MacBook and trusted operator workstations; cavespace-apollo |
| 90 | Management | mission-control | 10.0.90.0/24 | UniFi gateway LAN management, switches, APs and infrastructure management interfaces |

Do not create the old VLANs 10/20 or a DMZ under VLAN 70. Do not split nodes,
Kubernetes storage, NAS and servers into additional VLANs in this iteration.
Management has no ordinary clients or Houston. The labelled wired recovery
port belongs to **Admin VLAN 80**, with the same administration permissions as
Apollo. The operator's MacBook stays on Apollo; local administration requires
neither switching Wi-Fi nor a VPN.

### Recommendations requiring inventory confirmation

The handoff does not freeze host reservations, DHCP ranges, LoadBalancer pools,
VPN addressing, port lists, or secret-loading implementation. Proposed values:

| Item | Recommendation, not a frozen allocation |
| --- | --- |
| DHCP | `.100`–`.199` in each /24; gateway `.1`; infrastructure reservations outside that pool |
| Houston | `10.0.70.10` |
| Control plane / worker | `10.0.70.11` / `10.0.70.12`; preserve existing hostnames |
| NAS | `10.0.70.20` if/when inventoried |
| Switches / AP | `10.0.90.11`, `10.0.90.12`, `10.0.90.20`; reserve after confirming physical devices |
| MacBook | Optional `10.0.80.10` reservation for logs only; never the basis of its privileges |
| Media receivers | Individual reservations outside Home's DHCP pool; inventory before choosing addresses |
| Future LoadBalancer pool | Candidate `10.0.70.200`–`.219`, excluded from DHCP/reservations; do not provision it yet |
| Remote VPN | Candidate `wormhole`, `10.0.100.0/24`, no VLAN 100, fixed peer IPs; validate separately |
| Device names | Retain voyager-01/houston-01; relay-01/relay-02 and pulsar-01 are proposed switch/AP names |

Validate **all** target ranges against current routes, employer VPN routes,
other VPNs, Kubernetes pod/service CIDRs, existing reservations, and WAN/ONT
routes before any apply. The tracked pod CIDR hint is not a substitute for
reading live cluster configuration. A conflict pauses implementation of the
current stage until an explicit architecture revision resolves it.

HA's address is the address of its pinned Talos node, not a separate reservation
for a host-networked pod. Houston and the control plane must have distinct IPs
now that both are in VLAN 70.

### Exactly three visible SSIDs

| SSID | Authentication and proposed bands | VLAN mapping |
| --- | --- | --- |
| cavespace-apollo | WPA3 preferred, initially 5 GHz | Admin 80 |
| cavespace-endeavour | WPA3 preferred, 2.4/5 GHz; transition mode only for demonstrated compatibility needs | Work 30 |
| cavespace-orbit | WPA2 PPSK, 2.4/5 GHz | HOME → 40; IOT → 50; GUEST → 60 |

Do not create separate IoT/Guest SSIDs. Stardust remains an internal IoT name.
HomePod, Apple TV and personal Apple devices use the **HOME** key. Give visitors
only the GUEST key and IoT only the IOT key. Inventory which trusted HomeKit
accessories should remain Home rather than assigning every smart device to IoT.

Each accepted Orbit password must map to exactly its intended VLAN. Reject
invalid keys and test any base/fallback password behavior; do not permit an
undocumented shared password to grant Home or Admin access. Keep PPSK secrets
independent and define separate guest-key rotation/revocation instructions.

Keep Orbit WLAN client isolation off so Home devices can communicate. This is
a shared SSID setting, not a per-PPSK setting. Guest↔Guest and IoT↔IoT traffic
inside their own VLANs is not blocked by the gateway firewall. The baseline
isolates trust zones; additional isolation inside those VLANs requires a
separate capability/design review. Endeavour may enable WLAN client isolation.
Avoid global multicast/broadcast filtering on Orbit until DHCP and Apple
features have passed live tests. PPSK requires WPA2 and cannot use 6 GHz.

Preserve local multicast/IPv6 inside Home for Apple/Thread. Do not enable new
WAN prefix delegation or routed IPv6 on these VLANs in this IPv4 baseline.
Verify there is no cross-zone IPv6 bypass. Features requiring the MacBook and
Home receivers to share a Wi-Fi/VLAN are not implied by Apollo membership;
optional Admin discovery needs its own reviewed exception, not Wi-Fi switching.

### Physical port roles

Final AP uplink: native Management VLAN 90; tagged VLANs 30, 40, 50, 60 and 80.
Do not also configure a device Network Override to the AP's native VLAN 90.
Switch management uses explicit Network Override to **tagged VLAN 90**, with
a different legacy/parking native network on switch uplinks. Prepare every
upstream tag in a separate apply before changing device management/native
selection. Allow only the tags required by each downstream link.

Houston/Talos/NAS use Servers 70 access ports. Wired administration/recovery
uses Admin 80 access ports. Retire legacy untagged SSIDs before changing AP
native management; otherwise old wireless clients could enter Management 90.
Preserve legacy wired paths until Houston and both nodes have moved.

## Firewall, discovery, and monitoring design

### Stateful trust-zone policy

Create one custom zone per LAN VLAN. Deny other inter-zone initiation and allow
replies to permitted flows. Do not mistake routed-zone policy for isolation
inside one VLAN. Server/application authentication and Cilium host/pod policies
remain necessary when Houston, Kubernetes and storage share Servers 70.

| Source | Permitted initiation | Denied by default / constraints |
| --- | --- | --- |
| Work 30 | Internet; required Gateway DHCP/DNS/NTP | All other LAN trust zones and gateway administration |
| Home 40 | Internet; named services in Servers; inventoried IoT services | Work, Guest, Admin, Management and all unlisted services |
| IoT 50 | Internet; required basic gateway services | Home, Servers, Admin, Management, Work and Guest; integration callbacks only by explicit exception |
| Guest 60 | Internet; selected Home AIRPLAY_DEVICES | All private zones and general Home access; no gateway administration |
| Servers 70 | Internet; temporarily Management ANY; exact HA→IoT integration rules | No general client-zone access; no implicit reverse Management access |
| Admin 80 | Internet; Servers ANY; Management ANY; gateway administration | Work and Guest; Home/IoT access only where operationally useful and documented |
| Management 90 | Required update/NTP/vendor Internet services and controller traffic | Work, Home, IoT, Guest, Admin, Servers; telemetry push only by named future exception |
| Admin VPN | Same intended privileges as Admin, enforced in the VPN zone | Work and Guest; tunnel routes are not authorization |

Admin permissions derive from **VLAN 80 membership**, never from the MacBook's
reserved IP. Preserve ANY administration permissions at the UniFi routing
layer while retaining authentication and deliberate host/pod protection.
The initial Servers→Management ANY exception is intentionally one direction;
return traffic is stateful, not a reverse ANY allow. Record its owner, purpose,
and review milestone: replace it with concrete sources/protocols when the
monitoring implementation is defined. Do not assert monitoring ports are frozen.

### Gateway is a separate zone

Traffic to gateway-owned IPs, including each VLAN's `.1`, belongs to the built-in
**Gateway** zone. Admin→Management ANY does not itself grant UCG administration;
add Admin→Gateway administration permissions. Likewise, Servers→Management
ANY does not provide Houston's Network API access. Preserve a separate
Houston→Gateway HTTPS/API permit, including its old/new IPs during migration;
scoping this to Houston's reservation is a recommendation, not a MacBook rule.

Restricted VLANs need DHCP UDP 67, DNS TCP/UDP 53, required NTP where actually
served, and mDNS UDP 5353 only for selected relay networks. Deny Gateway
administration from Work/Home/IoT/Guest. Preserve observed Management device
controller traffic, including inform TCP 8080 and STUN UDP 3478 where used.
Do not block established replies or required infrastructure services while
restricting Gateway access. Separate NEW-traffic restrictions from INVALID
handling; review the actual firmware's effective system policy.

Require applicable baseline denies and Gateway administration guards to cover
both IPv4 and IPv6 explicitly. Do not inherit an IPv4-only policy default.
Verify `ip_version = "BOTH"` against the pinned provider schema in PR 02 and
check effective system-rule coverage. Test UCG administration through each
VLAN's IPv6/link-local addresses as well as IPv4; absence of routed IPv6 or
WAN delegation does not protect a local Gateway management endpoint.
Preserve required IPv6 link-local control traffic/neighbor discovery for local
Home operation; do not enable routed IPv6 to satisfy these tests.

### Guest AirPlay is a baseline requirement

Reserve selected Home receiver IPs and manage an `AIRPLAY_DEVICES` address group.
Initially allow Guest→that group with a broader destination-service allowance
if needed, plus return-only traffic; **never Guest→Home ANY**. Narrow the ports
from working sessions/captures after validation. Add receiver-initiated NEW
callbacks only if evidence proves they are necessary, with equally narrow
source/destination scope. Receiver-side Apple access/password settings also
need to permit the intended visitors.

Use the accepted manual UniFi mDNS exception in **Custom** mode: Home 40 and
Guest 60 only, with AirPlay services. Start with the vendor AirPlay service set,
including `_airplay._tcp` and `_raop._tcp`, then retain only required discovery.
Inspect actual defaults: newly created networks can enable broad proxying.
Disable unwanted proxy scope before clients join; do not use Auto/all VLANs.

Native mDNS network/service filtering does not filter individual receiver IPs.
Other matching Home advertisements may be visible, while AIRPLAY_DEVICES limits
actual routed access. If selected-only visibility becomes mandatory, a separate
reflector/design change is required; do not claim this baseline provides it.
Discovery and playback are separate tests. Prove sessions traverse Guest 60
and Home 40 rather than succeeding via Apple TV peer-to-peer/Bluetooth paths.

### Home Assistant and monitoring

HA stays on its existing PV-bound node, eventually Servers 70. Start with
explicit HA-host→IoT destination/service allowances derived from current
integrations. No IoT→Servers ANY, and no default IoT/Servers/Home mDNS relay.
The gateway sees the node's source IP, so a host-based HA allowance can also
cover other processes or SNATed workloads on that node. Preserve host/pod
policy and document this limit rather than claiming process-specific isolation.
Home may reach HA TCP 8123; inventory any required IoT callbacks separately.
If a concrete integration requires mDNS/SSDP later, document and test the
smallest exception. Do not simply add all networks to the Guest/Home reflector;
verify that any expansion can preserve the intended discovery boundaries.
Cross-VLAN HA Matter hosting remains a later design iteration.

Monitoring collection is Servers→Management. Once collector locations and
protocols are known, narrow the temporary ANY exception to required HTTPS/API,
SNMP, ICMP/exporters or observed alternatives. Future Management→Servers
syslog/telemetry must name a receiver and service; it is not covered by the
collection permission. Existing monitoring manifests need a live inventory,
not an automatic network-architecture change.

Keep applications private. Disable UPnP/NAT-PMP where applicable and remove
existing public Minecraft application forwarding during final cleanup without
altering LEOX SNAT. Public websites/Minecraft, DMZ design, LoadBalancer allocation,
private HTTPS ingress, new monitoring exporters and automatic UniFi applies are
follow-up work. V1 private-service checks cover HA 8123, private Minecraft 30000
if running, and Kubernetes API/port-forward access to ClusterIP ArgoCD/n8n.

## Terraform resource layout and secrets

### Repository layout

Adapt the requested logical split to the existing Terraform convention; keep
`infra/unifi` as operational documentation and unchanged WAN support material.
Do not create a second competing UniFi root there.

```text
terraform/unifi/
  backend.tf, providers.tf, main.tf, variables.tf, outputs.tf
  variables.tfvars.json.example, README.md, .terraform.lock.hcl
terraform/modules/unifi/
  providers.tf, networks.tf, wifi.tf, firewall.tf, groups.tf
  devices.tf, dns.tf, vpn.tf, variables.tf, outputs.tf
infra/unifi/
  README.md
  docs/network-inventory.md, docs/network-runbook.md
  docs/provider-exceptions.md
  docs/wan-netia.md                    # unchanged WAN dependency
  scripts/leox-management.sh           # unchanged runtime support
```

Pin `ubiquiti-community/unifi = 0.57.0` and retain Terraform `~> 1.16.4`.
The root configures the provider/backend and calls `../modules/unifi` with typed
network, device/port, reservation, SSID, service-group and VPN peer inputs.
The module owns networks, WLANs, zones/policies, groups, ports/devices, supported
private DNS records and WireGuard resources. WAN/PPPoE and LEOX remain unowned.

Use only `unifi_firewall_zone.network_ids` for zone membership; do not also own
it through `unifi_network.firewall_zone_id`. Define explicit forward ALLOW and
reverse RESPOND_ONLY policies with `create_allow_respond = false`. Reverse
service ports are source ports; do not copy them into ephemeral destination
port matches. Keep nonsecret variables and outputs documented in English.

The custom-zone system deny/order behavior must be verified on installed
firmware. The provider's policy `index` is read-only, so do not assume Terraform
can reorder conflicting catch-all custom blocks and allows. Test system deny
and custom allow precedence on pilot VLANs; if absent, revise this stage's
implementation/exception plan before migrating clients. ZBF prerequisites
(Network 9+ and gateway firmware 4.1+) are inventory gates, not upgrade authority.

### Secret injection recommendation

Use the existing private Houston SSD workspace, private backend and host wrapper.
Recommended baseline: an operator-owned, mode-0600 ignored JSON input file in
a mode-0700 directory, populated from the operator's password manager. This is
a proposed mechanism to finalize in PR 02, not an already-deployed secret store.
Keep real credentials out of Git, command-line arguments, example values,
public CI, plan comments and logs. Run with `umask 077` and shell tracing off.

Use a normal **sensitive** map for HOME/IOT/GUEST PPSK inputs. The provider uses
`private_preshared_keys_enabled` and entries containing `network_id`/`password`;
those passwords are stored in Terraform state. Do not declare them ephemeral:
the nested PPSK fields are not write-only. Sensitive marking redacts normal UI
output; it does not encrypt state. Protect backend/SSD access, saved plans,
state exports and the private R2 backups as secret material.

For ordinary Apollo/Endeavour passwords, use ephemeral sensitive inputs and
`passphrase_wo` where supported. It has no password-change version trigger;
rotation needs a documented reviewed WLAN update/replacement procedure and
reconnection checks, not a promise of automatic secret drift detection.
PPSK guest rotation must verify old-key rejection and revoke/reconnect existing
sessions as necessary; changing a password alone is not proof of session loss.

Retain local authenticated controller access with verified TLS. WireGuard client
private keys stay on clients; only public keys are inputs. The server private key
and VPN profiles/state are confidential. No secret outputs or public artifacts.

### Backend and operations

Use Garage key `prod/unifi/terraform.tfstate`; preserve the existing R2 key.
All production Terraform commands run on Houston through `/usr/local/bin/terraform`
and the shared process lock. Garage remains loopback `http://127.0.0.1:3900`.
The lock covers individual commands, not an entire plan/apply workflow; serialize
operator sessions and reject stale saved plans after intervening state changes.

Extend the existing backup procedure with `terraform/unifi` and state name
`prod/unifi`. Require verified readback/hash snapshots before mutation once state
exists, and define first-state bootstrap separately. Existing marker restore
rehearsals do not prove recovery of UniFi production state; record a matching
configuration/provider/private destination recovery procedure. Do not test it
by restoring production state or applying cloned resources to the live controller.

Public CI performs backend-disabled init/validate with placeholder inputs and no
controller credentials. UniFi applies remain deliberate on the merged revision;
the current private R2 apply dispatch must not acquire UniFi ownership. Pause
competing jobs during migrations. Automatic UniFi CI apply is a later iteration.

### Provider and platform limitations

- The provider uses controller APIs whose behavior must be tested against the
  installed Network/gateway versions; an API credential is not compatibility proof.
- PPSK secrets persist in state; the ordinary passphrase write-only option does
  not protect them. Orbit authentication/radio/client isolation settings are shared.
- Policy ordering is not fully manageable; verify effective default deny/allow
  precedence rather than relying on guessed order.
- The legacy `multicast_dns` network field is not proof of effective modern UCG
  mDNS settings. Custom Home/Guest scope is a documented manual exception with
  owner, settings, evidence and recheck after provisioning/upgrades.
- Native mDNS filters services/networks rather than named AIRPLAY_DEVICES receivers.
- Firewall Gateway semantics differ from custom Management-zone membership.
- UniFi routed rules do not isolate same-VLAN server, Guest or IoT peers.
- AP native management and switch tagged management require different procedures.

## Sequential PR workflow

Only one implementation PR is open at a time. Branch from the latest merged
`main` using `codex/unifi-XX-<english-slug>`. Do not stack PRs.

1. Implement that stage only, with English deployment, validation and rollback.
2. Run relevant checks, open the PR, review the diff and required CI.
3. Merge after repository protections/review requirements are satisfied.
4. Deploy the merged revision; re-plan if the reviewed revision/state changed.
5. Complete live checks and record sanitized evidence, PR URL, SHA, time, backup
   receipt and any manual exception in `docs/security-verification.md`.
6. Open the next PR only when the current stage is verified.

A failed merged stage needs a corrective PR for that same stage, then recovery
verification before the next numbered PR. Git revert alone does not undo live
Terraform, UniFi, or Talos changes. Re-apply reviewed configuration; restore
Terraform state only for actual loss/corruption, never as a network rollback.

Use trusted pilot devices only until isolation is proven. Creating VLANs/SSIDs
without restrictive changes is safe only while they are unused or under pilot
control. Real Work/IoT/Guest clients must not enter a temporary flat-LAN window.
Management-device cutover follows client migration so legacy untagged SSIDs
can be retired safely before changing the AP's native network. This refines
the handoff's suggested order without changing its final trust boundaries.
Disruptive stages need an operator, tested wired recovery and a maintenance
window. The single control plane has a planned outage. Houston must not migrate
its own connectivity through a runner job or Terraform apply that depends on it.

### PR sequence

| PR | English title | Deployment boundary |
| --- | --- | --- |
| 01 | docs(unifi): align the baseline with the architecture handoff | Inventory, design and recovery prerequisites |
| 02 | build(terraform): add isolated UniFi state and secret inputs | Root/module, CI, private secret-loading procedure |
| 03 | feat(unifi): adopt the existing LAN configuration | Imports and a no-change plan |
| 04 | feat(unifi): prepare VLAN networks and tagged paths | Unused networks/DHCP; wired pilot only |
| 05 | fix(network): prepare cluster policies for VLAN migration | Additive Cilium policy and manual sync |
| 06 | feat(unifi): establish permanent Apollo administration | Admin SSID, wired recovery, tested management paths |
| 07 | feat(unifi): prepare Orbit PPSK and Endeavour pilot networks | Two SSIDs and key-to-VLAN tests; no production cutover |
| 08 | feat(unifi): enforce stateful trust-zone isolation | Default deny, Gateway services and transitional allows |
| 09 | feat(unifi): enable admin-only WireGuard access | External access/revocation tests |
| 10 | feat(unifi): enable scoped Guest AirPlay and HA integration paths | AIRPLAY_DEVICES, Home/Guest mDNS, explicit HA services |
| 11 | feat(unifi): migrate Home Work IoT and Guest clients | Production clients, one group at a time |
| 12 | feat(unifi): migrate infrastructure to Management VLAN 90 | Switch/AP management, one device at a time |
| 13 | feat(infra): migrate Houston to Servers VLAN 70 | Independent local host/network cutover |
| 14 | feat(talos): migrate the worker to Servers VLAN 70 | Staged worker network/restart |
| 15 | feat(talos): migrate the control plane to Servers VLAN 70 | Staged control-plane network and planned outage |
| 16 | fix(network): retire legacy paths and verify segmentation | Cleanup, final tests and exception register |

### PR 01 — Handoff, inventory, and recovery prerequisites

**Changes:** Commit this revised plan and add the English inventory/runbook.
Record gateway model/versions, controller/site IDs, physical ports, native/tagged
paths, current addresses/SSIDs/forwarding, WAN/LEOX working observations, route
conflicts, cluster CIDRs, HA integrations/PV-bound node, media receivers and
current monitoring. Record the confirmed UCG-Fiber model and verify its exact
ports/versions before hardware-specific instructions. Preserve backups/device identities privately.

Classify NAS/other non-Talos servers as currently live or future-only. If any
are live, insert a separate, reviewed wired Servers migration PR for each
appropriate dependency group before PR 16, with storage-client read/write,
mount/export, backup and rollback tests. Determine its position from actual
dependencies; keep legacy storage paths until verified. The sixteen core PRs
do not imply unobserved servers can be silently left on a retired LAN.

**Gate:** Validate target ranges, ZBF/provider compatibility, controller TLS/API,
wired recovery, current connectivity and recoverable UniFi/etcd/PVC backups.
Select proposed reservations and secret procedure deliberately. No WAN changes.

**Rollback:** Documentation/read-only inventory only.

**Progress (2026-10-04):**

- [x] Record the accepted seven-VLAN / three-SSID architecture and sequential PRs.
- [x] Add a minimal UniFi README and English inventory/recovery runbook.
- [x] Record read-only UniFi UI and Houston observations with their evidence source.
- [x] Record unreachable cluster endpoints as unresolved, without inferring node roles.
- [ ] Verify remaining ports/versions, identities, cluster/storage/application inventory.
- [ ] Validate all range conflicts and accept reservation/secret-loading choices.
- [ ] Verify controller TLS/API from Houston and rehearse wired/local recovery.
- [ ] Confirm recoverable private UniFi, etcd and PVC backups.
- [x] Pass local documentation checks and full GitHub Validate (fdaf1c2).
- [ ] Review and merge PR 01 after resolving its live gates.
- [ ] Confirm all PR 01 live gates before opening PR 02.

Detailed current findings and unresolved gates are in
[network-inventory.md](../../../infra/unifi/docs/network-inventory.md). PR 01
can be reviewed as a draft while evidence is collected; it does not authorize
implementation of later stages or certify historical backups as current.

### PR 02 — Terraform, secrets, and isolated state

**Changes:** Add the proposed root/module skeleton, pinned provider/lockfile,
English variable descriptions, credential-free examples, private secret loading,
separate backend, backup/recovery and manual plan/apply instructions. Extend
`make validate` for backend-disabled UniFi validation and recursive cache
exclusions. Preserve the R2 root and its automatic workflow behavior.

**Gate:** CI needs no controller/secrets. Houston initialization selects only
`prod/unifi/terraform.tfstate`; skeleton proposes no live resources. Demonstrate
private input permissions, redacted logs and first-state handling with placeholders.

**Rollback:** Remove unused scaffolding; preserve initialized state.

### PR 03 — Import existing LAN configuration

**Changes:** Import real existing LAN objects needed for future ownership,
including complete device port overrides. Keep actual live defaults. Exclude
WAN/PPPoE/LEOX ownership and guessed IDs.

**Gate:** Reviewed no-change plan, correct lineage/key, tested credentials/TLS,
wrapper locking and verified R2 state snapshot.

**Rollback:** Reconcile code/state ownership privately; do not destroy live objects.

### PR 04 — VLANs, DHCP, and upstream tags

**Changes:** Create VLANs 30/40/50/60/70/80/90, confirmed DHCP/reservations and
required profiles/tags. Keep existing client/native management assignments.
Do not introduce broad restrictive cutovers yet. Inspect effective mDNS defaults
and disable automatic/global forwarding for the new networks.

**Gate:** Wired pilot on each new VLAN obtains the correct address/gateway,
DNS/Internet and expected tag path. Existing WAN/LEOX/LAN stay functional.
No real untrusted clients join the new networks at this stage.

**Rollback:** Restore prior profiles; remove only unused additions.

### PR 05 — Prepare cluster access before client changes

**Changes:** Add and manually sync Cilium old/new-node and legacy migration
exceptions, Admin 80 operator/API access, required exact Houston administration
and the proposed VPN range. Prepare Home→current HA 8123 and inventoried
integration callbacks. Do not grant Management 90 general Talos/Kubernetes
operator permissions. Record HA placement; keep auto-synced HA manifest changes
out of this PR. Retain old paths until their replacements are verified.

**Gate:** Existing applications/data and known-listening admin paths work before
and after manual policy sync; forbidden source tests use real listening targets.

**Rollback:** Restore and manually sync the prior policies.

### PR 06 — Permanent Apollo and wired recovery

**Changes:** Create cavespace-apollo on Admin 80 and the labelled Admin wired
port. Add only the temporary allows needed to reach old servers/management,
new Management and Gateway administration. Keep AP native management unchanged.
The MacBook stays on Apollo; permissions use its VLAN, not reservation IP.

**Gate:** MacBook and wired operator reach UCG, switches/APs, current servers,
Talos/Kubernetes and the new Management gateway endpoint. Houston's old address
still has a separately tested Gateway API path. Do not tighten old access yet.

**Rollback:** Restore old access/profiles through the proven wired path.

### PR 07 — Orbit PPSK and Work pilots

**Changes:** Create cavespace-orbit WPA2 with HOME→40/IOT→50/GUEST→60, and
cavespace-endeavour WPA3 preferred. Use only trusted test clients and keep the
guest key undistributed. Keep Orbit isolation off; test Work isolation separately.
Document actual security fallback and password rotation behavior.

**Gate:** Each key obtains exactly the expected VLAN/subnet; reconnect/renew and
invalid-key tests pass. No fallback key grants unintended trust. Confirm only
three new visible SSIDs; temporary legacy SSIDs may remain during migration.

**Rollback:** Disable pilot WLANs/keys; existing clients remain on old networks.

### PR 08 — Default deny with tested administration

**Changes:** Introduce custom zones and the final stateful access matrix only
now that Admin/recovery works. Keep narrow old/new Houston/node/HA exceptions.
Permit Admin→Servers/Management ANY, explicit Admin→Gateway administration,
Houston→Gateway API, Servers→Management temporary ANY and return-only reverse.
Restrict Gateway services without breaking DHCP/DNS/NTP/controller traffic.
Review application forwarding/UPnP independently of WAN/LEOX runtime settings.

**Gate:** Pilot positive/negative tests prove effective rule order, default deny,
stateful replies, dual-family Gateway/link-local protection and ONT management
destination protection. Work/IoT/Guest remain
pilots until their applicable rules pass. WAN/LEOX and Houston refresh survive.

**Rollback:** Re-apply last verified LAN policy/profile via Admin wired recovery;
restore only needed transitional paths, not a blanket flat LAN.

### PR 09 — Retained remote administration goal

**Changes:** Add wormhole WireGuard, proposed UDP 51820 and separately validated
non-VLAN tunnel range. Use fixed peers with client-generated public keys and
split-tunnel/private DNS instructions. Peer `allowed_ips` describes networks
behind a peer, not target authorization; apply Admin-equivalent firewall rules
in the built-in VPN zone, including Work/Guest exclusions.

PR 01 found existing control-plane `wg0` configuration at 10.0.0.1/24 with a
10.0.0.2/32 peer. Inventory its current listener, routes, forwarding, purpose
and operator dependency before deploying the gateway VPN. Preserve any working
recovery path until the replacement is verified; do not silently remove it or
assume that a reported wg0 address proves remote access works.

**Gate:** External/cellular client reaches intended Admin services; forbidden
zones stay blocked; DNS/replies work and removing a test peer revokes access.

**Rollback:** Remove/disable affected peers/listener and reconcile policy.

### PR 10 — Guest AirPlay and explicit HA services

**Changes:** Add confirmed media reservations and AIRPLAY_DEVICES. Allow Guest
only to those Home targets, with accepted initial broader service scope and
stateful replies. Configure manual Custom mDNS for Home/Guest AirPlay only,
recording settings that Terraform cannot own. Confirm receiver access settings.
Add inventoried HA-host→IoT services and exact required callbacks; retain the
current legacy HA host until its node migration, with no default HA mDNS relay.

After PR 08 isolation is verified, perform controlled pilot cutovers here:
move the selected actual receivers and paired trusted Apple clients to HOME
VLAN 40, and representative required IoT devices to IOT VLAN 50. Verify their
reservations, source VLANs and HA endpoints before testing Guest playback or
integration commands. PR 11 migrates the remaining clients and rechecks these
pilots; it is not a prerequisite for passing this stage's gate.

**Gate:** Guest pilot discovers and streams to selected receivers over routed
Guest/Home traffic; unselected Home/services stay inaccessible. Test stop,
reconnect and actual required casting functions. Home Apple functions and HA
integrations work; general Guest→Home and IoT→Servers initiation fails.

**Rollback:** Restore prior scoped policy/discovery settings; keep Guest pilot
only until recovery is verified. Never replace this with global mDNS.
Return affected pilot receivers/IoT and paired Home clients to their verified
previous network and integration settings if needed.

### PR 11 — Production client migration

**Changes:** Pin HA to its existing PV-bound node if live scheduling requires
an explicit constraint. After merge, wait for automatic application sync/Ready
with the same PVC/data before moving clients. Prior Cilium/UniFi rules are
already deployed and tested. Move Home, Work, IoT and finally Guest in small
groups; retest the appropriate matrix after each group. Keep MacBook on Apollo.

**Gate:** Correct VLAN/key/DHCP/DNS/Internet; Home Apple functions, Guest AirPlay,
HA integration traffic and Work/IoT isolation pass. Record all old-SSID clients.
No normal client uses Management and no separate IoT/Guest SSID is created.

**Rollback:** Restore only a verified legacy client network/profile and its
necessary policies. Do not reopen general legacy trust to restricted clients.
Revert HA pin only without moving/deleting its bound storage.

### PR 12 — Management VLAN 90 cutover

**Changes:** Retire every legacy untagged SSID before changing AP native
management. Prepare tagged Management 90 end-to-end in a separate apply, then
move one switch/AP at a time. Switches use tagged override 90 with a different
native legacy/parking VLAN; the AP uses native 90 without matching override.
Retain old wired paths for Houston/Talos and the tested Admin recovery port.

Switch provider endpoint to verified `10.0.90.1` only after authenticated
Houston refresh works through the explicit Gateway API path; do not depend on
cluster-hosted DNS. Preserve full port overrides and controller/device traffic.

**Gate:** Each device returns online/reprovisions before the next. All three
WLANs/PPSKs, API, trunks, legacy wired hosts, WAN/LEOX and recovery work.

**Rollback:** Restore that device's old native/IP/profile through local access.
Re-enable an old SSID only with its verified legacy VLAN, never Management 90.

### PR 13 — Houston to Servers VLAN 70

**Changes:** Prepare target access/host configuration, pause idle runner jobs,
finish verified state backups and preserve old/new Gateway API allowances.
An independent wired operator stops the runner and changes Houston's network.
Reconnect at the confirmed proposed `10.0.70.10`; reconcile Terraform ownership.

Keep Garage loopback, SSD, state keys, capcom account, credentials and wrapper
lock unchanged. Do not perform this move through Houston's own dependent job.

**Gate:** SSH, SSD, Garage read/write, locks, R2 snapshots, UniFi API and both
Terraform roots work. Resume the runner only after recovery checks.

**Rollback:** Locally restore old host addressing/port and verify backend/API
before resuming jobs; retain the same state.

### PR 14 — Worker to Servers VLAN 70

**Changes:** Create private API DNS pointing to the old control-plane IP.
Apply endpoint/SAN-only configuration on the still-old cluster and verify API
TLS/kubeconfig first. Preserve current valid address selectors; do not apply
new-only control-plane selectors early. Stage the worker's new networking,
then coordinate restart and port change. Preserve secrets/CNI/CIDRs/node/data.

If it hosts HA, install additive new-IP integration rules before cutover,
then change HA DNS with the host address. Any approved integration-specific
reflector exception changes at the same point; do not introduce one by default.

**Gate:** Same node identity, new InternalIP, Talos API, Ready/Cilium/DNS, old
control-plane communication and PV/application data; HA checks if hosted here.

**Rollback:** Restore worker networking/port through local access; no reset/bootstrap.

### PR 15 — Control plane to Servers VLAN 70

**Changes:** Take fresh etcd/PVC backups. Stage confirmed addressing and valid
kubelet/etcd selectors, then coordinate restart/port during the planned outage.
Switch private API DNS to the confirmed proposed `10.0.70.11`, update Talos
endpoints/kubeconfig and reconcile node addresses. If HA is here, deploy
additive new-IP rules first and update its DNS with the cutover.

**Gate:** Healthy etcd/advertised addresses, API TLS/DNS, both nodes Ready,
Cilium, application/storage checks and Admin access pass. Both nodes and
Houston now share Servers 70 without an invented storage/Kubernetes VLAN.

**Rollback:** Restore old networking/endpoint/port locally. Etcd restore is a
separate disaster-recovery procedure, not routine network rollback.

### PR 16 — Legacy retirement and final acceptance

**Changes:** Remove temporary old-address exceptions, unused SSIDs/profiles,
obsolete DNS/SAN entries where safe and broad legacy Cilium/n8n allowances.
Remove public Minecraft application forwarding; restrict host/pod paths using
observed NodePort/SNAT source behavior. Preserve WAN/LEOX management SNAT.

Delete the old LAN only if unused and supported. Otherwise propose isolated
legacy-parking on a collision-checked unused range, no DHCP/SSID/client ports
or access to trusted/Gateway administration/Internet. If deleting its switch
native network, prepare an unrouted VLAN-only parking network first (candidate
VLAN 254); Management stays tagged 90. Do not reuse ONT space for parking.

Review/narrow AirPlay services from evidence. Keep the temporary one-direction
Servers→Management monitoring exception only with its documented review milestone;
no implicit reverse allow. Update README/runbooks/exception register and record
all final tests, private backup receipts and no-change plans.

**Gate:** All acceptance tests pass; exactly three visible SSIDs, no target
legacy clients/servers, effective policy matrix and documented manual exceptions.
Any conditional NAS/other-server migration PRs from inventory are also complete.

**Rollback:** Re-apply only needed paths from the last verified configuration.
Restore Terraform state only after actual state loss/corruption.

## Verification, evidence, and follow-up decisions

For Terraform changes: `terraform fmt -check -recursive terraform`,
backend-disabled initialization, `terraform validate`, required CI, reviewed
live plan on Houston, and post-apply no-change plan plus verified snapshot.
For manifests: relevant YAML/Kustomize/security checks and deployment-specific
sync. Documentation-only work needs link/whitespace checks, no infrastructure
execution. Never record an unperformed live check as passed.

| Origin / scenario | Positive smoke tests | Negative / boundary tests |
| --- | --- | --- |
| Work | Internet/DNS; required employer VPN works | Home/IoT/Guest/Servers/Admin/Management and gateway admin blocked |
| Home | Internet, Apple Home/AirPlay, HA 8123, named private services | Operator/API and unlisted private services blocked |
| IoT | Internet; inventoried commands/callbacks | Unsolicited Home/Servers/Admin/Management/Work/Guest access blocked |
| Guest | Internet; selected receivers discovered and playback works | General Home, unselected receivers, Servers/Admin/Management/Work/IoT blocked |
| Admin | MacBook remains Apollo; ANY routing to Servers/Management, gateway administration | Work/Guest blocked; privileges do not depend on MacBook IP |
| Servers | Internet, Houston API/backend, cluster/storage/HA; temporary Management access | No unrestricted client access or unapproved reverse monitoring path |
| Management | Devices online/reprovision; required update/NTP/controller connectivity | No initiated general client/Servers access |
| VPN | External admin access/DNS, intended routes and peer revocation | Work/Guest exclusion; routes cannot bypass authorization |
| PPSK | HOME/IOT/GUEST key placement, renewal/reconnect, private secret loading | Invalid/fallback/rotated keys cannot grant unintended trust |
| Cross-cutting | WAN/LEOX from Admin, wired recovery, node identities/PVC data, private backups | IPv6/link-local Gateway admin bypass, ONT access from restricted clients, global mDNS leakage, unexpected public application access |

Use known-listening targets for prohibited-access tests; closed ports/timeouts
alone are not policy proof. Test with fresh sessions to avoid established-state
false positives. Correlate source VLAN/IP, gateway flow logs and Cilium/Hubble
where relevant. Check Guest AirPlay on the actual receivers and demonstrate
routed traffic rather than peer-to-peer success. Capture sanitized evidence
only; no packet payloads containing credentials or state/plan secret output.

Keep a stage ledger in `docs/security-verification.md`: PR URL, merged SHA,
deployment mechanism/time, positive/negative results, backup receipt, manual
exception settings and rollback outcome. Each PR description uses English
Changes / Validation / Deployment / Rollback sections and states checks actually
completed separately from checks still required after deployment.

Inventory/implementation must finalize these recommendations explicitly:
DHCP/reserved addresses, future LB pool, VPN range, private secret-loader choice,
Endeavour WPA3 compatibility, selected receivers, exact AirPlay/HA/monitoring
ports, and any optional Admin discovery. None are invented as frozen decisions.

## References

- [UniFi operational material](../../../infra/unifi/README.md)
- [Existing Terraform backend](../../../terraform/BACKEND.md)
- [Private state backups](../../../terraform/R2_BACKUP.md)
- [Houston operations](../../../infra/ansible/README.md)
- [Security and recovery runbook](../../../docs/security-runbook.md)
- [Verification ledger](../../../docs/security-verification.md)
- [Provider v0.57.0](https://github.com/ubiquiti-community/terraform-provider-unifi/releases/tag/v0.57.0)
- [Pinned WLAN/PPSK implementation](https://github.com/ubiquiti-community/terraform-provider-unifi/blob/v0.57.0/unifi/wlan_resource.go)
- [UniFi PPSK and VLAN assignment](https://help.ui.com/hc/en-us/articles/29887064407319-Using-PPSK-RADIUS-for-Multiple-VLANs-On-an-SSID-in-UniFi-Network)
- [UniFi zone-based firewall](https://help.ui.com/hc/en-us/articles/115003173168-Zone-Based-Firewalls-in-UniFi)
- [UniFi VLAN and management troubleshooting](https://help.ui.com/hc/en-us/articles/9592924981911-Virtual-Network-VLAN-Troubleshooting)
- [UniFi mDNS proxy](https://help.ui.com/hc/en-us/articles/12648701398807-UniFi-Gateway-Multicast-DNS-mDNS-Proxy)
- [Apple AirPlay deployment](https://support.apple.com/en-gb/guide/deployment/-dep9151c4ace/web)
- [Apple HomePod networking](https://support.apple.com/en-gb/guide/homepod/apdfb81a72e4/homepod)
- [Home Assistant Matter networking](https://www.home-assistant.io/integrations/matter/)
- [Talos staged configuration](https://docs.siderolabs.com/talos/v1.11/configure-your-talos-cluster/system-configuration/editing-machine-configuration)

Check Talos and provider procedures against the installed versions inventoried
in PR 01 before execution.
