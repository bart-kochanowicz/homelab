output "device_ids" {
  description = "Managed UniFi device IDs keyed by logical identifier."
  value       = { for key, device in unifi_device.this : key => device.id }
}
