resource "unifi_wlan" "this" {
  for_each = var.wlans

  site          = var.site
  name          = "${var.name_prefix}${each.key}"
  network_id    = var.network_ids[each.value.network]
  user_group_id = var.user_group_id

  ap_group = {
    mode = "all"
    ids  = [var.ap_group_id]
  }

  security = "wpapsk"
  wpa3 = {
    support    = each.value.wpa_mode == "wpa3"
    transition = false
  }
  wpa = {
    enc = "ccmp"
  }
  pmf_mode       = each.value.wpa_mode == "wpa3" ? "required" : "optional"
  enhanced_iot   = false
  group_rekey    = 3600
  bss_transition = false
  hide_ssid      = false
  no2ghz_oui     = true

  # The controller receives passphrase_wo only on create or when the version changes.
  passphrase_wo         = lookup(var.passphrases, each.key, null)
  passphrase_wo_version = each.value.passphrase_version

  private_preshared_keys_enabled = false

  wlan_bands = each.value.bands
  wlan_band  = contains(each.value.bands, "2g") && contains(each.value.bands, "5g") ? "both" : contains(each.value.bands, "5g") ? "5g" : "2g"

  lifecycle {
    prevent_destroy = true
  }
}
