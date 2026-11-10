# Preserve active instances when removing the protected Guest collections.

moved {
  from = module.networks.unifi_network.this["endeavour"]
  to   = module.networks.unifi_network.active["endeavour"]
}

moved {
  from = module.networks.unifi_network.this["orbit"]
  to   = module.networks.unifi_network.active["orbit"]
}

moved {
  from = module.networks.unifi_network.this["stardust"]
  to   = module.networks.unifi_network.active["stardust"]
}

moved {
  from = module.networks.unifi_network.this["launchpad"]
  to   = module.networks.unifi_network.active["launchpad"]
}

moved {
  from = module.networks.unifi_network.this["apollo"]
  to   = module.networks.unifi_network.active["apollo"]
}

moved {
  from = module.networks.unifi_network.this["mission-control"]
  to   = module.networks.unifi_network.active["mission-control"]
}

moved {
  from = module.port_profiles.unifi_port_profile.this["access-endeavour"]
  to   = module.port_profiles.unifi_port_profile.active["access-endeavour"]
}

moved {
  from = module.port_profiles.unifi_port_profile.this["access-orbit"]
  to   = module.port_profiles.unifi_port_profile.active["access-orbit"]
}

moved {
  from = module.port_profiles.unifi_port_profile.this["access-stardust"]
  to   = module.port_profiles.unifi_port_profile.active["access-stardust"]
}

moved {
  from = module.port_profiles.unifi_port_profile.this["access-launchpad"]
  to   = module.port_profiles.unifi_port_profile.active["access-launchpad"]
}

moved {
  from = module.port_profiles.unifi_port_profile.this["access-apollo"]
  to   = module.port_profiles.unifi_port_profile.active["access-apollo"]
}

moved {
  from = module.port_profiles.unifi_port_profile.this["access-mission-control"]
  to   = module.port_profiles.unifi_port_profile.active["access-mission-control"]
}

moved {
  from = module.port_profiles.unifi_port_profile.this["access-parking"]
  to   = module.port_profiles.unifi_port_profile.active["access-parking"]
}

moved {
  from = module.port_profiles.unifi_port_profile.this["ap"]
  to   = module.port_profiles.unifi_port_profile.active["ap"]
}

moved {
  from = module.port_profiles.unifi_port_profile.this["switch-trunk"]
  to   = module.port_profiles.unifi_port_profile.active["switch-trunk"]
}

moved {
  from = module.firewall.unifi_firewall_zone.this["endeavour"]
  to   = module.firewall.unifi_firewall_zone.active["endeavour"]
}

moved {
  from = module.firewall.unifi_firewall_zone.this["orbit"]
  to   = module.firewall.unifi_firewall_zone.active["orbit"]
}

moved {
  from = module.firewall.unifi_firewall_zone.this["stardust"]
  to   = module.firewall.unifi_firewall_zone.active["stardust"]
}

moved {
  from = module.firewall.unifi_firewall_zone.this["launchpad"]
  to   = module.firewall.unifi_firewall_zone.active["launchpad"]
}

moved {
  from = module.firewall.unifi_firewall_zone.this["apollo"]
  to   = module.firewall.unifi_firewall_zone.active["apollo"]
}

moved {
  from = module.firewall.unifi_firewall_zone.this["mission-control"]
  to   = module.firewall.unifi_firewall_zone.active["mission-control"]
}
