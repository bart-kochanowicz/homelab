output "network_ids" {
  description = "Managed UniFi LAN network IDs keyed by logical identifier."
  value       = module.unifi.network_ids
}

output "default_network_id" {
  description = "ID of the read-only built-in Default LAN."
  value       = data.unifi_network.default.id
}
