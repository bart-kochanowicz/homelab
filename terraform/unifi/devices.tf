locals {
  devices = {
    flex-5 = {
      mac = var.infrastructure_macs["flex-5"]
      ports = {
        admin = {
          index   = 1
          profile = "access-apollo"
          name    = "${var.name_prefix}apollo"
        }
      }
    }
    voyager-01 = {
      mac = var.infrastructure_macs["voyager-01"]
      ports = {
        home = {
          index   = 2
          profile = "access-orbit"
          name    = "${var.name_prefix}orbit"
        }
      }
    }
  }
}

# UniFi import IDs are MAC addresses; Terraform rejects sensitive import IDs.
import {
  for_each = local.devices
  to       = module.devices.unifi_device.this[each.key]
  id       = nonsensitive(each.value.mac)
}

module "devices" {
  source = "../modules/unifi/devices"

  site             = var.controller.site
  port_profile_ids = module.port_profiles.port_profile_ids
  devices          = local.devices

  depends_on = [module.airplay_reservations]
}
