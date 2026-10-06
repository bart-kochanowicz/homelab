output "network_ids" {
  description = "UniFi LAN network IDs keyed by logical identifier."
  value       = module.unifi.network_ids
}
