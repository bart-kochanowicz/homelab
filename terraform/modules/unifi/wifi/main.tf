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

resource "unifi_wlan" "ppsk" {
  for_each = var.ppsk_wlans

  site          = var.site
  name          = "${var.name_prefix}${each.key}"
  network_id    = var.network_ids[each.value.keys[each.value.default_key]]
  ap_group_mode = "all"
  ap_group_ids  = [var.ap_group_id]
  user_group_id = var.user_group_id

  security        = "wpapsk"
  wpa3_support    = false
  wpa3_transition = false
  pmf_mode        = "optional"
  enhanced_iot    = false
  l2_isolation    = false
  is_guest        = false
  passphrase_wo   = lookup(var.ppsk_passphrases, "${each.key}/${each.value.default_key}", null)

  private_preshared_keys_enabled = true
  private_preshared_keys = [
    for key, network in each.value.keys : {
      network_id = var.network_ids[network]
      password   = lookup(var.ppsk_passphrases, "${each.key}/${key}", null)
    }
  ]

  wlan_bands = each.value.bands
  wlan_band  = contains(each.value.bands, "2g") && contains(each.value.bands, "5g") ? "both" : contains(each.value.bands, "5g") ? "5g" : "2g"

  lifecycle {
    prevent_destroy = true
  }
}
