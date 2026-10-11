mock_provider "unifi" {
  mock_data "unifi_client_info" {
    defaults = { network_id = "test-default-lan" }
  }
}

override_data {
  target = data.unifi_network.default
  values = { id = "test-default-lan", purpose = "corporate", subnet = "192.168.1.1/24" }
}

override_module {
  target = module.networks
  outputs = {
    network_ids = {
      endeavour       = "test-work"
      orbit           = "test-home"
      stardust        = "test-iot"
      comet           = "test-guest"
      launchpad       = "test-servers"
      apollo          = "test-admin"
      mission-control = "test-management"
      parking         = "test-parking"
    }
  }
}

override_resource {
  target = module.devices.unifi_device.this["flex-5"]
  values = { id = "74:f9:2c:96:c2:cc", mac = "74:f9:2c:96:c2:cc" }
}

override_module {
  target = module.port_profiles
  outputs = {
    port_profile_ids = { access-apollo = "test-admin-profile" }
  }
}

variables {
  controller       = { url = "https://unifi.example.internal" }
  unifi_auth       = { username = "test-only", password = "test-only" } # gitleaks:allow -- mock provider input
  wifi_passphrases = { apollo = "test-only-passphrase", endeavour = "test-work-passphrase" }
  wifi_ppsks = {
    "orbit/home"  = "test-home-passphrase"
    "orbit/iot"   = "test-iot-passphrase"
    "orbit/guest" = "test-guest-passphrase"
  }
}

run "least_privilege_access_matrix" {
  command = plan

  assert {
    condition = alltrue([
      for rule in values(local.firewall_rules) :
      !contains(["endeavour", "stardust", "comet"], rule.source.zone) ? true : (
        rule.destination.zone == "external" ? try(rule.destination.invert_ips, false) :
        rule.destination.zone == "gateway" && (
          try(rule.destination.ports == "53", false) ||
          (try(rule.protocol == "udp", false) && try(contains(["67", "123"], rule.destination.ports), false)) ||
          try(rule.protocol == "icmpv6", false)
        )
      )
    ])
    error_message = "Work, IoT and Guest must have only public Internet and required gateway services."
  }
  assert {
    condition = (
      alltrue([for rule in values(local.firewall_rules) :
        rule.source.zone != "apollo" || !contains(["endeavour", "comet", "orbit", "stardust"], rule.destination.zone)
      ]) &&
      local.firewall_rules.admin-servers.destination.zone == "launchpad" &&
      local.firewall_rules.admin-management.destination.zone == "mission-control" &&
      local.firewall_rules.admin-gateway.destination.zone == "gateway"
    )
    error_message = "Admin must reach Servers, Management and Gateway without blanket client access."
  }
  assert {
    condition = alltrue([
      for rule in values(local.firewall_rules) :
      rule.source.zone != "orbit" || !contains(["internal", "launchpad"], rule.destination.zone) ? true : (
        rule.protocol == "tcp" && contains(["8123", "30000"], rule.destination.ports) && length(rule.destination.clients) == 1
      )
    ])
    error_message = "Home server access must identify the service and registered server MAC."
  }
  assert {
    condition = (
      contains(local.non_public_destinations, "192.168.0.0/16") &&
      contains(local.non_public_destinations, "fc00::/7") &&
      contains(local.non_public_destinations, "fe80::/10") &&
      local.firewall_rules.admin-ont.source.zone == "apollo" &&
      local.firewall_rules.admin-ont.destination.ips == ["192.168.100.1"] &&
      local.firewall_rules.houston-controller.source.clients == [local.server_macs.houston] &&
      local.firewall_rules.houston-controller.destination.ports == "443"
    )
    error_message = "Internet rules must exclude private/ONT destinations and controller access must identify Houston."
  }
}

run "server_rule_follows_membership" {
  command = plan
  override_data {
    target = data.unifi_client_info.server["worker"]
    values = { network_id = "test-servers" }
  }
  assert {
    condition = (
      local.firewall_rules.home-ha.destination.zone == "launchpad" &&
      local.firewall_rules.admin-worker.destination.zone == "launchpad" &&
      local.firewall_rules.admin-control-plane.destination.zone == "internal"
    )
    error_message = "Registered client rules must follow independently reported network memberships."
  }
}

run "reject_server_on_client_vlan" {
  command = plan
  override_data {
    target = data.unifi_client_info.server["worker"]
    values = { network_id = "test-home" }
  }
  expect_failures = [data.unifi_client_info.server["worker"]]
}
