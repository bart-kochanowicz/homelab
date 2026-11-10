# UniFi Infrastructure

UCG-Fiber network architecture and WAN configuration. Terraform layout:
[`terraform/unifi`](../../terraform/unifi) with reusable modules under
[`terraform/modules/unifi`](../../terraform/modules/unifi).

## Networks

Each network uses the `cavespace-` prefix and gateway `10.0.<VLAN>.1`.

| VLAN | Name | Subnet | Role |
| --- | --- | --- | --- |
| 30 | endeavour | 10.0.30.0/24 | Work devices |
| 40 | orbit | 10.0.40.0/24 | Personal devices and trusted Apple/HomeKit devices |
| 50 | stardust | 10.0.50.0/24 | Untrusted IoT |
| 70 | launchpad | 10.0.70.0/24 | Houston, Talos, Kubernetes, storage and Home Assistant |
| 80 | apollo | 10.0.80.0/24 | Administrator devices |
| 90 | mission-control | 10.0.90.0/24 | Network infrastructure management |

DHCP uses `.100`–`.199`, a 24-hour lease and the VLAN gateway for DNS.
Servers addresses: Houston `10.0.70.10`, control plane `10.0.70.11`, worker
`10.0.70.12`; `.200`–`.219` is reserved for service LoadBalancer addresses.

Port profiles use the `cavespace-` prefix:

| Profile | Native network | Tagged VLANs |
| --- | --- | --- |
| `access-<network>` | Named LAN | None |
| `ap` | Management 90 | 30, 40, 50, 80 |
| `switch-trunk` | Parking 999 | 50, 70, 80, 90 |
| `access-parking` | Parking 999 | None |

`cavespace-parking` (999) has no gateway, DHCP or SSID. Switch management uses
tagged VLAN 90; AP management uses native VLAN 90 without a Network Override.
Switch uplinks use `switch-trunk`; unused LAN ports use `access-parking`.
Flex 8 port 2 is an untagged IoT access port for SONOFF Dongle Max.

Four SSIDs: `cavespace-apollo` (80), `cavespace-endeavour` (30), and
`cavespace-orbit` (40) require WPA3. `cavespace-stardust` uses WPA2-AES,
2.4 GHz, VLAN 50. No Wi-Fi guest access is configured.

Inter-zone access is denied by default, with stateful replies and explicit service
exceptions. Admin has access to Servers, Management and gateway administration;
remote administration uses `cavespace-wormhole` WireGuard (`10.0.100.0/24`),
in the built-in VPN zone with scoped Admin permissions and split routing.
mDNS proxy is disabled.
Home Assistant runs in
Servers; IoT has no access to it without an explicit integration rule. Application endpoints are private.

The WAN uses Netia GPON through LEOX LXT-010S-H, VLAN 35 and PPPoE.
LEOX management uses a WAN-side route and SNAT.

## WAN support

- [Netia GPON WAN](docs/wan-netia.md)
- [LEOX runtime support](scripts/leox-management.sh)
