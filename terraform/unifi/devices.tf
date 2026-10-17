locals {
  devices = {
    flex-5 = {
      mac                = var.infrastructure_macs["flex-5"]
      management_network = "mission-control"
      ports = {
        admin = {
          index   = 1
          profile = "access-apollo"
          name    = "${var.name_prefix}apollo"
        }
      }
    }
    flex-8 = {
      mac                = var.infrastructure_macs["flex-8"]
      management_network = "mission-control"
      ports = {
        houston = {
          index   = 1
          profile = "access-launchpad"
          name    = "${var.name_prefix}houston-01"
        }
        worker = {
          index   = 7
          profile = "access-launchpad"
          name    = "${var.name_prefix}worker-01"
        }
      }
    }
    voyager-01 = {
      mac = var.infrastructure_macs["voyager-01"]
      ports = {
        ap = {
          index    = 4
          profile  = "ap"
          name     = "${var.name_prefix}ap"
          poe_mode = "auto"
        }
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
  network_ids      = module.networks.network_ids
  devices          = local.devices

  depends_on = [module.reservations, module.firewall]
}
