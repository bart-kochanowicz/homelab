# UniFi provider constraints

| Object | Constraint | Owner |
| --- | --- | --- |
| Built-in `Default` LAN | Read-only `data.unifi_network.default`; configuration belongs to the UniFi administrator. Provider 0.57.0 plans updates for omitted `enabled`, `setting_preference`, and `dhcpd_leasetime` fields after resource import. Recheck round-trip behavior before changing ownership after provider/controller upgrades. | Network administrator |
| Port profile tags | Provider 0.57.0 does not serialize `tagged_networkconf_ids`. Use `tagged_vlan_mgmt = "custom"` with `excluded_networkconf_ids` computed from every LAN outside the native/tagged set. Recheck the provider implementation and controller read-back after upgrades. | Terraform |
| Unrouted VLAN DHCP | Omit `dhcp_server` on VLAN-only networks. Provider 0.57.0 injects lease/conflict-checking defaults into a configured object, while UniFi omits those fields, causing an inconsistent result after apply. | Terraform |
| WLAN passphrases | `passphrase_wo` has no rotation-version field in provider 0.57.0. A passphrase-only change produces no diff; trigger a reviewed WLAN update when rotating the secret. | Terraform |
| WLAN PPSK base network | UCG-Fiber normalizes PPSK WLAN `network_id` to the built-in Default LAN. Reference its read-only ID and bind every PPSK explicitly to a managed network; do not configure a base passphrase. | Terraform |
| WLAN PPSKs | Provider 0.57.0 has no write-only PPSK passwords. Sensitive PPSK values persist in private plans, state and backups. | Terraform |
| Device ports | Provider 0.57.0 preserves undeclared port entries but replaces each declared entry and sends the full override array. Use dedicated ports and compare other port settings after apply. | Terraform |

The provider's read-back `enabled=false` on `Default` does not describe LAN
availability. WAN/PPPoE and LEOX management are outside Terraform ownership.
