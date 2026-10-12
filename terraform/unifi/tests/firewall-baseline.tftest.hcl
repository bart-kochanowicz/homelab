mock_provider "unifi" {
  mock_data "unifi_client_info" {
    defaults = { network_id = "test-default-lan", ip = "192.168.1.200" }
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
  values = { id = "02:00:00:00:00:05", mac = "02:00:00:00:00:05" }
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
      local.firewall_rules["houston-01-controller"].source.clients == [local.server_macs["houston-01"]] &&
      local.firewall_rules["houston-01-controller"].destination.ports == "443"
    )
    error_message = "Internet rules must exclude private/ONT destinations and controller access must identify Houston."
  }
}

run "server_rule_follows_address_and_membership" {
  command = plan
  override_data {
    target = data.unifi_client_info.server["worker-01"]
    values = { network_id = "test-servers", ip = "10.0.70.12" }
  }
  assert {
    condition = (
      local.firewall_rules.home-ha.destination.zone == "launchpad" &&
      local.firewall_rules["admin-worker-01"].destination.zone == "launchpad" &&
      local.firewall_rules["admin-control-plane-01"].destination.zone == "internal" &&
      local.server_ipv4_addresses[local.server_macs["worker-01"]] == "10.0.70.12" &&
      local.server_ipv4_addresses[local.server_macs["control-plane-01"]] == "192.168.1.200"
    )
    error_message = "Registered client rules must follow independently reported IPv4 addresses and network memberships."
  }
}

run "icmp_errors_require_related_state" {
  command = plan
  assert {
    condition = alltrue([
      for name, rule in local.firewall_rules :
      rule.states == ["RELATED"] && !rule.reply && !can(rule.destination.ports)
      if endswith(name, "-icmp-errors") || endswith(name, "-icmpv6-errors")
    ])
    error_message = "ICMP errors must match RELATED state without relying on TCP/UDP port filters."
  }
}

run "reject_server_on_client_vlan" {
  command = plan
  override_data {
    target = data.unifi_client_info.server["worker-01"]
    values = { network_id = "test-home" }
  }
  expect_failures = [data.unifi_client_info.server["worker-01"]]
}

run "reject_server_without_ipv4" {
  command = plan
  override_data {
    target = data.unifi_client_info.server["worker-01"]
    values = { ip = "" }
  }
  expect_failures = [data.unifi_client_info.server["worker-01"]]
}
