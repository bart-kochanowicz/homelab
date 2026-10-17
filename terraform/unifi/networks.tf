locals {
  vlan_ids = {
    endeavour       = 30
    orbit           = 40
    stardust        = 50
    comet           = 60
    launchpad       = 70
    apollo          = 80
    mission-control = 90
  }

  networks = {
    for name, vlan in local.vlan_ids : name => {
      vlan   = vlan
      subnet = "10.0.${vlan}.1/24"
      dhcp = {
        start = "10.0.${vlan}.100"
        stop  = "10.0.${vlan}.199"
      }
    }
  }

  port_profiles = merge(
    { for name in keys(local.vlan_ids) : "access-${name}" => { native_network = name } },
    {
      ap = {
        native_network  = "mission-control"
        tagged_networks = ["endeavour", "orbit", "stardust", "comet", "apollo"]
      }
      switch-trunk = {
        native_network  = "parking"
        tagged_networks = ["launchpad", "apollo", "mission-control"]
      }
      access-parking = { native_network = "parking" }
    }
  )
}

moved {
  from = module.port_profiles.unifi_port_profile.this["servers-trunk"]
  to   = module.port_profiles.unifi_port_profile.this["switch-trunk"]
}
