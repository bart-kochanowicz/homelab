resource "unifi_vpn_server" "this" {
  site    = var.site
  name    = var.name
  enabled = true
  subnet  = "${cidrhost(var.subnet, 1)}/${split("/", var.subnet)[1]}"

  wan = {
    ip        = var.public_ip
    interface = "wan"
  }
  dns = {
    enabled = true
    servers = var.dns_servers
  }
  wireguard = {
    port = var.port
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "wireguard_asymmetric_key" "server" {
  private_key = unifi_vpn_server.this.wireguard.private_key

  lifecycle {
    precondition {
      condition     = unifi_vpn_server.this.wireguard.private_key != null
      error_message = "UniFi must retain the server private key for public key derivation."
    }
  }
}

resource "unifi_wireguard_peer" "this" {
  for_each = var.peers

  site         = var.site
  network_id   = unifi_vpn_server.this.id
  name         = each.key
  interface_ip = each.value.interface_ip
  public_key   = each.value.public_key
  # Additional routes toward a peer; client split routes are configured separately.
  allowed_ips = []
}
