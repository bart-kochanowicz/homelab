# DHCP reservations

Reserve IPv4 addresses outside each network's dynamic pool by default. Set
`allow_dynamic_pool = true` on a reservation to retain an existing address inside
the pool. Import existing clients by MAC. Forgetting is disabled: destroying a
reservation only removes it from state, and the client keeps its fixed IP in
UniFi until it is cleared there.
VLAN membership belongs to the switch port or Wi-Fi configuration, not
`unifi_client.network_id`.
