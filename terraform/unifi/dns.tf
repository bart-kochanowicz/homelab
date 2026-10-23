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
    argocd = {
      name    = "argocd.thecavespace.net"
      address = "10.0.70.201"
    }
    n8n = {
      name    = "n8n.thecavespace.net"
      address = "10.0.70.201"
    }
    n8n-webhook = {
      name    = "n8n-webhook.thecavespace.net"
      address = "10.0.70.201"
    }
    grafana = {
      name    = "grafana.thecavespace.net"
      address = "10.0.70.201"
    }
    home-assistant-backend = {
      name    = "ha-backend.thecavespace.net"
      address = local.server_reservations["worker-01"].ip
    }
    minecraft-atm = {
      name    = "atm.mc.thecavespace.net"
      address = local.server_reservations["worker-01"].ip
    }
  }

  private_dns_srv_records = {
    minecraft-atm = {
      name          = "_minecraft._tcp.atm.mc.thecavespace.net"
      target_record = "minecraft-atm"
      port          = 30000
    }
  }
}

module "private_dns" {
  source = "../modules/unifi/dns"

  site        = var.controller.site
  records     = local.private_dns_records
  srv_records = local.private_dns_srv_records
}
