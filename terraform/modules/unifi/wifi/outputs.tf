output "wlan_ids" {
  description = "UniFi WLAN IDs keyed by logical identifier."
  value       = { for key, wlan in unifi_wlan.this : key => wlan.id }
}
