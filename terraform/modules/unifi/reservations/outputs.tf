output "ipv4_addresses" {
  description = "Reserved IPv4 addresses keyed by logical client name."
  sensitive   = true
  value       = { for name, client in unifi_client.this : name => client.fixed_ip }
}
