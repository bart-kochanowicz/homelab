mock_provider "unifi" {}

variables {
  site = "default"
  network_ids = {
    orbit           = "test-home"
    launchpad       = "test-servers"
    mission-control = "test-management"
    parking         = "test-parking"
  }
  reserved_network_ids = ["test-default"]
  port_profiles = {
    access = { native_network = "orbit" }
    ap = {
      native_network  = "mission-control"
      tagged_networks = ["orbit"]
    }
    trunk = {
      native_network  = "parking"
      tagged_networks = ["launchpad", "mission-control"]
    }
  }
}

run "port_boundaries" {
  command = plan
  module {
    source = "../modules/unifi/port-profiles"
  }

  assert {
    condition = (
      unifi_port_profile.this["access"].native_networkconf_id == "test-home" &&
      unifi_port_profile.this["access"].forward == "native" &&
      unifi_port_profile.this["access"].tagged_vlan_mgmt == "block_all"
    )
    error_message = "An access port must assign Home and reject tagged VLANs."
  }
  assert {
    condition = (
      unifi_port_profile.this["ap"].native_networkconf_id == "test-management" &&
      unifi_port_profile.this["ap"].tagged_vlan_mgmt == "custom" &&
      unifi_port_profile.this["ap"].excluded_networkconf_ids == toset(["test-default", "test-servers", "test-parking"])
    )
    error_message = "The AP profile must exclude Servers, Default and parking without excluding its native or allowed tagged networks."
  }
  assert {
    condition = (
      unifi_port_profile.this["trunk"].native_networkconf_id == "test-parking" &&
      unifi_port_profile.this["trunk"].excluded_networkconf_ids == toset(["test-home", "test-default"])
    )
    error_message = "The server trunk must allow only Servers and Management tags."
  }
}

run "reject_native_tag" {
  command = plan
  module {
    source = "../modules/unifi/port-profiles"
  }
  variables {
    port_profiles = { invalid = { native_network = "orbit", tagged_networks = ["orbit"] } }
  }
  expect_failures = [var.port_profiles]
}

run "reject_unknown_tag" {
  command = plan
  module {
    source = "../modules/unifi/port-profiles"
  }
  variables {
    port_profiles = { invalid = { native_network = "orbit", tagged_networks = ["missing"] } }
  }
  expect_failures = [var.port_profiles]
}
