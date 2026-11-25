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

  dhcp_reservations = merge(local.server_reservations, {
    lg-tv = {
      mac                = var.infrastructure_macs["lg-tv"]
      network            = "orbit"
      ip                 = "10.0.40.107"
      allow_dynamic_pool = true
    }
    office-light = {
      mac                = var.infrastructure_macs["office-light"]
      network            = "stardust"
      ip                 = "10.0.50.167"
      allow_dynamic_pool = true
    }
    front-door-camera = {
      mac                = var.infrastructure_macs["front-door-camera"]
      network            = "stardust"
      ip                 = "10.0.50.190"
      allow_dynamic_pool = true
    }
    sonoff-zigbee = {
      mac                = var.infrastructure_macs["sonoff-zigbee"]
      network            = "stardust"
      ip                 = "10.0.50.182"
      allow_dynamic_pool = true
    }
    tv-ambient = {
      mac                = var.infrastructure_macs["tv-ambient"]
      network            = "stardust"
      ip                 = "10.0.50.124"
      allow_dynamic_pool = true
    }
    windowspc-01 = {
      mac                = var.infrastructure_macs["windowspc-01"]
      network            = "apollo"
      ip                 = "10.0.80.127"
      allow_dynamic_pool = true
    }
  })
}

import {
  for_each = local.dhcp_reservations
  to       = module.reservations.unifi_client.this[each.key]
  id       = nonsensitive(each.value.mac)
}

module "reservations" {
  source = "../modules/unifi/reservations"

  site         = var.controller.site
  networks     = local.networks
  reservations = local.dhcp_reservations
}
