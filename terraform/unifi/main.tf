module "unifi" {
  source = "../modules/unifi"

  site          = var.controller.site
  name_prefix   = var.name_prefix
  networks      = local.networks
  port_profiles = local.port_profiles
  vlan_only_networks = {
    parking = 999
  }
  reserved_networks = {
    default = { id = data.unifi_network.default.id, subnet = data.unifi_network.default.subnet }
  }
}
