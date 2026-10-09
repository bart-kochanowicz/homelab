# UniFi WiFi

WPA3 SSIDs and WPA2 PPSK SSIDs use managed network IDs and existing AP/QoS groups.
WPA3 passphrases are ephemeral/write-only; PPSKs persist in private plans and
state. `ppsk_wlans` binds each role explicitly to a managed network. The
controller requires the read-only Default LAN ID for PPSK base metadata; client
VLANs come from the per-key bindings. No base passphrase is configured.
PPSK passwords must be distinct within an SSID.
PPSK supports 2.4/5 GHz; client isolation is disabled for shared Home/IoT use.
WLANs have `prevent_destroy`; AP uplinks must carry their network VLANs.
Provider 0.57.0 does not detect write-only passphrase changes alone; rotate them
with a reviewed WLAN update. PPSK changes produce a plan; verify old-key and
connected-client revocation on the controller when rotating Guest access.
