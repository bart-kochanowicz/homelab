output "network_ids" {
  description = "Managed UniFi LAN network IDs keyed by logical identifier."
  value       = module.networks.network_ids
}

output "default_network_id" {
  description = "ID of the read-only built-in Default LAN."
  value       = data.unifi_network.default.id
}

output "port_profile_ids" {
  description = "Managed UniFi port profile IDs keyed by logical identifier."
  value       = module.port_profiles.port_profile_ids
}

output "wlan_ids" {
  description = "Managed UniFi WLAN IDs keyed by logical identifier."
  value       = module.wifi.wlan_ids
}

output "device_ids" {
  description = "Managed UniFi device IDs keyed by logical identifier."
  value       = module.devices.device_ids
}
