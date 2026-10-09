resource "unifi_wlan" "this" {
  for_each = var.wlans

  site          = var.site
  name          = "${var.name_prefix}${each.key}"
  network_id    = var.network_ids[each.value.network]
  ap_group_mode = "all"
  ap_group_ids  = [var.ap_group_id]
  user_group_id = var.user_group_id

  security        = "wpapsk"
  wpa3_support    = true
  wpa3_transition = false
  pmf_mode        = "required"
  enhanced_iot    = false
  passphrase_wo   = lookup(var.passphrases, each.key, null)

  wlan_bands = each.value.bands
  wlan_band  = contains(each.value.bands, "2g") && contains(each.value.bands, "5g") ? "both" : contains(each.value.bands, "5g") ? "5g" : "2g"

  lifecycle {
    prevent_destroy = true
  }
}
