# UniFi provider constraints

These settings depend on UniFi API behavior or sit outside Terraform ownership.
Review them after provider/controller upgrades, especially policy ordering,
network overrides, write-only credentials and administrator-managed settings.

| Object | Constraint | Owner |
| --- | --- | --- |
| Built-in `Default` LAN | Read-only `data.unifi_network.default`; provider `enabled=false` does not describe LAN availability. | Administrator |
| Port profile tags | The provider omits `tagged_networkconf_ids`. Custom trunks use `excluded_networkconf_ids` for every LAN outside the native/tagged set. | Terraform |
| Unrouted VLAN DHCP | Omit `dhcp_server`. Provider defaults otherwise differ from the controller response and cause an inconsistent apply result. | Terraform |
| WPA3 passphrases | `passphrase_wo` has no rotation-version field. A password-only edit produces no diff; rotate it together with a reviewed WLAN change. | Terraform |
| PPSK base network | UCG-Fiber stores the built-in Default LAN as `network_id`. Each key explicitly selects its managed VLAN; there is no base passphrase. | Terraform |
| PPSK passwords | No write-only API field; passwords remain in private plans, state and backups. | Terraform |
| Device ports | Declared overrides replace each port entry. Undeclared ports are preserved, but the provider sends the complete override array. | Terraform |
| Firewall order | Policy indices are read-only. Allow/reply rules must sit above their zone-pair denies; new rules may need manual reordering. | Administrator |
| Firewall client targets | Network 10.6.106 rejects `CLIENT` destinations. Rules use `CLIENT` sources and explicit destination IPv4 addresses, including replies. | Terraform |
| WireGuard zone | Network 10.6.106 keeps the server network in built-in `Vpn`. Rules scope access to the VPN pool and override built-in permissions. | Terraform / controller |
| WireGuard server key | If UniFi omits `wireguard_public_key`, derive it from the existing private key with `OJFord/wireguard`. Both copies remain in protected state. | Terraform / controller |
| Site mDNS | No provider setting; the proxy is disabled and discovery stays within each VLAN. | Administrator |
| WAN | UPnP/NAT-PMP disabled; no public application forwarding. PPPoE and LEOX route/SNAT are outside this root. | Administrator |
