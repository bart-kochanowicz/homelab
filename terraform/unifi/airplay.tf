locals {
  airplay_receiver_names = toset(["apple-tv-01", "homepod-01", "homepod-02"])
  airplay_reservations = {
    for name in local.airplay_receiver_names : name => {
      mac     = var.airplay_receivers[name].mac
      ip      = var.airplay_receivers[name].ip
      network = "orbit"
    }
  }

  airplay_services = {
    control = { protocol = "tcp", ports = "7000" }
    media   = { protocol = "tcp_udp", ports = "49152-65535" }
  }

  airplay_firewall_rules = merge(
    {
      for name, service in local.airplay_services : "guest-airplay-${name}" => {
        description = "Guest AirPlay ${name} to selected Home receivers."
        protocol    = service.protocol
        ip_version  = "IPV4"
        source      = { zone = "comet" }
        destination = { zone = "orbit", ip_group = "airplay-devices", ports = service.ports }
      }
    },
    {
      guest-airplay-icmp-errors = {
        description = "Receiver ICMP errors related to tracked Guest AirPlay connections."
        protocol    = "icmp"
        ip_version  = "IPV4"
        reply       = false
        states      = ["RELATED"]
        source      = { zone = "orbit", ip_group = "airplay-devices" }
        destination = { zone = "comet" }
      }
    }
  )
}

# Client imports require a non-sensitive MAC ID; only this field is declassified.
import {
  for_each = local.airplay_reservations
  to       = module.airplay_reservations.unifi_client.this[each.key]
  id       = nonsensitive(each.value.mac)
}

module "airplay_reservations" {
  source = "../modules/unifi/reservations"

  site         = var.controller.site
  networks     = local.networks
  reservations = local.airplay_reservations
}
