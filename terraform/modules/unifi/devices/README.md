# UniFi device ports

Assign profiles to declared ports on adopted devices, with one resource per MAC.
Other ports and device management settings stay outside this module's scope.
Declared port entries are replaced; use dedicated access ports without unrelated
overrides. Removing a port declaration stops managing it without resetting it.
Devices have `prevent_destroy`; adoption and forgetting are disabled.
