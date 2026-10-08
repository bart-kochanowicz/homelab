# UniFi networks

Routed LANs with gateway CIDRs and optional DHCP, plus unrouted VLAN-only networks.
Map keys are stable resource identifiers. Subnets and VLANs cannot overlap;
DHCP pools exclude gateways. Networks have `prevent_destroy`.
Provider configuration belongs to the caller.
