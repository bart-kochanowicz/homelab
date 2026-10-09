data "unifi_ap_group" "all" {
  site = var.controller.site
  name = "All APs"
}

data "unifi_client_qos_rate" "default" {
  site = var.controller.site
  name = "Default"
}

module "wifi" {
  source = "../modules/unifi/wifi"

  site                 = var.controller.site
  name_prefix          = var.name_prefix
  network_ids          = module.networks.network_ids
  ap_group_id          = data.unifi_ap_group.all.id
  user_group_id        = data.unifi_client_qos_rate.default.id
  passphrases          = var.wifi_passphrases
  ppsk_passphrases     = var.wifi_ppsks
  ppsk_base_network_id = data.unifi_network.default.id
  wlans = {
    apollo = {
      network = "apollo"
      bands   = ["5g"]
    }
    endeavour = {
      network = "endeavour"
      bands   = ["2g", "5g"]
    }
  }
  ppsk_wlans = {
    orbit = {
      bands = ["2g", "5g"]
      keys = {
        home  = "orbit"
        iot   = "stardust"
        guest = "comet"
      }
    }
  }
}
