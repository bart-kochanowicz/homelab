output "network_ids" {
  description = "UniFi LAN network IDs keyed by stable logical identifier."
  value       = local.network_ids
}

output "port_profile_ids" {
  description = "UniFi port profile IDs keyed by logical identifier."
  value       = { for key, profile in unifi_port_profile.this : key => profile.id }
}
