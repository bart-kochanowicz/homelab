mock_provider "unifi" {}

override_resource {
  override_during = plan
  target          = unifi_network.this["orbit"]
  values          = { id = "test-home" }
}
override_resource {
  override_during = plan
  target          = unifi_network.this["launchpad"]
  values          = { id = "test-servers" }
}
override_resource {
  override_during = plan
  target          = unifi_network.this["mission-control"]
  values          = { id = "test-management" }
}
override_resource {
  override_during = plan
  target          = unifi_network.vlan_only["parking"]
  values          = { id = "test-parking" }
}

variables {
  site = "default"
  networks = {
    orbit = {
      vlan   = 40
      subnet = "10.0.40.1/24"
      dhcp   = { start = "10.0.40.100", stop = "10.0.40.199" }
    }
    launchpad       = { vlan = 70, subnet = "10.0.70.1/24" }
    mission-control = { vlan = 90, subnet = "10.0.90.1/24" }
  }
  vlan_only_networks = { parking = 999 }
  reserved_networks = {
    default = { id = "test-default", subnet = "192.168.1.1/24" }
  }
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

run "port_boundaries_and_dhcp" {
  command = plan
  module {
    source = "../modules/unifi"
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

run "reject_native_tag" {
  command = plan
  module {
    source = "../modules/unifi"
  }
  variables {
    port_profiles = { invalid = { native_network = "orbit", tagged_networks = ["orbit"] } }
  }
  expect_failures = [var.port_profiles]
}

run "reject_unknown_tag" {
  command = plan
  module {
    source = "../modules/unifi"
  }
  variables {
    port_profiles = { invalid = { native_network = "orbit", tagged_networks = ["missing"] } }
  }
  expect_failures = [var.port_profiles]
}

run "reject_parking_vlan_collision" {
  command = plan
  module {
    source = "../modules/unifi"
  }
  variables {
    vlan_only_networks = { parking = 40 }
  }
  expect_failures = [var.vlan_only_networks]
}

run "reject_unrouted_wan_vlan" {
  command = plan
  module {
    source = "../modules/unifi"
  }
  variables {
    vlan_only_networks = { parking = 35 }
  }
  expect_failures = [var.vlan_only_networks]
}
