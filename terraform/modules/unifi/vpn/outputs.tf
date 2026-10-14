output "network_id" {
  description = "VPN network ID for the firewall zone membership owner."
  value       = unifi_vpn_server.this.id
}

output "server_public_key" {
  description = "WireGuard server public key; excludes the private key stored in state."
  value       = unifi_vpn_server.this.wireguard.public_key
}

output "endpoint" {
  description = "Public IPv4 endpoint with its UDP port."
  value       = "${var.public_ip}:${var.port}"
}
