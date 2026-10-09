output "wlan_ids" {
  description = "UniFi WLAN IDs keyed by logical identifier."
  value = merge(
    { for key, wlan in unifi_wlan.this : key => wlan.id },
    { for key, wlan in unifi_wlan.ppsk : key => wlan.id },
  )
}
