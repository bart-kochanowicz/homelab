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

The wired Admin port is USW Flex 2.5G 5 port 1. AP/QoS defaults are read-only.
Local `terraform.tfvars` supplies `wifi_passphrases` (Apollo/Endeavour) and
`wifi_ppsks` (`orbit/home`, `orbit/iot`, `orbit/guest`). Actions uses private
`UNIFI_WIFI_PASSPHRASES` and `UNIFI_WIFI_PPSKS` secrets respectively.
WPA3 passphrases are ephemeral/write-only; PPSKs persist in private plans,
state and backups. Orbit defaults to Guest and has client isolation disabled.

- [Plan and apply](../README.md#plan-and-apply)
- [Local plans](../LOCAL_PLAN.md) and [controller certificate](CERTIFICATE.md)
- [Provider constraints](../../infra/unifi/docs/provider-exceptions.md)
