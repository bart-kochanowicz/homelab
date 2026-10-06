# UniFi provider constraints

| Object | Constraint | Owner |
| --- | --- | --- |
| Built-in `Default` LAN | Read-only `data.unifi_network.default`; configuration belongs to the UniFi administrator. Provider 0.57.0 plans updates for omitted `enabled`, `setting_preference`, and `dhcpd_leasetime` fields after resource import. Recheck round-trip behavior before changing ownership after provider/controller upgrades. | Network administrator |

The provider's read-back `enabled=false` on `Default` does not describe LAN
availability. WAN/PPPoE and LEOX management are outside Terraform ownership.
