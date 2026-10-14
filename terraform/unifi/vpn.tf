locals {
  vpn_subnet = "10.0.100.0/24"
  vpn_port   = 51820
  vpn_peers = {
    macbook-01 = {
      interface_ip = "10.0.100.10"
      public_key   = "hSDwCYkwp1R0i33ctD73Wg2/Og0mOBr066SpjqqbTmo="
    }
  }

  vpn_client_routes = sort(distinct(concat(
    [for key in ["apollo", "launchpad", "mission-control"] :
      "${cidrhost(local.networks[key].subnet, 0)}/${split("/", local.networks[key].subnet)[1]}"
    ],
    ["${cidrhost(local.vpn_subnet, 1)}/32", "${split("/", data.unifi_network.default.subnet)[0]}/32", "192.168.100.1/32"],
    [for server in data.unifi_client_info.server : "${server.ip}/32" if server.network_id == data.unifi_network.default.id]
  )))

  vpn_firewall_rules = merge(
    {
      for key, destination in {
        servers    = { zone = "launchpad" }
        management = { zone = "mission-control" }
        gateway    = { zone = "gateway" }
        admin      = { zone = "apollo" }
        ont        = { zone = "external", ips = ["192.168.100.1"] }
        internet   = { zone = "external", ips = [for cidr in local.non_public_destinations : cidr if !strcontains(cidr, ":")], invert_ips = true }
        } : "vpn-${key}" => {
        description = "Administrative WireGuard access to ${key}."
        ip_version  = "IPV4"
        source      = { zone = "vpn", ips = [local.vpn_subnet] }
        destination = destination
      }
    },
    {
      for key, mac in local.server_macs : "vpn-${key}" => {
        description = "Administrative WireGuard access to registered server ${key}."
        ip_version  = "IPV4"
        source      = { zone = "vpn", ips = [local.vpn_subnet] }
        destination = { zone = local.server_zones[key], clients = [mac] }
      }
    },
    {
      vpn-internet-icmp-errors = {
        description = "Internet ICMP errors related to tracked administrative VPN connections."
        protocol    = "icmp"
        ip_version  = "IPV4"
        reply       = false
        states      = ["RELATED"]
        source      = { zone = "external" }
        destination = { zone = "vpn", ips = [local.vpn_subnet] }
      }
    }
  )
}

module "vpn" {
  source = "../modules/unifi/vpn"

  site        = var.controller.site
  name        = "${var.name_prefix}wormhole"
  subnet      = local.vpn_subnet
  public_ip   = var.vpn_public_ip
  port        = local.vpn_port
  peers       = local.vpn_peers
  dns_servers = [split("/", local.networks.apollo.subnet)[0]]
  reserved_subnets = concat(
    [for network in values(local.networks) : network.subnet],
    [data.unifi_network.default.subnet, "192.168.100.0/24", "10.244.0.0/16", "10.96.0.0/12"]
  )
}
