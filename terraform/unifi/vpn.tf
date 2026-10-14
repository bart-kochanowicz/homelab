locals {
  vpn_subnet = "10.0.100.0/24"
  vpn_port   = 51820
  vpn_peers = {
    macbook-01 = {
      interface_ip = "10.0.100.10"
      public_key   = "z97bFYfOsnEsM4gwO+G81k9IZx+GRVzwxrxWURwmuzQ="
    }
  }

  vpn_client_routes = sort(distinct(concat(
    [for key in ["apollo", "launchpad", "mission-control"] :
      "${cidrhost(local.networks[key].subnet, 0)}/${split("/", local.networks[key].subnet)[1]}"
    ],
    ["${cidrhost(local.vpn_subnet, 1)}/32", "${split("/", data.unifi_network.default.subnet)[0]}/32", "192.168.100.1/32"],
    [for server in data.unifi_client_info.server : "${server.ip}/32" if server.network_id == data.unifi_network.default.id]
  )))
}

module "vpn" {
  source = "../modules/unifi/vpn"

  site        = var.controller.site
  name        = "${var.name_prefix}wormhole"
  subnet      = local.vpn_subnet
  public_ip   = "87.205.15.64"
  port        = local.vpn_port
  peers       = local.vpn_peers
  dns_servers = [split("/", local.networks.apollo.subnet)[0]]
  reserved_subnets = concat(
    [for network in values(local.networks) : network.subnet],
    [data.unifi_network.default.subnet, "192.168.100.0/24", "10.244.0.0/16", "10.96.0.0/12"]
  )
}
