mock_provider "unifi" {}

variables {
  site = "default"
}

run "valid_lan_networks" {
  command = plan
  module {
    source = "../modules/unifi"
  }
  variables {
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
}

run "reject_wan_vlan" {
  command = plan
  module {
    source = "../modules/unifi"
  }
  variables {
    networks = { wan = { vlan = 35, subnet = "10.0.35.1/24" } }
  }
  expect_failures = [var.networks]
}

run "reject_duplicate_vlans" {
  command = plan
  module {
    source = "../modules/unifi"
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
    source = "../modules/unifi"
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
    source = "../modules/unifi"
  }
  variables {
    networks = { orbit = { vlan = 40, subnet = "8.8.8.1/24" } }
  }
  expect_failures = [var.networks]
}

run "reject_dhcp_outside_subnet" {
  command = plan
  module {
    source = "../modules/unifi"
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
    source = "../modules/unifi"
  }
  variables {
    networks = { orbit = { vlan = 40, subnet = "10.0.40.1/7" } }
  }
  expect_failures = [var.networks]
}

run "reject_reversed_dhcp_pool" {
  command = plan
  module {
    source = "../modules/unifi"
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
    source = "../modules/unifi"
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
