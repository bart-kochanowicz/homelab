# UniFi WiFi

WPA3-only SSIDs use managed network IDs and existing AP/QoS groups.
Passphrases are ephemeral and write-only; supply them for plan and saved-plan
apply. Provider 0.57.0 does not detect passphrase-only changes.
WLANs have `prevent_destroy`; AP uplinks must carry their network VLANs.
