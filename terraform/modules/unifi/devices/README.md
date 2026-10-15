# UniFi devices

Assign profiles to declared ports on adopted devices, with one resource per MAC.
`management_network` selects a tagged Network Override; allow that VLAN along
the uplink path first. Native management uses no override. Omitting
`management_network` does not clear an existing override; clear it in UniFi.
Other ports stay outside this module's scope.
Declared port entries are replaced; include all required overrides for those ports.
Removing a port declaration stops managing it without resetting it.
Devices have `prevent_destroy`; adoption and forgetting are disabled.
Declared ports use auto-negotiation. Set `poe_mode` explicitly on powered uplinks.
