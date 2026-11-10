data "unifi_ap_group" "all" {
  site = var.controller.site
  name = "All APs"
}

data "unifi_client_qos_rate" "default" {
  site = var.controller.site
  name = "Default"
}

moved {
  from = module.wifi.unifi_wlan.ppsk["orbit"]
  to   = module.wifi.unifi_wlan.this["orbit"]
}

module "wifi" {
  source = "../modules/unifi/wifi"

  site          = var.controller.site
  name_prefix   = var.name_prefix
  network_ids   = module.networks.network_ids
  ap_group_id   = data.unifi_ap_group.all.id
  user_group_id = data.unifi_client_qos_rate.default.id
  passphrases = merge(var.wifi_passphrases, {
    orbit    = var.wifi_ppsks["orbit/home"]
    stardust = var.wifi_ppsks["orbit/iot"]
  })
  wlans = {
    apollo = {
      network = "apollo"
      bands   = ["5g"]
    }
    endeavour = {
      network = "endeavour"
      bands   = ["2g", "5g"]
    }
    orbit = {
      network = "orbit"
      bands   = ["2g", "5g"]
    }
    stardust = {
      network  = "stardust"
      bands    = ["2g"]
      wpa_mode = "wpa2"
    }
  }
}
