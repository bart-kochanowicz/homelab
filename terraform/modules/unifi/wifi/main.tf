resource "unifi_wlan" "this" {
  for_each = var.wlans

  site          = var.site
  name          = "${var.name_prefix}${each.key}"
  network_id    = var.network_ids[each.value.network]
  ap_group_mode = "all"
  ap_group_ids  = [var.ap_group_id]
  user_group_id = var.user_group_id

  security        = "wpapsk"
  wpa3_support    = each.value.wpa_mode == "wpa3"
  wpa3_transition = false
  pmf_mode        = each.value.wpa_mode == "wpa3" ? "required" : "optional"
  enhanced_iot    = false
  wpa_enc         = "ccmp"
  group_rekey     = 3600
  bss_transition  = false
  hide_ssid       = false
  no2ghz_oui      = true
  passphrase_wo   = lookup(var.passphrases, each.key, null)

  private_preshared_keys_enabled = false

  wlan_bands = each.value.bands
  wlan_band  = contains(each.value.bands, "2g") && contains(each.value.bands, "5g") ? "both" : contains(each.value.bands, "5g") ? "5g" : "2g"

  lifecycle {
    prevent_destroy = true
  }
}
