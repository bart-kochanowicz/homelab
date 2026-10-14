data "unifi_firewall_zone" "builtin" {
  for_each = {
    internal = "Internal"
    external = "External"
    gateway  = "Gateway"
    vpn      = "Vpn"
    hotspot  = "Hotspot"
    dmz      = "Dmz"
  }

  site = var.controller.site
  name = each.value
}

data "unifi_client_info" "server" {
  for_each = local.server_macs

  site = var.controller.site
  mac  = each.value

  lifecycle {
    postcondition {
      condition = contains(
        [data.unifi_network.default.id, module.networks.network_ids["launchpad"]],
        self.network_id
      )
      error_message = "Registered servers must belong to Default or launchpad."
    }

    postcondition {
      condition     = can(cidrnetmask("${self.ip}/32"))
      error_message = "Registered servers must report a valid IPv4 address for firewall selectors."
    }
  }
}

locals {
  firewall_zone_network_ids = {
    for key in keys(local.vlan_ids) : key => concat(
      [module.networks.network_ids[key]], key == "apollo" ? [module.vpn.network_id] : []
    )
  }

  server_macs = {
    houston-01       = "02:00:00:00:00:10"
    control-plane-01 = "02:00:00:00:00:11"
    worker-01        = "02:00:00:00:00:12"
  }

  server_zones = {
    for key, server in data.unifi_client_info.server : key =>
    server.network_id == data.unifi_network.default.id ? "internal" : "launchpad"
  }

  server_ipv4_addresses = {
    for key, server in data.unifi_client_info.server : local.server_macs[key] => server.ip
  }

  non_public_destinations = [
    "0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8",
    "169.254.0.0/16", "172.16.0.0/12", "192.168.0.0/16", "224.0.0.0/4", "240.0.0.0/4",
    "::/128", "::1/128", "fc00::/7", "fe80::/10", "ff00::/8"
  ]

  firewall_rules = merge(
    {
      for zone in ["endeavour", "orbit", "stardust", "comet", "launchpad", "apollo"] : "${zone}-internet" => {
        description = "${zone} to public Internet destinations."
        source      = { zone = zone }
        destination = { zone = "external", ips = local.non_public_destinations, invert_ips = true }
      }
    },
    {
      wireguard-handshake = {
        description = "Public WireGuard handshake to the gateway."
        protocol    = "udp"
        ip_version  = "IPV4"
        source      = { zone = "external" }
        destination = { zone = "gateway", ports = tostring(local.vpn_port) }
      }
      management-web = {
        description = "Infrastructure web updates and vendor services."
        protocol    = "tcp"
        source      = { zone = "mission-control" }
        destination = { zone = "external", ips = local.non_public_destinations, invert_ips = true, ports = "80,443" }
      }
      management-ntp = {
        description = "Infrastructure time synchronization."
        protocol    = "udp"
        source      = { zone = "mission-control" }
        destination = { zone = "external", ips = local.non_public_destinations, invert_ips = true, ports = "123" }
      }
      admin-servers = {
        description = "Admin access to Servers."
        source      = { zone = "apollo" }
        destination = { zone = "launchpad" }
      }
      admin-management = {
        description = "Admin access to network infrastructure."
        source      = { zone = "apollo" }
        destination = { zone = "mission-control" }
      }
      admin-gateway = {
        description = "Admin access to gateway administration."
        source      = { zone = "apollo" }
        destination = { zone = "gateway" }
      }
      admin-ont = {
        description = "Admin access to WAN-side LEOX management."
        ip_version  = "IPV4"
        source      = { zone = "apollo" }
        destination = { zone = "external", ips = ["192.168.100.1"] }
      }
      servers-management = {
        description = "Infrastructure collection; owner: homelab operator; review when collector services are defined."
        source      = { zone = "launchpad" }
        destination = { zone = "mission-control" }
      }
      houston-01-controller = {
        description = "Houston Terraform access to the UniFi HTTPS API."
        protocol    = "tcp"
        source      = { zone = local.server_zones["houston-01"], clients = [local.server_macs["houston-01"]] }
        destination = { zone = "gateway", ports = "443" }
      }
      home-ha = {
        description = "Home access to Home Assistant."
        protocol    = "tcp"
        ip_version  = "IPV4"
        source      = { zone = "orbit" }
        destination = { zone = local.server_zones["worker-01"], clients = [local.server_macs["worker-01"]], ports = "8123" }
      }
      management-inform = {
        description = "Infrastructure inform traffic to the Network controller."
        protocol    = "tcp"
        source      = { zone = "mission-control" }
        destination = { zone = "gateway", ports = "8080" }
      }
      management-stun = {
        description = "Infrastructure STUN traffic to the Network controller."
        protocol    = "udp"
        source      = { zone = "mission-control" }
        destination = { zone = "gateway", ports = "3478" }
      }
    },
    {
      for key, mac in local.server_macs : "admin-${key}" => {
        description = "Admin access to registered server ${key}."
        source      = { zone = "apollo" }
        destination = { zone = local.server_zones[key], clients = [mac] }
      }
    },
    {
      for key in ["control-plane-01", "worker-01"] : "home-minecraft-${key}" => {
        description = "Home access to the Minecraft NodePort."
        protocol    = "tcp"
        ip_version  = "IPV4"
        source      = { zone = "orbit" }
        destination = { zone = local.server_zones[key], clients = [local.server_macs[key]], ports = "30000" }
      }
    },
    {
      for zone in keys(local.vlan_ids) : "${zone}-dns" => {
        description = "${zone} gateway DNS."
        protocol    = "tcp_udp"
        source      = { zone = zone }
        destination = { zone = "gateway", ports = "53" }
      }
    },
    {
      for zone in keys(local.vlan_ids) : "${zone}-ntp" => {
        description = "${zone} gateway time service."
        protocol    = "udp"
        source      = { zone = zone }
        destination = { zone = "gateway", ports = "123" }
      }
    },
    {
      for zone in keys(local.vlan_ids) : "${zone}-dhcp-request" => {
        description = "${zone} DHCP requests."
        protocol    = "udp"
        ip_version  = "IPV4"
        reply       = false
        track_state = false
        source      = { zone = zone, ports = "68" }
        destination = { zone = "gateway", ports = "67" }
      }
    },
    {
      for zone in keys(local.vlan_ids) : "${zone}-dhcp-offer" => {
        description = "${zone} DHCP offers and acknowledgements."
        protocol    = "udp"
        ip_version  = "IPV4"
        reply       = false
        track_state = false
        source      = { zone = "gateway", ports = "67" }
        destination = { zone = zone, ports = "68" }
      }
    },
    {
      for zone in keys(local.vlan_ids) : "${zone}-icmpv6-to-gateway" => {
        description = "${zone} local ICMPv6, including neighbor discovery."
        protocol    = "icmpv6"
        ip_version  = "IPV6"
        reply       = false
        track_state = false
        source      = { zone = zone }
        destination = { zone = "gateway" }
      }
    },
    {
      for zone in keys(local.vlan_ids) : "${zone}-icmpv6-from-gateway" => {
        description = "Gateway local ICMPv6, including neighbor discovery."
        protocol    = "icmpv6"
        ip_version  = "IPV6"
        reply       = false
        track_state = false
        source      = { zone = "gateway" }
        destination = { zone = zone }
      }
    },
    {
      for zone in keys(local.vlan_ids) : "${zone}-gateway-icmp-errors" => {
        description = "Gateway ICMP errors related to tracked ${zone} connections."
        protocol    = "icmp"
        ip_version  = "IPV4"
        reply       = false
        states      = ["RELATED"]
        source      = { zone = "gateway" }
        destination = { zone = zone }
      }
    },
    {
      for zone in keys(local.vlan_ids) : "${zone}-internet-icmp-errors" => {
        description = "Internet ICMP errors related to tracked ${zone} connections."
        protocol    = "icmp"
        ip_version  = "IPV4"
        reply       = false
        states      = ["RELATED"]
        source      = { zone = "external" }
        destination = { zone = zone }
      }
    },
    {
      for zone in keys(local.vlan_ids) : "${zone}-internet-icmpv6-errors" => {
        description = "Internet ICMPv6 errors related to tracked ${zone} connections."
        protocol    = "icmpv6"
        ip_version  = "IPV6"
        reply       = false
        states      = ["RELATED"]
        source      = { zone = "external" }
        destination = { zone = zone }
      }
    },
    {
      for key in ["control-plane-01", "worker-01"] : "home-${key}-icmp-errors" => {
        description = "Registered server ICMP errors related to tracked Home connections."
        protocol    = "icmp"
        ip_version  = "IPV4"
        reply       = false
        states      = ["RELATED"]
        source      = { zone = local.server_zones[key], clients = [local.server_macs[key]] }
        destination = { zone = "orbit" }
      }
    }
  )
}

module "firewall" {
  source = "../modules/unifi/firewall"

  site                  = var.controller.site
  name_prefix           = var.name_prefix
  zone_network_ids      = local.firewall_zone_network_ids
  builtin_zone_ids      = { for key, zone in data.unifi_firewall_zone.builtin : key => zone.id }
  client_ipv4_addresses = local.server_ipv4_addresses
  rules                 = local.firewall_rules
}
