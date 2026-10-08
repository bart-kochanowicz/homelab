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
| 60 | comet | 10.0.60.0/24 | Guests |
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
| `ap` | Management 90 | 30, 40, 50, 60, 80 |
| `servers-trunk` | Parking 999 | 70, 90 |

`cavespace-parking` (999) has no gateway, DHCP or SSID. Switch management uses
tagged VLAN 90; AP management uses native VLAN 90 without a Network Override.

Three SSIDs: `cavespace-apollo` (80), `cavespace-endeavour` (30), and
`cavespace-orbit` (WPA2 PPSK: HOME → 40, IOT → 50, GUEST → 60).

Inter-zone access is denied by default, with stateful replies and explicit service
exceptions. Admin has access to Servers, Management and gateway administration;
remote administration uses WireGuard. Guest AirPlay is limited to selected Home
receivers, with AirPlay mDNS scoped to Home and Guest. Home Assistant runs in
Servers with explicit IoT integration rules. Application endpoints are private.

The WAN uses Netia GPON through LEOX LXT-010S-H, VLAN 35 and PPPoE.
LEOX management uses a WAN-side route and SNAT.

## WAN support

- [Netia GPON WAN](docs/wan-netia.md)
- [LEOX runtime support](scripts/leox-management.sh)
