mock_provider "unifi" {}

variables {
  site             = "default"
  name             = "test-wormhole"
  public_ip        = "198.51.100.10"
  subnet           = "10.0.100.0/24"
  dns_servers      = ["10.0.80.1"]
  reserved_subnets = ["10.0.80.1/24", "192.168.1.1/24", "10.244.0.0/16", "10.96.0.0/12"]
  peers = {
    macbook-01 = {
      interface_ip = "10.0.100.10"
      public_key   = "hSDwCYkwp1R0i33ctD73Wg2/Og0mOBr066SpjqqbTmo="
    }
  }
}

run "road_warrior_server_and_peer" {
  command = plan
  module {
    source = "../modules/unifi/vpn"
  }
  assert {
    condition = (
      unifi_vpn_server.this.subnet == "10.0.100.1/24" &&
      unifi_vpn_server.this.wan.ip == "198.51.100.10" &&
      unifi_vpn_server.this.wan.interface == "wan" &&
      unifi_vpn_server.this.wireguard.port == 51820 &&
      unifi_wireguard_peer.this["macbook-01"].interface_ip == "10.0.100.10" &&
      length(unifi_wireguard_peer.this["macbook-01"].allowed_ips) == 0
    )
    error_message = "The server requires a gateway CIDR; road-warrior peers must not route homelab destinations toward themselves."
  }
}

run "reject_gateway_subnet_input" {
  command = plan
  module {
    source = "../modules/unifi/vpn"
  }
  variables {
    subnet = "10.0.100.1/24"
  }
  expect_failures = [var.subnet]
}

run "reject_reserved_subnet_containment" {
  command = plan
  module {
    source = "../modules/unifi/vpn"
  }
  variables {
    reserved_subnets = ["10.0.0.0/16"]
  }
  expect_failures = [var.subnet]
}

run "reject_reserved_subnet_inside_vpn" {
  command = plan
  module {
    source = "../modules/unifi/vpn"
  }
  variables {
    reserved_subnets = ["10.0.100.128/25"]
  }
  expect_failures = [var.subnet]
}

run "reject_peer_outside_pool" {
  command = plan
  module {
    source = "../modules/unifi/vpn"
  }
  variables {
    peers = { macbook-01 = { interface_ip = "10.0.80.10", public_key = "hSDwCYkwp1R0i33ctD73Wg2/Og0mOBr066SpjqqbTmo=" } }
  }
  expect_failures = [var.peers]
}

run "reject_peer_server_address" {
  command = plan
  module {
    source = "../modules/unifi/vpn"
  }
  variables {
    peers = { macbook-01 = { interface_ip = "10.0.100.1", public_key = "hSDwCYkwp1R0i33ctD73Wg2/Og0mOBr066SpjqqbTmo=" } }
  }
  expect_failures = [var.peers]
}

run "reject_duplicate_peer_addresses" {
  command = plan
  module {
    source = "../modules/unifi/vpn"
  }
  variables {
    peers = {
      macbook-01 = { interface_ip = "10.0.100.10", public_key = "hSDwCYkwp1R0i33ctD73Wg2/Og0mOBr066SpjqqbTmo=" }
      phone-01   = { interface_ip = "10.0.100.10", public_key = "BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBA=" }
    }
  }
  expect_failures = [var.peers]
}

run "reject_duplicate_peer_keys" {
  command = plan
  module {
    source = "../modules/unifi/vpn"
  }
  variables {
    peers = {
      macbook-01 = { interface_ip = "10.0.100.10", public_key = "hSDwCYkwp1R0i33ctD73Wg2/Og0mOBr066SpjqqbTmo=" }
      phone-01   = { interface_ip = "10.0.100.11", public_key = "hSDwCYkwp1R0i33ctD73Wg2/Og0mOBr066SpjqqbTmo=" }
    }
  }
  expect_failures = [var.peers]
}

run "reject_invalid_public_key" {
  command = plan
  module {
    source = "../modules/unifi/vpn"
  }
  variables {
    peers = { macbook-01 = { interface_ip = "10.0.100.10", public_key = "not-a-wireguard-key" } }
  }
  expect_failures = [var.peers]
}

run "reject_private_endpoint" {
  command = plan
  module {
    source = "../modules/unifi/vpn"
  }
  variables {
    public_ip = "192.168.1.1"
  }
  expect_failures = [var.public_ip]
}

run "reject_extra_dns_servers" {
  command = plan
  module {
    source = "../modules/unifi/vpn"
  }
  variables {
    dns_servers = ["10.0.80.1", "1.1.1.1", "8.8.8.8"]
  }
  expect_failures = [var.dns_servers]
}

run "revoke_peer_without_replacing_server" {
  command = apply
  module {
    source = "../modules/unifi/vpn"
  }
}

run "revoke_macbook" {
  command = apply
  module {
    source = "../modules/unifi/vpn"
  }
  variables {
    peers = {}
  }
  assert {
    condition     = length(unifi_wireguard_peer.this) == 0 && output.network_id == run.revoke_peer_without_replacing_server.network_id
    error_message = "Revoking a peer must leave the server identity unchanged."
  }
}
