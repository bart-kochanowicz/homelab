mock_provider "unifi" {}

variables {
  site             = "default"
  reserved_subnets = ["192.168.1.1/24"]
}

run "valid_lan_networks" {
  command = plan
  module {
    source = "../modules/unifi/networks"
  }
  variables {
    vlan_only_networks = { parking = 999 }
    networks = {
      orbit = {
        vlan   = 40
        subnet = "10.0.40.1/24"
        dhcp   = { start = "10.0.40.100", stop = "10.0.40.199" }
      }
      comet = {
        vlan   = 60
        subnet = "10.0.60.1/24"
      }
    }
  }
  assert {
    condition = (
      unifi_network.vlan_only["parking"].subnet == null &&
      unifi_network.vlan_only["parking"].purpose == "vlan-only" &&
      unifi_network.vlan_only["parking"].dhcp_server.enabled == false
    )
    error_message = "Parking must have no gateway or DHCP server."
  }
  assert {
    condition = (
      unifi_network.this["orbit"].dhcp_server.dns_enabled &&
      unifi_network.this["orbit"].dhcp_server.dns_servers == tolist(["10.0.40.1"]) &&
      !unifi_network.this["orbit"].auto_scale &&
      unifi_network.this["orbit"].setting_preference == "manual"
    )
    error_message = "DHCP must advertise the LAN gateway as DNS and preserve explicit addressing."
  }
}

run "reject_wan_vlan" {
  command = plan
  module {
    source = "../modules/unifi/networks"
  }
  variables {
    networks = { wan = { vlan = 35, subnet = "10.0.35.1/24" } }
  }
  expect_failures = [var.networks]
}

run "reject_duplicate_vlans" {
  command = plan
  module {
    source = "../modules/unifi/networks"
  }
  variables {
    networks = {
      orbit = { vlan = 40, subnet = "10.0.40.1/24" }
      comet = { vlan = 40, subnet = "10.0.60.1/24" }
    }
  }
  expect_failures = [var.networks]
}

run "reject_overlapping_subnets" {
  command = plan
  module {
    source = "../modules/unifi/networks"
  }
  variables {
    networks = {
      broad  = { vlan = 40, subnet = "10.0.0.1/16" }
      narrow = { vlan = 60, subnet = "10.0.60.1/24" }
    }
  }
  expect_failures = [var.networks]
}

run "reject_public_subnet" {
  command = plan
  module {
    source = "../modules/unifi/networks"
  }
  variables {
    networks = { orbit = { vlan = 40, subnet = "8.8.8.1/24" } }
  }
  expect_failures = [var.networks]
}

run "reject_dhcp_outside_subnet" {
  command = plan
  module {
    source = "../modules/unifi/networks"
  }
  variables {
    networks = {
      orbit = {
        vlan   = 40
        subnet = "10.0.40.1/24"
        dhcp   = { start = "10.0.50.100", stop = "10.0.50.199" }
      }
    }
  }
  expect_failures = [var.networks]
}

run "reject_subnet_spanning_public_addresses" {
  command = plan
  module {
    source = "../modules/unifi/networks"
  }
  variables {
    networks = { orbit = { vlan = 40, subnet = "10.0.40.1/7" } }
  }
  expect_failures = [var.networks]
}

run "reject_reversed_dhcp_pool" {
  command = plan
  module {
    source = "../modules/unifi/networks"
  }
  variables {
    networks = {
      orbit = {
        vlan   = 40
        subnet = "10.0.40.1/24"
        dhcp   = { start = "10.0.40.199", stop = "10.0.40.100" }
      }
    }
  }
  expect_failures = [var.networks]
}

run "reject_gateway_in_dhcp_pool" {
  command = plan
  module {
    source = "../modules/unifi/networks"
  }
  variables {
    networks = {
      orbit = {
        vlan   = 40
        subnet = "10.0.40.128/24"
        dhcp   = { start = "10.0.40.100", stop = "10.0.40.199" }
      }
    }
  }
  expect_failures = [var.networks]
}

run "reject_default_network_key" {
  command = plan
  module {
    source = "../modules/unifi/networks"
  }
  variables {
    networks = { default = { vlan = 40, subnet = "10.0.40.1/24" } }
  }
  expect_failures = [var.networks]
}

run "reject_default_network_name" {
  command = plan
  module {
    source = "../modules/unifi/networks"
  }
  variables {
    networks = { orbit = { name = "Default", vlan = 40, subnet = "10.0.40.1/24" } }
  }
  expect_failures = [var.networks]
}

run "accept_non_overlapping_lan" {
  command = plan
  module {
    source = "../modules/unifi/networks"
  }
  variables {
    networks = { orbit = { vlan = 40, subnet = "10.0.40.1/24" } }
  }
}

run "reject_default_subnet_overlap" {
  command = plan
  module {
    source = "../modules/unifi/networks"
  }
  variables {
    networks = { orbit = { vlan = 40, subnet = "192.168.1.2/24" } }
  }
  expect_failures = [var.networks]
}

run "reject_subnet_containing_default" {
  command = plan
  module {
    source = "../modules/unifi/networks"
  }
  variables {
    networks = { orbit = { vlan = 40, subnet = "192.168.0.1/16" } }
  }
  expect_failures = [var.networks]
}

run "reject_subnet_inside_default" {
  command = plan
  module {
    source = "../modules/unifi/networks"
  }
  variables {
    networks = { orbit = { vlan = 40, subnet = "192.168.1.129/25" } }
  }
  expect_failures = [var.networks]
}

run "reject_parking_vlan_collision" {
  command = plan
  module {
    source = "../modules/unifi/networks"
  }
  variables {
    networks           = { orbit = { vlan = 40, subnet = "10.0.40.1/24" } }
    vlan_only_networks = { parking = 40 }
  }
  expect_failures = [var.vlan_only_networks]
}

run "reject_unrouted_wan_vlan" {
  command = plan
  module {
    source = "../modules/unifi/networks"
  }
  variables {
    vlan_only_networks = { parking = 35 }
  }
  expect_failures = [var.vlan_only_networks]
}
