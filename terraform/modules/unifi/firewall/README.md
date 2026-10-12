# Firewall

Custom zones own network membership. `rules` declares permitted initiation;
the module creates explicit stateful replies and dual-family denies for every
zone pair involving a managed zone. Traffic within a VLAN is not filtered.
Use separate ICMP/ICMPv6 `RELATED` allowances for connection errors; TCP/UDP
reply port filters cannot match these packets.

Allowances/replies must precede denies. Creation dependencies order the first
apply; provider 0.57.0 cannot reorder existing policies. Newly created allowances
can require UI reordering above existing denies. `policy_order` rejects an order
that shadows allowances or replies; re-plan after correcting the order.
Custom denies must also precede built-in policies (`builtin_policy_index`,
default `30000`); recheck the boundary after controller upgrades.
