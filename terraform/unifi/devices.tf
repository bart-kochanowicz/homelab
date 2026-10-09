locals {
  devices = {
    flex-5 = {
      mac = "74:f9:2c:96:c2:cc"
      ports = {
        admin = {
          index   = 1
          profile = "access-apollo"
          name    = "${var.name_prefix}apollo"
        }
      }
    }
  }
}

import {
  for_each = local.devices
  to       = module.devices.unifi_device.this[each.key]
  id       = each.value.mac
}

module "devices" {
  source = "../modules/unifi/devices"

  site             = var.controller.site
  port_profile_ids = module.port_profiles.port_profile_ids
  devices          = local.devices
}
