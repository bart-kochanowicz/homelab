output "network_ids" {
  description = "UniFi LAN network IDs keyed by stable logical identifier."
  value = merge(
    { for key, network in unifi_network.this : key => network.id },
    { for key, network in unifi_network.vlan_only : key => network.id }
  )
}
