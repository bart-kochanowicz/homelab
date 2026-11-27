# UniFi WiFi

WPA2/WPA3 SSIDs use managed network IDs and existing AP/QoS groups. AP uplinks
must carry the WLAN VLANs. Each SSID has one ephemeral, write-only passphrase.
The provider sends `passphrase_wo` only on create or when a WLAN's
`passphrase_version` changes. Leave it unset until the first rotation, then
set it to 1 and increment it on each later rotation.
