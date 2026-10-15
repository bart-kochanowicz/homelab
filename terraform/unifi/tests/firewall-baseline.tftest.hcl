mock_provider "unifi" {
  mock_data "unifi_client_info" {
    defaults = { network_id = "test-default-lan", ip = "192.168.1.200" }
  }
}

override_data {
  target = data.unifi_network.default
  values = { id = "test-default-lan", purpose = "corporate", subnet = "192.168.1.1/24" }
}

override_data {
  target = data.unifi_client_info.server["worker-01"]
  values = { network_id = "test-default-lan", ip = "192.168.1.217" }
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

override_module {
  target = module.vpn
  outputs = {
    network_id        = "test-vpn"
    server_public_key = "test-server-public-key"
    endpoint          = "198.51.100.10:51820"
  }
}

override_resource {
  target = module.airplay_reservations.unifi_client.this["apple-tv-01"]
  values = { id = "test-apple-tv-01", mac = "02:00:00:00:00:30" }
}

override_resource {
  target = module.airplay_reservations.unifi_client.this["homepod-01"]
  values = { id = "test-homepod-01", mac = "02:00:00:00:00:31" }
}

override_resource {
  target = module.airplay_reservations.unifi_client.this["homepod-02"]
  values = { id = "test-homepod-02", mac = "02:00:00:00:00:32" }
}

variables {
  airplay_receivers = {
    apple-tv-01 = { mac = "02:00:00:00:00:30", ip = "10.0.40.10" }
    homepod-01  = { mac = "02:00:00:00:00:31", ip = "10.0.40.11" }
    homepod-02  = { mac = "02:00:00:00:00:32", ip = "10.0.40.12" }
  }
  infrastructure_macs = {
    flex-5           = "02:00:00:00:00:05"
    houston-01       = "02:00:00:00:00:10"
    control-plane-01 = "02:00:00:00:00:11"
    worker-01        = "02:00:00:00:00:12"
  }
  vpn_public_ip = "198.51.100.10"
  vpn_peer_public_keys = {
    macbook-01 = "hSDwCYkwp1R0i33ctD73Wg2/Og0mOBr066SpjqqbTmo="
  }
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
        (rule.source.zone == "comet" && rule.destination.zone == "orbit" &&
          try(rule.destination.ip_group == "airplay-devices", false) &&
          ((rule.protocol == "tcp" && rule.destination.ports == "7000") ||
          (rule.protocol == "tcp_udp" && rule.destination.ports == "49152-65535"))
          ) || rule.destination.zone == "gateway" && (
          try(rule.destination.ports == "53", false) ||
          (try(rule.protocol == "udp", false) && try(contains(["67", "123"], rule.destination.ports), false)) ||
          try(rule.protocol == "icmpv6", false)
        )
      )
    ])
    error_message = "Work/IoT remain isolated; Guest may reach only public Internet, gateway services and selected AirPlay receivers."
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

run "guest_airplay_requires_receiver_group" {
  command = plan
  assert {
    condition = (
      alltrue([for rule in values(local.airplay_firewall_rules) :
        rule.ip_version == "IPV4" && (
          rule.source.zone == "comet" ? (
            rule.destination.zone == "orbit" && rule.destination.ip_group == "airplay-devices" &&
            ((rule.protocol == "tcp" && rule.destination.ports == "7000") ||
            (rule.protocol == "tcp_udp" && rule.destination.ports == "49152-65535"))
            ) : (
            rule.source.zone == "orbit" && rule.source.ip_group == "airplay-devices" &&
            rule.destination.zone == "comet" && rule.protocol == "icmp" && rule.states == ["RELATED"] && !rule.reply
          )
        )
      ]) &&
      toset(keys(local.airplay_reservations)) == toset(["apple-tv-01", "homepod-01", "homepod-02"]) &&
      alltrue([for reservation in values(local.airplay_reservations) : reservation.network == "orbit"])
    )
    error_message = "Guest AirPlay must target only selected Home receivers and explicit services; receivers may return only tracked replies/errors."
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
      local.server_ipv4_addresses[local.server_macs["control-plane-01"]] == "192.168.1.200" &&
      !contains(local.vpn_client_routes, "192.168.1.217/32") &&
      !contains(local.vpn_client_routes, "10.0.70.12/32") &&
      contains(local.vpn_client_routes, "10.0.70.0/24")
    )
    error_message = "Registered client rules must follow independently reported IPv4 addresses and network memberships."
  }
}

run "vpn_keeps_builtin_membership_and_split_routes" {
  command = plan
  assert {
    condition = (
      local.firewall_zone_network_ids.apollo == ["test-admin"] &&
      alltrue([for ids in values(local.firewall_zone_network_ids) : length(ids) == 1 && !contains(ids, "test-vpn")])
    )
    error_message = "Custom zones must own only their LANs; UniFi owns the VPN network membership."
  }
  assert {
    condition = (
      local.vpn_client_routes == sort([
        "10.0.70.0/24", "10.0.80.0/24", "10.0.90.0/24", "10.0.100.1/32", "192.168.1.1/32", "192.168.1.200/32", "192.168.1.217/32", "192.168.100.1/32"
      ]) && !contains(keys(local.firewall_rules), "wireguard-handshake")
    )
    error_message = "Split routes must exclude default/client routes; controller-owned WireGuard handshake rules must not be duplicated."
  }
}

run "vpn_permissions_require_admin_pool" {
  command = plan
  assert {
    condition = (
      length(local.vpn_firewall_rules) == 10 &&
      alltrue([for rule in values(local.vpn_firewall_rules) :
        rule.source.zone == "vpn" && rule.source.ips == ["10.0.100.0/24"] && rule.ip_version == "IPV4" &&
        contains(["apollo", "launchpad", "mission-control", "gateway", "external", "internal"], rule.destination.zone)
        if rule.source.zone == "vpn"
      ]) &&
      local.vpn_firewall_rules.vpn-servers.destination.zone == "launchpad" &&
      local.vpn_firewall_rules.vpn-management.destination.zone == "mission-control" &&
      local.vpn_firewall_rules.vpn-gateway.destination.zone == "gateway" &&
      local.vpn_firewall_rules["vpn-worker-01"].destination.clients == [local.server_macs["worker-01"]] &&
      local.vpn_firewall_rules.vpn-internet.destination.invert_ips &&
      contains(local.vpn_firewall_rules.vpn-internet.destination.ips, "192.168.0.0/16") &&
      local.vpn_firewall_rules.vpn-internet-icmp-errors.destination.ips == ["10.0.100.0/24"] &&
      local.vpn_firewall_rules.vpn-internet-icmp-errors.states == ["RELATED"] &&
      !local.vpn_firewall_rules.vpn-internet-icmp-errors.reply
    )
    error_message = "Only the administrative VPN pool may reach Admin destinations; other private client networks remain excluded."
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
