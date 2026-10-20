locals {
  private_dns_records = {
    home-assistant = {
      name    = "ha.thecavespace.net"
      address = "10.0.70.200"
    }
    crafty-controller = {
      name    = "crafty-controller.thecavespace.net"
      address = "10.0.70.201"
    }
    home-assistant-backend = {
      name    = "ha-backend.thecavespace.net"
      address = local.server_reservations["worker-01"].ip
    }
  }
}

module "private_dns" {
  source = "../modules/unifi/dns"

  site    = var.controller.site
  records = local.private_dns_records
}
