# UniFi provider constraints

| Object | Constraint | Owner |
| --- | --- | --- |
| Built-in `Default` LAN | Read-only `data.unifi_network.default`; configuration belongs to the UniFi administrator. Recheck import and round-trip behavior before changing ownership after provider/controller upgrades. | Network administrator |
| Port profile tags | The provider does not serialize `tagged_networkconf_ids`. Use `tagged_vlan_mgmt = "custom"` with `excluded_networkconf_ids` computed from every LAN outside the native/tagged set. Recheck the provider implementation and controller read-back after upgrades. | Terraform |
| Unrouted VLAN DHCP | Omit `dhcp_server` on VLAN-only networks. The provider injects lease/conflict-checking defaults into a configured object, while UniFi omits those fields, causing an inconsistent result after apply. | Terraform |
| WLAN passphrases | `passphrase_wo` has no rotation-version field. A passphrase-only change produces no diff; trigger a reviewed WLAN update when rotating the secret. | Terraform |
| WLAN PPSK base network | UCG-Fiber normalizes PPSK WLAN `network_id` to the built-in Default LAN. Reference its read-only ID and bind every PPSK explicitly to a managed network; do not configure a base passphrase. | Terraform |
| WLAN PPSKs | The provider has no write-only PPSK passwords. Sensitive PPSK values persist in private plans, state and backups. | Terraform |
| Device ports | The provider preserves undeclared port entries but replaces each declared entry and sends the full override array. Use dedicated ports and compare other port settings after apply. | Terraform |
| Firewall order | The provider exposes a read-only policy index. Keep custom allow/reply policies above their zone-pair denies; `firewall_policy_order` enforces this condition. Newly created policies can require UI reordering. Recheck API ordering support after upgrades. | Network administrator |
| Firewall client targets | Network 10.6.106 rejects `CLIENT` destinations despite the provider accepting them. Preserve `CLIENT` sources and resolve destination MACs to explicit IPv4 targets, including reversed replies. Recheck after provider/controller upgrades. | Terraform |
| WireGuard zone | Network 10.6.106 rejects moving the server network out of built-in `Vpn`. Leave membership controller-owned; scope Admin rules to the VPN pool and override built-in permissions with explicit guards. Recheck after upgrades. | Terraform / controller |
| WireGuard server key | The provider returns a null public key when Network omits `wireguard_public_key`. Derive it from the existing server private key using `OJFord/wireguard`; both private-key copies remain in protected state. UniFi owns the WAN handshake rule. | Terraform / controller |
| Site mDNS | The provider does not expose site mDNS proxy settings. Keep the proxy disabled; discovery stays within each VLAN. Recheck support and effective settings after upgrades. | Network administrator |
| WAN exposure | WAN settings are outside root ownership: UPnP/NAT-PMP disabled, no public application forwarding, PPPoE and LEOX route/SNAT preserved. Recheck after WAN configuration changes and provisioning. | Network administrator |

The provider's read-back `enabled=false` on `Default` does not describe LAN
availability. WAN/PPPoE and LEOX management are outside Terraform ownership.
