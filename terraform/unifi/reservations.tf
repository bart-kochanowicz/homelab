locals {
  server_reservations = {
    houston-01 = {
      mac     = var.infrastructure_macs["houston-01"]
      network = "launchpad"
      ip      = "10.0.70.10"
    }
    control-plane-01 = {
      mac     = var.infrastructure_macs["control-plane-01"]
      network = "launchpad"
      ip      = "10.0.70.11"
    }
    worker-01 = {
      mac     = var.infrastructure_macs["worker-01"]
      network = "launchpad"
      ip      = "10.0.70.12"
    }
  }
}

import {
  for_each = local.server_reservations
  to       = module.reservations.unifi_client.this[each.key]
  id       = nonsensitive(each.value.mac)
}

module "reservations" {
  source = "../modules/unifi/reservations"

  site         = var.controller.site
  networks     = local.networks
  reservations = local.server_reservations
}
