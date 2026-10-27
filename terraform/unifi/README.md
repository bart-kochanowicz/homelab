# UniFi

Terraform configures the UCG-Fiber LANs and adopted switches/AP. See the
[network layout](../../infra/unifi/README.md) for VLANs and subnets.

| File | Configuration |
| --- | --- |
| [networks.tf](networks.tf) | LANs and port profiles |
| [devices.tf](devices.tf) | Switch/AP ports |
| [reservations.tf](reservations.tf) | Server addresses |
| [dns.tf](dns.tf) | Private A/SRV records |
| [wifi.tf](wifi.tf) | SSIDs and per-key VLANs |
| [firewall.tf](firewall.tf) | Trust zones and allowed traffic |
| [vpn.tf](vpn.tf) | WireGuard server and peers |

## LANs and ports

DHCP advertises the VLAN gateway as DNS. Networks, profiles, devices and WLANs
have deletion protection. The built-in `Default` LAN and AP/QoS groups are
read-only; managed names/subnets must not overlap Default. Outputs expose
network/profile IDs by logical name.

Trunks exclude every LAN outside their native/tagged set. Include all LANs in
`network_ids` or `reserved_network_ids` when adding a network.

| Device / port | Connection | Network |
| --- | --- | --- |
| Flex 5 / 1–2 | Admin devices | Admin 80 |
| Flex 8 / 1 | Houston, `10.0.70.10` | Servers 70 |
| Flex 8 / 7 | Worker, `10.0.70.12` | Servers 70 |
| Flex 8 / 8 | Control plane, `10.0.70.11` | Servers 70 |
| Voyager / 2 | Apple TV / LG TV switch | Home 40 |
| Voyager / 4 | U7 Lite | Native Management 90, tagged client VLANs |
| Voyager / 1 ↔ Flex 5 / 5 | Uplink | Native Parking 999, tagged 70/80/90 |
| Flex 5 / 3 ↔ Flex 8 / 9 | Uplink | Native Parking 999, tagged 70/80/90 |

Switch management is tagged on VLAN 90. AP management is native VLAN 90 without
a Network Override. Unused ports use Parking with no tags; Voyager WAN port 7
is unmanaged.

## Wi-Fi and DNS

| SSID | Security | Bands | VLAN |
| --- | --- | --- | --- |
| `cavespace-apollo` | WPA3 | 5 GHz | Admin 80 |
| `cavespace-endeavour` | WPA3 | 2.4/5 GHz | Work 30 |
| `cavespace-orbit` | WPA2 PPSK | 2.4/5 GHz | HOME 40, IOT 50, GUEST 60 |

Orbit keys select individual VLANs. Client isolation is disabled; Default is
the WLAN's base metadata. WPA3 passphrases are write-only; PPSKs remain in
private plans, state and backups. Site mDNS proxy is disabled.

HA resolves to the Home VIP; administrative panels resolve to the Admin VIP.
`ha-backend.thecavespace.net` resolves to the worker for HTTPS on `8123`;
Minecraft A/SRV records select that worker on `30000`. Router and Cilium rules
enforce access. Public DNS and ACME challenge records are outside this root.

## Firewall and VPN

Each LAN has a trust zone. Rules allow specific connections and stateful replies;
other inter-zone IPv4/IPv6 traffic is denied. Same-VLAN traffic bypasses this
firewall. Server rules follow reservation MACs/addresses; renew leases after
changes. Cilium controls Kubernetes traffic. Guest has Internet and required
gateway services only.

Allow/reply rules must precede denies. `firewall_policy_order` checks indices;
the provider cannot reorder existing rules. Correct the order in UniFi when
needed. See [provider constraints](../../infra/unifi/docs/provider-exceptions.md).

`cavespace-wormhole` uses WAN1 UDP `51820`, pool `10.0.100.0/24` and the built-in
VPN zone. Clients have Admin access through split routes; ordinary Internet
traffic stays outside the tunnel. UniFi owns the handshake rule and VPN zone
membership. WAN/PPPoE, LEOX and mDNS are administrator-managed.

The server listens on `any` so startup does not require the PPPoE address to
exist yet. Client settings still advertise `vpn_public_ip`.

Client private keys stay on devices; server private keys remain in protected
state/backups. Add/revoke `vpn_peers` through [plan and apply](../README.md#plan-and-apply).
Get client settings locally and retain the device's existing `PrivateKey`:

```bash
terraform output -json wireguard_clients | jq -r '."macbook-01"'
```

Settings include the WAN endpoint; refresh them after server address changes.
Test remote access from an external network with other VPNs disabled.

## Private inputs

Local inputs live in ignored `terraform.tfvars`; Actions reads private secrets:

| Input | Actions secret |
| --- | --- |
| `infrastructure_macs` | `UNIFI_INFRASTRUCTURE_MACS` |
| `wifi_passphrases` | `UNIFI_WIFI_PASSPHRASES` |
| `wifi_ppsks` | `UNIFI_WIFI_PPSKS` |
| `vpn_public_ip` | `UNIFI_VPN_PUBLIC_IP` |
| `vpn_peer_public_keys` | `UNIFI_VPN_PEER_PUBLIC_KEYS` |

Device MACs appear in import diagnostics and state. [Local plans](../LOCAL_PLAN.md)
use the [controller certificate](CERTIFICATE.md). Network-policy changes also
need a manual ArgoCD sync.
