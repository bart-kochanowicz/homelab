# UniFi

[networks.tf](networks.tf) declares LANs and port profiles; [the module](../modules/unifi/)
creates them with `prevent_destroy`. DHCP advertises the gateway as DNS.
The built-in `Default` LAN is read-only; `default_network_id` exposes its ID.
Managed subnets and names must not conflict with `Default`.
`network_ids` and `port_profile_ids` expose IDs keyed by logical name.

Custom profiles exclude every LAN outside their native/tagged set. Declare all
LANs in the module or its `reserved_networks` input and re-plan when adding one.
Port profile creation does not assign profiles to physical ports.

- [Plan and apply](../README.md#plan-and-apply)
- [Local plans](../LOCAL_PLAN.md) and [controller certificate](CERTIFICATE.md)
- [Provider constraints](../../infra/unifi/docs/provider-exceptions.md)
