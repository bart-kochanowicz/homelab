locals {
  devices = {
    flex-5 = {
      mac                = var.infrastructure_macs["flex-5"]
      management_network = "mission-control"
      ports = merge(
        {
          admin = {
            index   = 1
            profile = "access-apollo"
            name    = "${var.name_prefix}apollo"
          }
          admin-pc = {
            index   = 2
            profile = "access-apollo"
            name    = "${var.name_prefix}apollo-pc"
          }
          uplink = {
            index   = 5
            profile = "switch-trunk"
            name    = "${var.name_prefix}voyager-01"
          }
          flex-8 = {
            index   = 3
            profile = "switch-trunk"
            name    = "${var.name_prefix}flex-8"
          }
        },
        {
          for port in [4] : "parking-${port}" => {
            index   = port
            profile = "access-parking"
            name    = "${var.name_prefix}parking-${port}"
          }
        }
      )
    }
    flex-8 = {
      mac                = var.infrastructure_macs["flex-8"]
      management_network = "mission-control"
      ports = merge(
        {
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
          control-plane = {
            index   = 8
            profile = "access-launchpad"
            name    = "${var.name_prefix}control-plane-01"
          }
          uplink = {
            index   = 9
            profile = "switch-trunk"
            name    = "${var.name_prefix}flex-5"
          }
        },
        {
          for port in [2, 3, 4, 5, 6, 10] : "parking-${port}" => {
            index   = port
            profile = "access-parking"
            name    = "${var.name_prefix}parking-${port}"
          }
        }
      )
    }
    voyager-01 = {
      mac = var.infrastructure_macs["voyager-01"]
      ports = merge(
        {
          switches = {
            index   = 1
            profile = "switch-trunk"
            name    = "${var.name_prefix}flex-5"
          }
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
        },
        {
          for port in [3, 5, 6] : "parking-${port}" => {
            index   = port
            profile = "access-parking"
            name    = "${var.name_prefix}parking-${port}"
          }
        }
      )
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
