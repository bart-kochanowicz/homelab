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

`cavespace-apollo` uses WPA3 on 5 GHz and VLAN 80. The wired Admin port is
USW Flex 2.5G 5 port 1. AP groups and QoS defaults are read-only references.
Supply `wifi_passphrases.apollo` in local `terraform.tfvars`; Actions uses the
private `UNIFI_WIFI_PASSPHRASES` secret. Passphrases are ephemeral and write-only.

- [Plan and apply](../README.md#plan-and-apply)
- [Local plans](../LOCAL_PLAN.md) and [controller certificate](CERTIFICATE.md)
- [Provider constraints](../../infra/unifi/docs/provider-exceptions.md)
