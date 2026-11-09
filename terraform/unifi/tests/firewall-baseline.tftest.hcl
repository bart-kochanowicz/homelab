mock_provider "unifi" {}

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
  target = module.reservations.unifi_client.this["houston-01"]
  values = { id = "02:00:00:00:00:10", mac = "02:00:00:00:00:10" }
}

override_resource {
  target = module.reservations.unifi_client.this["control-plane-01"]
  values = { id = "02:00:00:00:00:11", mac = "02:00:00:00:00:11" }
}

override_resource {
  target = module.reservations.unifi_client.this["worker-01"]
  values = { id = "02:00:00:00:00:12", mac = "02:00:00:00:00:12" }
}

override_resource {
  target = module.reservations.unifi_client.this["windowspc-01"]
  values = { id = "02:00:00:00:00:80", mac = "02:00:00:00:00:80" }
}

override_resource {
  target = module.reservations.unifi_client.this["tv-ambient"]
  values = { id = "02:00:00:00:00:50", mac = "02:00:00:00:00:50" }
}

override_resource {
  target = module.reservations.unifi_client.this["front-door-camera"]
  values = { id = "02:00:00:00:00:51", mac = "02:00:00:00:00:51" }
}

override_resource {
  target = module.reservations.unifi_client.this["sonoff-zigbee"]
  values = { id = "02:00:00:00:00:52", mac = "02:00:00:00:00:52" }
}

override_resource {
  target = module.reservations.unifi_client.this["lg-tv"]
  values = { id = "02:00:00:00:00:40", mac = "02:00:00:00:00:40" }
}

override_resource {
  target = module.devices.unifi_device.this["flex-5"]
  values = { id = "02:00:00:00:00:05", mac = "02:00:00:00:00:05" }
}

override_resource {
  target = module.devices.unifi_device.this["flex-8"]
  values = { id = "02:00:00:00:00:07", mac = "02:00:00:00:00:07" }
}

override_resource {
  target = module.devices.unifi_device.this["voyager-01"]
  values = { id = "02:00:00:00:00:06", mac = "02:00:00:00:00:06" }
}

override_module {
  target = module.port_profiles
  outputs = {
    port_profile_ids = { access-apollo = "test-admin-profile", access-orbit = "test-home-profile", access-stardust = "test-iot-profile", access-launchpad = "test-servers-profile", access-parking = "test-parking-profile", switch-trunk = "test-trunk-profile", ap = "test-ap-profile" }
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

variables {
  infrastructure_macs = {
    flex-5            = "02:00:00:00:00:05"
    flex-8            = "02:00:00:00:00:07"
    voyager-01        = "02:00:00:00:00:06"
    houston-01        = "02:00:00:00:00:10"
    control-plane-01  = "02:00:00:00:00:11"
    worker-01         = "02:00:00:00:00:12"
    front-door-camera = "02:00:00:00:00:51"
    lg-tv             = "02:00:00:00:00:40"
    sonoff-zigbee     = "02:00:00:00:00:52"
    tv-ambient        = "02:00:00:00:00:50"
    windowspc-01      = "02:00:00:00:00:80"
  }
  vpn_public_ip = "198.51.100.10"
  vpn_peer_public_keys = {
    macbook-01   = "hSDwCYkwp1R0i33ctD73Wg2/Og0mOBr066SpjqqbTmo="
    iphone-01    = "BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBA="
    windowspc-01 = "CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCA="
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

run "sonoff_uses_only_flex8_port2_in_iot" {
  command = plan

  assert {
    condition = (
      flatten([for key, device in local.devices : [for port in values(device.ports) :
        "${key}/${port.index}" if port.profile == "access-stardust"
      ]]) == ["flex-8/2"] &&
      local.port_profiles["access-stardust"].native_network == "stardust"
    )
    error_message = "Only Flex 8 port 2 must use the SONOFF IoT access profile."
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
    error_message = "Work, IoT and Guest may reach only public Internet and required gateway services."
  }
  assert {
    condition = (
      alltrue([for rule in values(local.firewall_rules) :
        rule.source.zone != "apollo" || !contains(["endeavour", "comet", "orbit", "stardust"], rule.destination.zone) ||
        (rule.destination.zone == "stardust" && try(
          rule.destination.ips == [local.dhcp_reservations["sonoff-zigbee"].ip] &&
          rule.protocol == "tcp" && rule.destination.ports == "80" && rule.ip_version == "IPV4", false
        ))
      ]) &&
      local.firewall_rules.admin-servers.destination.zone == "launchpad" &&
      local.firewall_rules.admin-management.destination.zone == "mission-control" &&
      local.firewall_rules.admin-gateway.destination.zone == "gateway"
    )
    error_message = "Admin must reach Servers, Management, Gateway and only the exact SONOFF HTTP console without blanket client access."
  }
  assert {
    condition = alltrue([
      for name, rule in local.firewall_rules :
      rule.source.zone != "orbit" || !contains(["internal", "launchpad"], rule.destination.zone) ? true : (
        rule.protocol == "tcp" && (
          name == "home-ha-https" ? (
            rule.ip_version == "IPV4" && rule.destination.ports == "443" &&
            rule.destination.zone == "launchpad" && rule.destination.ips == ["10.0.70.200"]
          ) : contains(["8123", "30000"], rule.destination.ports) && length(rule.destination.clients) == 1
        )
      )
    ])
    error_message = "Home server access must identify a registered server or the exact HA HTTPS VIP."
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

run "home_moonlight_is_limited_to_sunshine_on_one_admin_pc" {
  command = plan

  assert {
    condition = (
      local.dhcp_reservations["windowspc-01"].ip == "10.0.80.127" &&
      local.dhcp_reservations["windowspc-01"].network == "apollo" &&
      local.dhcp_reservations["windowspc-01"].allow_dynamic_pool &&
      local.sunshine_ipv4_address == local.dhcp_reservations["windowspc-01"].ip &&
      toset([for name, rule in local.firewall_rules : name
        if rule.source.zone == "orbit" && rule.destination.zone == "apollo"
      ]) == toset(["home-sunshine-tcp", "home-sunshine-udp"]) &&
      alltrue([for name in ["home-sunshine-tcp", "home-sunshine-udp"] :
        local.firewall_rules[name].ip_version == "IPV4" &&
        local.firewall_rules[name].destination.ips == ["10.0.80.127"] &&
        !try(local.firewall_rules[name].destination.invert_ips, false) &&
        try(local.firewall_rules[name].reply, true) &&
        try(local.firewall_rules[name].track_state, true)
      ]) &&
      local.firewall_rules.home-sunshine-tcp.protocol == "tcp" &&
      local.firewall_rules.home-sunshine-tcp.destination.ports == "47984,47989,48010" &&
      local.firewall_rules.home-sunshine-udp.protocol == "udp" &&
      local.firewall_rules.home-sunshine-udp.destination.ports == "47998-48000"
    )
    error_message = "Home may reach only the Sunshine PC on its streaming ports, with stateful replies and no web UI or discovery access."
  }
}

run "camera_address_is_stable_without_new_inter_zone_permissions" {
  command = plan

  assert {
    condition = (
      local.dhcp_reservations["front-door-camera"].network == "stardust" &&
      local.dhcp_reservations["front-door-camera"].ip == "10.0.50.190" &&
      local.dhcp_reservations["front-door-camera"].allow_dynamic_pool &&
      local.private_dns_records["front-door-camera"].name == "front-door-camera.thecavespace.net" &&
      local.private_dns_records["front-door-camera"].address == local.dhcp_reservations["front-door-camera"].ip &&
      alltrue([for rule in values(local.firewall_rules) :
        !contains(try(rule.source.ips, []), "10.0.50.190") &&
        !contains(try(rule.destination.ips, []), "10.0.50.190") &&
        (rule.destination.zone != "stardust" || rule.source.zone == "gateway" ||
          try(contains(["icmp", "icmpv6"], rule.protocol) && rule.states == ["RELATED"], false) ||
          try(rule.destination.ips == ["10.0.50.124"], false) ||
          try(rule.destination.ips == [local.dhcp_reservations["sonoff-zigbee"].ip], false)
        )
      ])
    )
    error_message = "The camera must retain its reserved IoT address and private DNS without new access; only gateway services, related ICMP errors and exact LED/coordinator allowances may enter IoT."
  }
}

run "ha_lg_access_is_limited_to_the_reserved_webos_service" {
  command = plan

  assert {
    condition = (
      local.dhcp_reservations["lg-tv"].network == "orbit" &&
      local.dhcp_reservations["lg-tv"].ip == "10.0.40.107" &&
      local.dhcp_reservations["lg-tv"].allow_dynamic_pool &&
      local.private_dns_records["lg-tv"].name == "lg-tv.thecavespace.net" &&
      local.private_dns_records["lg-tv"].address == local.dhcp_reservations["lg-tv"].ip &&
      toset([for name, rule in local.firewall_rules : name
        if rule.source.zone == "launchpad" && rule.destination.zone == "orbit" && try(rule.protocol == "tcp", false)
      ]) == toset(["ha-lg-tv"]) &&
      local.firewall_rules.ha-lg-tv.source.ips == ["10.0.70.12"] &&
      local.firewall_rules.ha-lg-tv.destination.ips == ["10.0.40.107"] &&
      local.firewall_rules.ha-lg-tv.destination.ports == "3000,3001" &&
      local.firewall_rules.ha-lg-tv.ip_version == "IPV4" &&
      try(local.firewall_rules.ha-lg-tv.reply, true) &&
      try(local.firewall_rules.ha-lg-tv.track_state, true) &&
      !try(local.firewall_rules.ha-lg-tv.source.invert_ips, false) &&
      !try(local.firewall_rules.ha-lg-tv.destination.invert_ips, false)
    )
    error_message = "HA may initiate TCP only to the reserved LG TV's webOS ports in Home, with stateful replies."
  }
}

run "ha_iot_access_is_limited_to_the_light_and_coordinator" {
  command = plan

  assert {
    condition = (
      local.dhcp_reservations["tv-ambient"].network == "stardust" &&
      local.dhcp_reservations["tv-ambient"].ip == "10.0.50.124" &&
      local.dhcp_reservations["tv-ambient"].allow_dynamic_pool &&
      local.private_dns_records["tv-ambient"].name == "tv-ambient.thecavespace.net" &&
      local.private_dns_records["tv-ambient"].address == local.dhcp_reservations["tv-ambient"].ip &&
      toset([for name, rule in local.firewall_rules : name
        if rule.source.zone == "launchpad" && rule.destination.zone == "stardust"
      ]) == toset(["ha-tv-ambient", "ha-zigbee"]) &&
      local.firewall_rules.ha-tv-ambient.source.ips == ["10.0.70.12"] &&
      local.firewall_rules.ha-tv-ambient.destination.ips == ["10.0.50.124"] &&
      local.firewall_rules.ha-tv-ambient.destination.ports == "6668" &&
      local.firewall_rules.ha-tv-ambient.protocol == "tcp" &&
      local.firewall_rules.ha-tv-ambient.ip_version == "IPV4" &&
      try(local.firewall_rules.ha-tv-ambient.reply, true) &&
      try(local.firewall_rules.ha-tv-ambient.track_state, true) &&
      !try(local.firewall_rules.ha-tv-ambient.source.invert_ips, false) &&
      !try(local.firewall_rules.ha-tv-ambient.destination.invert_ips, false) &&
      alltrue([for rule in values(local.firewall_rules) : rule.source.zone != "stardust" || rule.destination.zone != "launchpad"])
    )
    error_message = "HA may initiate only the declared light/coordinator services; Tuya TCP6668 must target the reserved light and IoT must not initiate connections to Servers."
  }
}

run "sonoff_address_and_services_are_scoped" {
  command = plan
  assert {
    condition = (
      local.dhcp_reservations["sonoff-zigbee"].network == "stardust" &&
      local.dhcp_reservations["sonoff-zigbee"].ip == "10.0.50.182" &&
      local.dhcp_reservations["sonoff-zigbee"].allow_dynamic_pool &&
      local.private_dns_records["sonoff-zigbee"].name == "zigbee.thecavespace.net" &&
      local.private_dns_records["sonoff-zigbee"].address == local.dhcp_reservations["sonoff-zigbee"].ip &&
      toset([for name, rule in local.firewall_rules : name
        if try(rule.destination.ips == [local.dhcp_reservations["sonoff-zigbee"].ip], false)
      ]) == toset(["ha-zigbee", "admin-zigbee"]) &&
      local.firewall_rules.ha-zigbee.source.zone == "launchpad" &&
      local.firewall_rules.ha-zigbee.source.ips == ["10.0.70.12"] &&
      local.firewall_rules.ha-zigbee.destination.ports == "6638" &&
      local.firewall_rules.admin-zigbee.source.zone == "apollo" &&
      local.firewall_rules.admin-zigbee.destination.ports == "80" &&
      alltrue([for name in ["ha-zigbee", "admin-zigbee"] :
        local.firewall_rules[name].destination.zone == "stardust" &&
        local.firewall_rules[name].protocol == "tcp" &&
        local.firewall_rules[name].ip_version == "IPV4" &&
        try(local.firewall_rules[name].reply, true) &&
        try(local.firewall_rules[name].track_state, true) &&
        !try(local.firewall_rules[name].source.invert_ips, false) &&
        !try(local.firewall_rules[name].destination.invert_ips, false)
      ])
    )
    error_message = "Only HA's worker may reach coordinator TCP6638 and Admin its HTTP console, at the reserved IoT address with stateful replies."
  }
}

run "home_https_uses_only_its_private_gateway" {
  command = plan
  assert {
    condition = (
      local.private_dns_records == {
        home-assistant    = { name = "ha.thecavespace.net", address = "10.0.70.200" }
        crafty-controller = { name = "crafty-controller.thecavespace.net", address = "10.0.70.201" }
        argocd            = { name = "argocd.thecavespace.net", address = "10.0.70.201" }
        n8n               = { name = "n8n.thecavespace.net", address = "10.0.70.201" }
        n8n-webhook       = { name = "n8n-webhook.thecavespace.net", address = "10.0.70.201" }
        grafana           = { name = "grafana.thecavespace.net", address = "10.0.70.201" }
        home-assistant-backend = {
          name = "ha-backend.thecavespace.net", address = local.server_reservations["worker-01"].ip
        }
        minecraft-atm = {
          name = "atm.mc.thecavespace.net", address = local.server_reservations["worker-01"].ip
        }
        tv-ambient = {
          name = "tv-ambient.thecavespace.net", address = local.dhcp_reservations["tv-ambient"].ip
        }
        lg-tv = {
          name = "lg-tv.thecavespace.net", address = local.dhcp_reservations["lg-tv"].ip
        }
        front-door-camera = {
          name = "front-door-camera.thecavespace.net", address = local.dhcp_reservations["front-door-camera"].ip
        }
        sonoff-zigbee = {
          name = "zigbee.thecavespace.net", address = local.dhcp_reservations["sonoff-zigbee"].ip
        }
      } &&
      local.firewall_rules.home-ha-https.source.zone == "orbit" &&
      local.firewall_rules.home-ha-https.destination.ips == [local.private_dns_records["home-assistant"].address] &&
      !can(local.firewall_rules.home-ha-https.destination.clients)
    )
    error_message = "Private browser names must use their own VIP; the HA backend must use the reserved worker and Home HTTPS only the HA VIP."
  }
}

run "minecraft_name_discovers_the_private_nodeport" {
  command = plan
  assert {
    condition = local.private_dns_srv_records == {
      minecraft-atm = {
        name          = "_minecraft._tcp.atm.mc.thecavespace.net"
        target_record = "minecraft-atm"
        port          = 30000
      }
    }
    error_message = "Minecraft Java must discover port 30000 on the private worker using its owned A record."
  }
}

run "shared_media_port_uses_home" {
  command = plan
  assert {
    condition = (
      length(local.devices["voyager-01"].ports) == 6 &&
      local.devices["voyager-01"].ports.home.index == 2 &&
      local.devices["voyager-01"].ports.home.profile == "access-orbit"
    )
    error_message = "The shared media port must use Home."
  }
}

run "management_paths_preserve_admin_servers_and_ap" {
  command = plan
  assert {
    condition = (
      local.devices["flex-5"].management_network == "mission-control" &&
      local.devices["flex-8"].management_network == "mission-control" &&
      length(local.devices["flex-5"].ports) == 5 &&
      local.devices["flex-5"].ports.admin.index == 1 &&
      local.devices["flex-5"].ports.admin.profile == "access-apollo" &&
      local.devices["flex-5"].ports.admin-pc.index == 2 &&
      local.devices["flex-5"].ports.admin-pc.profile == "access-apollo" &&
      length(local.devices["flex-8"].ports) == 10 &&
      local.devices["flex-8"].ports.houston.index == 1 &&
      local.devices["flex-8"].ports.houston.profile == "access-launchpad" &&
      local.devices["voyager-01"].ports.ap.index == 4 &&
      local.devices["voyager-01"].ports.ap.profile == "ap" &&
      local.devices["voyager-01"].ports.ap.poe_mode == "auto" &&
      local.port_profiles.ap.native_network == "mission-control" &&
      toset(local.port_profiles.ap.tagged_networks) == toset(["endeavour", "orbit", "stardust", "comet", "apollo"])
    )
    error_message = "Switch management and the AP uplink must preserve Admin, server access, client tags and power."
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
        "10.0.70.0/24", "10.0.80.0/24", "10.0.90.0/24", "10.0.100.1/32", "192.168.1.1/32", "192.168.100.1/32"
      ]) && !contains(keys(local.firewall_rules), "wireguard-handshake")
    )
    error_message = "Split routes must exclude default/client routes; controller-owned WireGuard handshake rules must not be duplicated."
  }
}

run "same_vlan_nodes_need_no_router_exceptions" {
  command = plan
  assert {
    condition = (
      local.server_reservations["control-plane-01"].network == "launchpad" &&
      local.server_reservations["worker-01"].network == "launchpad" &&
      alltrue([for name in keys(local.firewall_rules) : !startswith(name, "cluster-")])
    )
    error_message = "Nodes sharing Servers must not retain inter-zone cluster exceptions."
  }
}

run "server_access_uses_reservations_and_zone_permissions" {
  command = plan
  assert {
    condition = (
      alltrue([for key, server in local.server_reservations :
        server.network == "launchpad" && local.server_ipv4_addresses[server.mac] == server.ip
      ]) &&
      local.firewall_rules["houston-01-controller"].source.zone == "launchpad" &&
      local.firewall_rules.home-ha.destination.zone == "launchpad" &&
      local.firewall_rules.home-ha.destination.clients == [local.server_macs["worker-01"]] &&
      local.devices["flex-8"].ports.worker.index == 7 &&
      local.devices["flex-8"].ports.worker.profile == "access-launchpad" &&
      local.devices["flex-8"].ports.control-plane.index == 8 &&
      local.devices["flex-8"].ports.control-plane.profile == "access-launchpad" &&
      alltrue([for key in keys(local.server_reservations) :
        !contains(keys(local.firewall_rules), "admin-${key}") &&
        !contains(keys(local.vpn_firewall_rules), "vpn-${key}")
      ]) &&
      alltrue([for rule in values(local.firewall_rules) :
        rule.source.zone != "launchpad" || rule.destination.zone != "mission-control"
      ])
    )
    error_message = "Servers must use declared reservations and shared Admin/VPN zone permissions, without blanket Management access."
  }
}

run "switch_uplinks_carry_only_required_tagged_vlans" {
  command = plan
  assert {
    condition = (
      local.port_profiles["switch-trunk"].native_network == "parking" &&
      toset(local.port_profiles["switch-trunk"].tagged_networks) == toset(["stardust", "launchpad", "apollo", "mission-control"]) &&
      alltrue([for port in [
        local.devices["voyager-01"].ports.switches,
        local.devices["flex-5"].ports.uplink,
        local.devices["flex-5"].ports.flex-8,
        local.devices["flex-8"].ports.uplink
      ] : port.profile == "switch-trunk"]) &&
      local.devices["voyager-01"].ports.switches.index == 1 &&
      local.devices["flex-5"].ports.uplink.index == 5 &&
      local.devices["flex-5"].ports.flex-8.index == 3 &&
      local.devices["flex-8"].ports.uplink.index == 9
    )
    error_message = "Both ends of each switch link must use Parking native and only IoT, Servers, Admin and Management tags."
  }
}

run "unused_lan_ports_are_parked_and_wan_is_unmanaged" {
  command = plan
  assert {
    condition = (
      local.port_profiles["access-parking"].native_network == "parking" &&
      alltrue(flatten([for device, ports in {
        flex-5     = [4]
        flex-8     = [3, 4, 5, 6, 10]
        voyager-01 = [3, 5, 6]
        } : [for port in ports :
        local.devices[device].ports["parking-${port}"].index == port &&
        local.devices[device].ports["parking-${port}"].profile == "access-parking"
      ]])) &&
      alltrue([for port in values(local.devices["voyager-01"].ports) : port.index != 7])
    )
    error_message = "Unused LAN ports must use Parking without managing the gateway WAN port."
  }
}

run "vpn_permissions_require_admin_pool" {
  command = plan
  assert {
    condition = (
      length(local.vpn_firewall_rules) == 7 &&
      alltrue([for rule in values(local.vpn_firewall_rules) :
        rule.source.zone == "vpn" && rule.source.ips == ["10.0.100.0/24"] && rule.ip_version == "IPV4" &&
        contains(["apollo", "launchpad", "mission-control", "gateway", "external"], rule.destination.zone)
        if rule.source.zone == "vpn"
      ]) &&
      local.vpn_firewall_rules.vpn-servers.destination.zone == "launchpad" &&
      local.vpn_firewall_rules.vpn-management.destination.zone == "mission-control" &&
      local.vpn_firewall_rules.vpn-gateway.destination.zone == "gateway" &&
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
