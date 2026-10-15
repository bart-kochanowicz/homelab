# UniFi

[networks.tf](networks.tf) declares LANs and port profiles. [main.tf](main.tf)
connects the [network and port-profile modules](../modules/unifi/). Resources have
`prevent_destroy`; DHCP advertises the gateway as DNS.
The built-in `Default` LAN is read-only; `default_network_id` exposes its ID.
Managed subnets and names must not conflict with `Default`.
`network_ids` and `port_profile_ids` expose IDs keyed by logical name.

Custom profiles exclude every LAN outside their native/tagged set. Declare all
LAN IDs in `network_ids` or `reserved_network_ids` and re-plan when adding one.
Port profile creation does not assign profiles to physical ports.

| SSID | Security | Bands | VLAN |
| --- | --- | --- | --- |
| `cavespace-apollo` | WPA3 | 5 GHz | Admin 80 |
| `cavespace-endeavour` | WPA3 | 2.4/5 GHz | Work 30 |
| `cavespace-orbit` | WPA2 PPSK | 2.4/5 GHz | HOME 40, IOT 50, GUEST 60 |

The wired Admin port is USW Flex 2.5G 5 port 1. AP/QoS groups are read-only.
The unmanaged switch for Apple TV and LG TV uses Home on UCG-Fiber `voyager-01` port 2.
Both switches use tagged Management 90. U7 Lite uses native Management 90 on
`voyager-01` port 4, with no AP Network Override; client VLANs stay tagged.
Houston uses native Servers 70 on Flex 8 port 1, with DHCP reservation `10.0.70.10`.
Supply `infrastructure_macs` through ignored `terraform.tfvars`; Actions uses
the JSON map `UNIFI_INFRASTRUCTURE_MACS`. UniFi device IDs equal their MACs and
remain visible in import diagnostics and protected state.
Local `terraform.tfvars` supplies `wifi_passphrases` (Apollo/Endeavour) and
`wifi_ppsks` (`orbit/home`, `orbit/iot`, `orbit/guest`). Actions uses private
`UNIFI_WIFI_PASSPHRASES` and `UNIFI_WIFI_PPSKS` secrets respectively.
WPA3 passphrases are ephemeral/write-only; PPSKs persist in private plans,
state and backups. Orbit uses explicit per-key VLANs and has client isolation
disabled; the controller stores Default as its base network metadata.

[firewall.tf](firewall.tf) declares one trust zone per routed LAN, gateway services
and the access matrix. Unlisted traffic between zones is denied for IPv4/IPv6;
same-VLAN traffic requires endpoint protection. Server rules follow registered
client MACs. Declared server reservations supply authoritative addresses and zones;
other servers use UniFi's reported membership and reservation/address. Renew leases
after reservation changes and re-plan after address or membership changes. WAN exposure settings
and site mDNS belong to the [administrator](../../infra/unifi/docs/provider-exceptions.md).
Check `firewall_policy_order`: allowances/replies must precede denies; the
provider cannot reorder existing rules. See the [firewall module](../modules/unifi/firewall/).

Guest has Internet access and required gateway services only; site mDNS proxy is disabled.

[vpn.tf](vpn.tf) declares `cavespace-wormhole`: WireGuard on WAN1 UDP 51820,
`10.0.100.0/24`, in UniFi's built-in VPN zone. Explicit rules grant this pool
Admin permissions; clients use split routes to administrative destinations.
UniFi owns VPN membership and its WAN handshake rule. The WireGuard provider
derives the server public key from its existing private key.
Server private keys persist in protected state/backups; device private keys stay
on their devices. Add/revoke peers through `vpn_peers` and reviewed apply.

Supply `vpn_public_ip` and `vpn_peer_public_keys` through ignored `terraform.tfvars`
locally. Actions uses `UNIFI_VPN_PUBLIC_IP` and the JSON map
`UNIFI_VPN_PEER_PUBLIC_KEYS`. Client settings include the WAN endpoint; retrieve
them locally and retain the device's existing `PrivateKey`:

```bash
terraform output -json wireguard_clients | jq -r '."macbook-01"'
```

Network policies require manual ArgoCD sync. Test VPN access from an external
network, with other VPNs disabled; validate coexistence separately. Re-read client
settings after registered server address changes.

- [Plan and apply](../README.md#plan-and-apply)
- [Local plans](../LOCAL_PLAN.md) and [controller certificate](CERTIFICATE.md)
- [Provider constraints](../../infra/unifi/docs/provider-exceptions.md)
