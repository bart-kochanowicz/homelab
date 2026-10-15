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
  sensitive   = true
  value       = module.devices.device_ids
}

output "firewall_zone_ids" {
  description = "Managed firewall zone IDs keyed by logical name."
  value       = module.firewall.zone_ids
}

output "firewall_policy_order" {
  description = "Controller-assigned firewall policy indices."
  value       = module.firewall.policy_order
}

output "wireguard_clients" {
  description = "Client configuration with the WAN endpoint; retain each device's existing PrivateKey."
  sensitive   = true
  value = {
    for key, peer in local.vpn_peers : key => <<-EOT
      [Interface]
      # Retain this device's existing PrivateKey.
      Address = ${peer.interface_ip}/32
      DNS = ${split("/", local.networks.apollo.subnet)[0]}

      [Peer]
      PublicKey = ${module.vpn.server_public_key}
      Endpoint = ${module.vpn.endpoint}
      AllowedIPs = ${join(", ", local.vpn_client_routes)}
      PersistentKeepalive = 25
    EOT
  }
}
