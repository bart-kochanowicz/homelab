# Firewall

Custom zones own network membership. `rules` declares permitted initiation;
the module creates explicit stateful replies and dual-family denies for every
zone pair involving a managed zone or `guarded_builtin_zones`. Traffic within
a VLAN is not filtered. Guard the built-in VPN zone to override its broad defaults.
`client_ipv4_addresses` resolves client destinations (including replies) to IPs;
UniFi accepts `CLIENT` only on sources. Address mappings must stay current.
Use separate ICMP/ICMPv6 `RELATED` allowances for connection errors; TCP/UDP
reply port filters cannot match these packets.

Allowances/replies must precede denies. Creation dependencies order the first
apply; the provider cannot reorder existing policies. Newly created allowances
can require UI reordering above existing denies. `policy_order` rejects an order
that shadows allowances or replies; re-plan after correcting the order.
Custom denies must also precede built-in policies (`builtin_policy_index`,
default `30000`); recheck the boundary after controller upgrades.
