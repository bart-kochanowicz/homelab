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

- [Plan and apply](../README.md#plan-and-apply)
- [Local plans](../LOCAL_PLAN.md) and [controller certificate](CERTIFICATE.md)
- [Provider constraints](../../infra/unifi/docs/provider-exceptions.md)
