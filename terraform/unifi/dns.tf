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
  }
}

module "private_dns" {
  source = "../modules/unifi/dns"

  site    = var.controller.site
  records = local.private_dns_records
}
