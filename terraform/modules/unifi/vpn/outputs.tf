output "network_id" {
  description = "VPN network ID; UniFi owns its built-in VPN zone membership."
  value       = unifi_vpn_server.this.id
}

output "server_public_key" {
  description = "WireGuard server public key; excludes the private key stored in state."
  value       = wireguard_asymmetric_key.server.public_key
}

output "endpoint" {
  description = "WAN IPv4 endpoint with its UDP port."
  sensitive   = true
  value       = "${var.public_ip}:${var.port}"
}
