locals {
  airplay_receiver_names = toset(["apple-tv-01", "homepod-01", "homepod-02"])
  airplay_reservations = {
    for name in local.airplay_receiver_names : name => {
      mac     = var.airplay_receivers[name].mac
      ip      = var.airplay_receivers[name].ip
      network = "orbit"
    }
  }
}

# Client imports require a non-sensitive MAC ID; only this field is declassified.
import {
  for_each = local.airplay_reservations
  to       = module.airplay_reservations.unifi_client.this[each.key]
  id       = nonsensitive(each.value.mac)
}

module "airplay_reservations" {
  source = "../modules/unifi/reservations"

  site         = var.controller.site
  networks     = local.networks
  reservations = local.airplay_reservations
}
