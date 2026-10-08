moved {
  from = module.unifi.unifi_network.this
  to   = module.networks.unifi_network.this
}

moved {
  from = module.unifi.unifi_network.vlan_only
  to   = module.networks.unifi_network.vlan_only
}

moved {
  from = module.unifi.unifi_port_profile.this
  to   = module.port_profiles.unifi_port_profile.this
}

module "networks" {
  source = "../modules/unifi/networks"

  site             = var.controller.site
  name_prefix      = var.name_prefix
  networks         = local.networks
  reserved_subnets = [data.unifi_network.default.subnet]
  vlan_only_networks = {
    parking = 999
  }
}

module "port_profiles" {
  source = "../modules/unifi/port-profiles"

  site                 = var.controller.site
  name_prefix          = var.name_prefix
  network_ids          = module.networks.network_ids
  reserved_network_ids = [data.unifi_network.default.id]
  port_profiles        = local.port_profiles
}
