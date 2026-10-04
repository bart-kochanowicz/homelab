# Cavespace Network Inventory

Observed on 2026-10-04 using the authenticated UniFi UI, SSH to Houston, and
existing Kubernetes/Talos clients. This is a partial current-state inventory;
the [target architecture](../../../thoughts/shared/plans/2026-10-04-cavespace-unifi-baseline.md)
has not been applied. Repository configuration, operator reports, and live
observations are identified separately below.

## Live network infrastructure

| Device | Current IPv4 | Observed upstream | Status / version |
| --- | --- | --- | --- |
| UCG-Fiber, `voyager-01` | 192.168.1.1 | Netia WAN1, gateway port 7, GbE | Online; device 5.1.33; Network 10.6.106 |
| USW Flex 2.5G 5 | 192.168.1.55 | Gateway port 1, 2.5 GbE | Online; firmware pending |
| USW Flex 2.5G 8 | 192.168.1.210 | Five-port switch port 3, 2.5 GbE | Online; firmware pending |
| U7 Lite | 192.168.1.186 | Gateway port 4, 2.5 GbE | Online; firmware pending |

U7 Lite is directly attached to the gateway. The switches are cascaded.
Physical labels, downstream uplink port numbers, PoE dependencies, complete
port overrides, and native/tagged VLAN settings still need verification.
The UI's `Default` network label alone does not prove an allowed-tag list.
Retain device IDs, MAC addresses and exports in private recovery material.

| Setting | Live observation |
| --- | --- |
| Controller / site path | `https://192.168.1.1/network/default`; authenticated UI available |
| LAN | One listed network, `Default`, 192.168.1.0/24; gateway 192.168.1.1 |
| DHCP | Server; auto-scale enabled; range 192.168.1.6–192.168.1.254; lease 86400 seconds |
| DNS / DHCP gateway | Automatic; DHCP domain `localdomain` |
| Default security posture | Allow All |
| Gateway mDNS Proxy | Auto |
| Default LAN IPv6 | Interface Type None; no IPv6 subnet shown |
| Host IPv6 | Houston has ULA and link-local addresses; local IPv6 still needs policy tests |
| Legacy WLAN | `solor-system-temp` (observed spelling); six associated clients on 5 GHz at observation time |
| WAN | Netia WAN1 Online; displayed 24-hour Internet uptime 100% and SLA checks Passing |

SSID authentication, client isolation, reservations, firewall rules, static
routes, VPNs, public forwarding and UPnP/NAT-PMP remain unverified. A reachable
browser session does not verify certificate trust or Terraform API authentication
from Houston. Version thresholds for ZBF are met; effective rule precedence,
provider compatibility and PPSK behavior still need staged tests.

## Hosts and applications

| Item | Evidence | Current conclusion |
| --- | --- | --- |
| Houston | SSH: hostname `houston-01`, enp1s0 192.168.1.165/24, default route via 192.168.1.1 | Reachable on the legacy LAN; physical switch port pending |
| Houston runtime | Terraform 1.16.4; `/srv/terraform` mounted on ext4; Garage and runner services active; S3 listening on 127.0.0.1:3900 | Backend host available; state contents and recovery not tested here |
| Houston permissions | Private operator directory 0700 `capcom:capcom`; Terraform lock 0660 `root:terraform-ops` | Expected permissions observed; no lock contention test performed |
| Garage version | Tracked deployment pins 2.4.1; runtime version command denied for operator account | Runtime version unverified |
| Kubernetes | Local `homelab-prod` kubeconfig points to 192.168.100.86:6443; read-only request timed out | Stale/unreachable endpoint; cluster health unknown |
| Candidate node at 192.168.1.217 | UniFi: eight-port switch port 7, GbE; Talos TCP 50000 and Kubernetes TCP 6443 refused connections | Identity and node role unverified; refusal does not prove worker role |
| Unidentified wired client reported by operator | UniFi: eight-port switch port 8, GbE, IPv4 Unknown, IPv6 link-local present | No confirmed Talos identity or role; private MAC mapping retained outside Git |
| Talos version | Local client v1.11.1; no server version returned | Installed node versions pending |
| Operator-reported node displays | Control plane shows 192.168.100.1; worker shows 192.168.1.1; displayed field/source not yet identified | Neither is accepted as a node address: 192.168.1.1 is the live UCG LAN address and 192.168.100.1 is the documented LEOX address |
| Home Assistant | Tracked Deployment uses hostNetwork, Recreate and a local-path PVC; no node selector | Actual running node, PV affinity, integrations and data unverified |
| Apple receivers | UI shows two HomePod mini clients and one wired Apple TV client; Apple TV on gateway port 2 | Selection, IP reservations and receiver access settings pending |
| Monitoring | Prometheus/Grafana manifests tracked | Live collectors, targets and management protocols pending |
| NAS / other servers | No confirmed server/storage inventory | Operator must classify as live or future-only; add migration PRs for live dependencies |

Keep node names, role evidence, Talos addresses, PV node/path/affinity and
application health together in the private inventory. UniFi model detection
is a heuristic and cannot establish a Kubernetes role.

Clarify whether the reported displays show interface addresses, default
gateways or cluster endpoints. If they are actual node interface addresses,
resolve the duplicate/overlapping addressing through a separately reviewed
recovery procedure before continuing. Do not repoint kubeconfig or assign the
candidate 192.168.1.217 a role based on these reports.

## Address and recovery gates

Target VLANs 30/40/50/60/70/80/90 and `10.0.<VLAN>.0/24` are proposals awaiting
collision checks. The current LAN and Houston route table contain no overlapping
target route, but that is only partial evidence. Employer VPN routes, gateway
routes/VPNs, live pod/service CIDRs, and every other host reservation remain
pending. Do not freeze DHCP, media, VPN or future LoadBalancer allocations yet.

The tracked WAN guide uses 192.168.100.2/24, while the tracked LEOX script uses
192.168.100.2/32 with a host route and SNAT. Legacy Talos configuration also
references 192.168.100.x. Runtime ONT routes/SNAT/O5 and operator-to-LEOX access
were not verified. Preserve the working WAN; do not run/reinstall the script
or reuse ONT space as a new LAN to resolve this discrepancy.

| Required evidence before PR 02 | Status |
| --- | --- |
| Full route/CIDR/reservation conflict review and accepted allocation map | Pending |
| Node identity, current authenticated API connectivity and cluster health | Pending |
| HA placement/PVC affinity, integration endpoints and live storage dependencies | Pending |
| Switch/AP firmware and complete port/profile/override inventory | Pending |
| Current rules, forwarding, VPNs, WLAN settings and receiver inventory | Pending |
| Houston-to-controller trusted TLS, API credential procedure and private site/object IDs | Pending |
| Labelled wired recovery path, local gateway/node access and operator rehearsal | Pending |
| Private UniFi backup, etcd snapshot, PVC backup and restore evidence | Pending; June verification is historical evidence only |
| WAN/LEOX runtime baseline and restricted-client ONT protection test design | Pending |
| Accepted reservations and private secret-loading procedure | Pending; recommendations remain in the plan |

PR 01 remains a draft until these gates are resolved. See the
[runbook](network-runbook.md) for evidence collection and recovery boundaries,
and the [verification ledger](../../../docs/security-verification.md) for dated
results. No state export, secret, public WAN address or device backup belongs
in this document.
