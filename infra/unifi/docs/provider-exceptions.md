# UniFi provider constraints

| Object | Constraint | Owner |
| --- | --- | --- |
| Built-in `Default` LAN | Read-only `data.unifi_network.default`; configuration belongs to the UniFi administrator. Provider 0.57.0 plans updates for omitted `enabled`, `setting_preference`, and `dhcpd_leasetime` fields after resource import. Recheck round-trip behavior before changing ownership after provider/controller upgrades. | Network administrator |
| Port profile tags | Provider 0.57.0 does not serialize `tagged_networkconf_ids`. Use `tagged_vlan_mgmt = "custom"` with `excluded_networkconf_ids` computed from every LAN outside the native/tagged set. Recheck the provider implementation and controller read-back after upgrades. | Terraform |
| Unrouted VLAN DHCP | Omit `dhcp_server` on VLAN-only networks. Provider 0.57.0 injects lease/conflict-checking defaults into a configured object, while UniFi omits those fields, causing an inconsistent result after apply. | Terraform |

The provider's read-back `enabled=false` on `Default` does not describe LAN
availability. WAN/PPPoE and LEOX management are outside Terraform ownership.
