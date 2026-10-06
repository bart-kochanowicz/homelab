output "network_ids" {
  description = "UniFi LAN network IDs keyed by stable logical identifier."
  value       = { for key, network in unifi_network.this : key => network.id }
}
