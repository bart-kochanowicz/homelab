# Cavespace Network Architecture and Implementation Plan

## Target architecture

The UCG-Fiber network uses seven LAN VLANs and exactly three visible SSIDs.
Houston, Talos, Kubernetes storage, NAS, Home Assistant and monitoring share
Servers VLAN 70. Management VLAN 90 contains network infrastructure only.
The owner's MacBook stays on Admin VLAN 80 for local administration; remote
administration uses a gateway WireGuard VPN.

Netia GPON, LEOX LXT-010S-H, VLAN 35/PPPoE and the existing WAN-side LEOX
management route/SNAT remain outside this implementation. LEOX does not belong
to LAN Management VLAN 90. Application services remain private; public websites,
Minecraft publication and a DMZ require a separate design.

## Networks and addressing

Each VLAN uses the listed /24 and a gateway at `10.0.<VLAN>.1`.

| VLAN | Role | Internal name | Subnet | Members |
| --- | --- | --- | --- | --- |
| 30 | Work | endeavour | 10.0.30.0/24 | Employer-owned devices |
| 40 | Home | orbit | 10.0.40.0/24 | Personal devices, iPhone, HomePod, Apple TV and trusted HomeKit devices |
| 50 | IoT | stardust | 10.0.50.0/24 | Generic and less trusted smart devices |
| 60 | Guest | comet | 10.0.60.0/24 | Visitors |
| 70 | Servers | launchpad | 10.0.70.0/24 | Houston, Talos, Kubernetes, storage, NAS, HA and monitoring |
| 80 | Admin | apollo | 10.0.80.0/24 | Trusted operator workstations and the wired administration port |
| 90 | Management | mission-control | 10.0.90.0/24 | Gateway LAN management, switches, APs and infrastructure management interfaces |

No additional Kubernetes/storage VLAN is required. VLAN 70 is not a public
DMZ. `capcom` remains the Houston user account, not a network or SSID name.

The following allocations are recommendations to confirm before implementation,
not approved reservations. Check LAN, employer VPN, other VPN, Kubernetes,
LoadBalancer and WAN/ONT ranges for conflicts.

| Allocation | Recommendation |
| --- | --- |
| DHCP | `.100`–`.199` in each /24; reservations outside the pool |
| Houston | 10.0.70.10 |
| Control plane / worker | 10.0.70.11 / 10.0.70.12 |
| NAS | 10.0.70.20 |
| Switches / AP | 10.0.90.11, 10.0.90.12 / 10.0.90.20 |
| MacBook | Optional 10.0.80.10 for predictable logs; privileges come from VLAN membership |
| Media receivers | Individual Home reservations outside DHCP |
| Future LoadBalancer pool | 10.0.70.200–10.0.70.219, reserved from other allocations |
| WireGuard | `wormhole`, candidate 10.0.100.0/24; no VLAN 100 |

Home Assistant uses its hosting node's address because it runs with
`hostNetwork`. Preserve node identities, Pod/Service CIDRs, disks and PV/PVC
node affinity. Talos kubelet and etcd address selection must use stable Servers
addresses. Kubernetes API DNS, certificate SANs and client endpoints must agree.

## Wi-Fi

| SSID | Security | Bands | VLAN assignment |
| --- | --- | --- | --- |
| cavespace-apollo | WPA3 preferred | 5 GHz | Admin 80 |
| cavespace-endeavour | WPA3 preferred; transition mode only for required compatibility | 2.4/5 GHz | Work 30 |
| cavespace-orbit | WPA2 PPSK | 2.4/5 GHz | HOME → 40, IOT → 50, GUEST → 60 |

Orbit has three independent passwords. There are no separate IoT or Guest
SSIDs. HomePod, Apple TV and personal Apple devices use HOME. Generic IoT uses
IOT; visitors receive only GUEST. Invalid or fallback passwords must not grant
access to a more trusted network.

Orbit client isolation stays off for Home device communication. Authentication,
radio settings and WLAN isolation are shared across its PPSKs; gateway policies
do not isolate peers within the same VLAN. PPSK requires WPA2 and excludes
6 GHz. Guest-key rotation must reject the old key and revoke existing access.

Home retains local multicast and IPv6 link-local operation for Apple/Thread.
The baseline does not enable routed IPv6 or WAN prefix delegation. Gateway and
inter-zone protections must still cover IPv6. Admin membership does not imply
same-VLAN Apple features or automatic Home discovery.

## Physical network

- The AP uplink uses native Management 90 and tagged 30, 40, 50, 60 and 80.
  It has no Network Override to its own native VLAN.
- Switch management uses a tagged VLAN 90 Network Override. Switch uplinks
  use a different native parking VLAN and only required downstream tags.
- Server access ports use VLAN 70; the labelled wired operator port uses VLAN 80.
- No ordinary wireless or wired clients enter Management 90. Any parking
  network is unrouted, has no DHCP/SSID and uses a collision-checked allocation.

## Access policy

Use one custom trust zone per LAN VLAN, stateful replies and default deny for
unlisted inter-zone initiation. Application authentication and Cilium host/pod
policies remain necessary within Servers.

| Source | Permitted initiation | Boundaries |
| --- | --- | --- |
| Work | Internet and required gateway services | All other LAN zones and gateway administration denied |
| Home | Internet, selected Servers services and required IoT services | No general access to other zones or administration |
| IoT | Internet and required gateway services | Private zones denied; explicit integration callbacks only |
| Guest | Internet and selected Home AirPlay receivers | All other private access denied, including general Home access |
| Servers | Internet, Management collection and explicit HA-to-IoT services | No general client access; no implicit reverse Management permission |
| Admin | Internet, Servers ANY, Management ANY and gateway administration | Work/Guest denied; Home/IoT only where operationally required |
| Management | Required updates, NTP, vendor and controller services | No general access to clients or Servers; explicit telemetry destinations only |
| Admin VPN | Admin-equivalent permissions enforced in the VPN zone | Work/Guest denied; tunnel routes do not grant access |

Admin authorization comes from VLAN 80 membership, not the MacBook's IP.
The monitoring baseline permits Servers→Management ANY as an explicit exception
until collector protocols are defined. Record its owner and review milestone;
replace it with named sources/services. Management→Servers telemetry requires
separate receiver/service rules.

### Gateway and WAN management

Gateway-owned addresses belong to the built-in Gateway zone. Configure explicit
Admin→Gateway administration and Houston→Gateway HTTPS/API access; neither is
provided by a Management-zone allow. Work/Home/IoT/Guest cannot administer the
gateway or access the WAN-side ONT management destination.

Permit required DHCP, DNS, NTP and controller services without granting gateway
administration. Preserve required inform/STUN traffic where used. Applicable
denies and gateway guards cover IPv4 and IPv6, including link-local endpoints.
Disable UPnP/NAT-PMP and public application forwarding; retain WAN/LEOX SNAT.

### AirPlay, Home Assistant and monitoring

- Selected Home receivers have reservations and belong to `AIRPLAY_DEVICES`.
  Guest access is limited to this group with stateful replies. Receiver access
  settings must permit visitors; required ports are confirmed from working
  sessions rather than invented in advance.
- UniFi mDNS uses Custom scope for Home 40 and Guest 60, forwarding AirPlay
  services including `_airplay._tcp` and `_raop._tcp`. No global relay is allowed.
  Native filtering selects services/networks, not individual receiver IPs;
  `AIRPLAY_DEVICES` limits routed access, not advertisement visibility.
- Home can reach HA TCP 8123. HA-to-IoT commands and IoT callbacks use named
  integration destinations/services. No default IoT/Servers/Home mDNS or SSDP
  relay is included. Cross-VLAN Matter requires a separate design.
- HA host rules also cover other processes or SNATed workloads on that node;
  they do not provide process-specific isolation. Retain Cilium protection.
- Monitoring collection flows Servers→Management. Push-based syslog/telemetry
  names an explicit Servers receiver and service.

## Terraform design

```text
terraform/unifi/
  backend.tf, providers.tf, main.tf, variables.tf, outputs.tf
  variables.tfvars.json.example, README.md, .terraform.lock.hcl
terraform/modules/unifi/
  providers.tf, networks.tf, wifi.tf, firewall.tf, groups.tf
  devices.tf, dns.tf, vpn.tf, variables.tf, outputs.tf
infra/unifi/
  README.md
  docs/provider-exceptions.md
  docs/wan-netia.md
  scripts/leox-management.sh
```

The UniFi root configures the backend/provider and calls `../modules/unifi`
with typed network, WLAN, device/port, reservation, service-group and VPN inputs.
Pin `ubiquiti-community/unifi = 0.57.0` and Terraform `~> 1.16.4`. Keep the
Cloudflare R2 root separate. WAN/PPPoE and LEOX resources remain unowned.

Use `unifi_firewall_zone.network_ids` as the single owner of zone membership.
Define explicit ALLOW and reverse RESPOND_ONLY policies with
`create_allow_respond = false`; reverse service ports are source-port matches.
Verify effective policy ordering on the installed controller: the provider's
policy index is read-only. Validate dual-family rule coverage against its schema.

Unsupported settings, including Custom Home/Guest mDNS where necessary, belong
in an English provider-exception register with exact desired settings, ownership
and a recheck requirement after provisioning/upgrades.

### State, secrets and execution

- Use Garage state key `prod/unifi/terraform.tfstate` on Houston. Preserve the
  existing R2 state key, loopback backend and Terraform wrapper/process lock.
  Serialize plan/apply sessions and include UniFi state in private R2 backups.
- Production plans/applies run deliberately on Houston. Public CI performs
  backend-disabled init/validate without controller credentials. Existing R2
  automatic apply does not manage UniFi.
- The recommended secret loader is an ignored, operator-owned mode-0600 JSON
  file in a mode-0700 directory, populated from a password manager. Confirm
  this mechanism in the Terraform foundation PR.
- HOME/IOT/GUEST use a sensitive PPSK map. PPSK values persist in state and
  cannot be ephemeral. Protect state, saved plans, exports and backups as
  secret material; sensitive marking does not encrypt them.
- Apollo/Endeavour use ephemeral sensitive inputs and `passphrase_wo` where
  supported. Its lack of a rotation-version trigger requires a documented
  WLAN update/reconnection strategy.
- Controller TLS remains verified. WireGuard client private keys stay on
  clients; Terraform receives public peer keys. Server keys/profiles are private.

## Sequential implementation PRs

Open one PR at a time from the latest merged `main`. Merge, deploy and verify
its scope before opening the next. Repository documentation, comments and PR
descriptions are English. Each implementation PR defines deployment, validation
and rollback for its own changes.

| PR | Scope | Acceptance |
| --- | --- | --- |
| 01 | Target architecture and implementation plan | Agreed networks, SSIDs, trust boundaries and delivery sequence |
| 02 | Isolated UniFi root/module, provider, backend, secrets and CI | Credential-free CI; isolated state and secure production inputs |
| 03 | Terraform ownership of existing LAN objects | Reviewed imports and a no-change plan; WAN excluded |
| 04 | VLAN networks, DHCP/reservations and tagged paths | Correct address, gateway, DNS and tag path on every VLAN |
| 05 | Cilium administration and application policies | Admin, HA and cluster paths enforced without unnecessary Management access |
| 06 | Apollo and wired Admin access | VLAN-based administration reaches Servers, Management and Gateway |
| 07 | Orbit PPSK and Endeavour | Exactly three SSIDs; correct password-to-VLAN mapping and compatibility |
| 08 | Stateful trust zones and Gateway protection | Positive/negative access matrix, IPv6 and ONT boundaries pass |
| 09 | Admin-only gateway WireGuard | External access, DNS, zone restrictions and peer revocation pass |
| 10 | Guest AirPlay and HA integration services | Routed playback to selected receivers; explicit integration traffic |
| 11 | Home, Work, IoT and Guest membership | Correct network placement and required client functions |
| 12 | Infrastructure management on VLAN 90 | Switch/AP adoption, trunks and WLANs remain functional |
| 13 | Houston on Servers VLAN 70 | SSH, Garage, state locking/backups, runner and controller API work |
| 14 | Worker on Servers VLAN 70 | Same node identity, Ready/Cilium, PVC data and HA functions |
| 15 | Control plane on Servers VLAN 70 | Stable etcd/API endpoints, both nodes Ready and application data intact |
| 16 | Remove obsolete network objects and permissions | Final architecture, no broad legacy access, accepted exceptions and no-change plans |

Trusted pilots validate new networks before Work/IoT/Guest production membership.
Admin and the wired operator path precede restrictive policy changes. Client
membership and retirement of untagged WLANs precede the AP's native Management
cutover. Prepare required tags before device moves. Houston's move uses an
independent operator path; move the worker before the control plane. Live NAS
or other storage dependencies need their own migration PRs before final cleanup.

Before disruptive changes, verify private UniFi/Talos/etcd/PVC/state backups,
restore procedures, local access and current node/storage health. Preserve
existing paths until replacements pass. Reapply recorded device/network settings
for rollback; resetting nodes, deleting PVCs or restoring Terraform state is not
routine network rollback. Plan a maintenance window for the single control plane.

## Acceptance criteria

- Exactly seven LAN trust zones and three SSIDs with correct PPSK placement.
- Work/IoT/Guest isolation and stateful replies match the access matrix.
- MacBook administration works from Apollo and the wired Admin port without
  IP-specific authorization or local VPN use.
- Home Apple functions and actual routed Guest AirPlay work; discovery alone
  or peer-to-peer playback is not sufficient evidence.
- HA integrations work with explicit rules; Home, IoT and Guest do not receive
  general Servers or Management access.
- Houston backend/runner/API access, Talos identities, both nodes, storage and
  required private services remain healthy. No public application exposure.
- Management devices remain adopted and manageable; reverse telemetry is scoped.
- Gateway/ONT protection covers prohibited sources and IPv6/link-local paths.
- WAN/GPON and LEOX management remain functional and unchanged.
- Private backups and reviewed no-change plans exist. Test prohibited access
  against known-listening targets with fresh sessions and correlated flow evidence.

Provider ordering, DHCP/reservations, LoadBalancer/VPN allocations, WPA3 client
compatibility, receiver selection and integration/monitoring ports are confirmed
in their implementation PRs. A collision or unsupported capability requires an
explicit design revision rather than an undocumented exception.

## References

- [UniFi infrastructure](../../../infra/unifi/README.md)
- [Terraform backend](../../../terraform/BACKEND.md)
- [Private state backups](../../../terraform/R2_BACKUP.md)
- [Houston operations](../../../infra/ansible/README.md)
- [Provider v0.57.0](https://github.com/ubiquiti-community/terraform-provider-unifi/releases/tag/v0.57.0)
- [UniFi PPSK](https://help.ui.com/hc/en-us/articles/29887064407319-Using-PPSK-RADIUS-for-Multiple-VLANs-On-an-SSID-in-UniFi-Network)
- [UniFi zone-based firewall](https://help.ui.com/hc/en-us/articles/115003173168-Zone-Based-Firewalls-in-UniFi)
- [UniFi mDNS](https://help.ui.com/hc/en-us/articles/12648701398807-UniFi-Gateway-Multicast-DNS-mDNS-Proxy)
- [Apple AirPlay](https://support.apple.com/en-gb/guide/deployment/-dep9151c4ace/web)
- [HomePod networking](https://support.apple.com/en-gb/guide/homepod/apdfb81a72e4/homepod)
