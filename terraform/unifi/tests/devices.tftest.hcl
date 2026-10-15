mock_provider "unifi" {}

variables {
  site             = "default"
  port_profile_ids = { access-apollo = "test-admin-profile" }
  devices = {
    operator-switch = {
      mac = "02:00:00:00:00:AA"
      ports = {
        admin = { index = 4, profile = "access-apollo", name = "cavespace-apollo" }
      }
    }
  }
}

run "declared_admin_port" {
  command = plan
  module {
    source = "../modules/unifi/devices"
  }

  assert {
    condition = (
      length(unifi_device.this) == 1 &&
      unifi_device.this["operator-switch"].mac == "02:00:00:00:00:aa" &&
      length(unifi_device.this["operator-switch"].port_override) == 1 &&
      one(unifi_device.this["operator-switch"].port_override).index == 4 &&
      one(unifi_device.this["operator-switch"].port_override).name == "cavespace-apollo" &&
      one(unifi_device.this["operator-switch"].port_override).port_profile_id == "test-admin-profile"
    )
    error_message = "Only the declared Admin port must receive its profile and name."
  }

  assert {
    condition = (
      !unifi_device.this["operator-switch"].allow_adoption &&
      !unifi_device.this["operator-switch"].forget_on_destroy
    )
    error_message = "Port management must not adopt or forget devices."
  }
}

run "reject_unknown_profile" {
  command = plan
  module {
    source = "../modules/unifi/devices"
  }
  variables {
    devices = {
      switch = {
        mac   = "02:00:00:00:00:aa"
        ports = { admin = { index = 4, profile = "missing", name = "cavespace-apollo" } }
      }
    }
  }
  expect_failures = [var.devices]
}

run "reject_duplicate_mac" {
  command = plan
  module {
    source = "../modules/unifi/devices"
  }
  variables {
    devices = {
      first = {
        mac   = "02:00:00:00:00:aa"
        ports = { admin = { index = 4, profile = "access-apollo", name = "cavespace-apollo" } }
      }
      second = {
        mac   = "02:00:00:00:00:AA"
        ports = { admin = { index = 5, profile = "access-apollo", name = "cavespace-apollo" } }
      }
    }
  }
  expect_failures = [var.devices]
}

run "reject_duplicate_port_index" {
  command = plan
  module {
    source = "../modules/unifi/devices"
  }
  variables {
    devices = {
      switch = {
        mac = "02:00:00:00:00:aa"
        ports = {
          admin     = { index = 4, profile = "access-apollo", name = "cavespace-apollo" }
          duplicate = { index = 4, profile = "access-apollo", name = "duplicate" }
        }
      }
    }
  }
  expect_failures = [var.devices]
}

run "reject_fractional_port_index" {
  command = plan
  module {
    source = "../modules/unifi/devices"
  }
  variables {
    devices = {
      switch = {
        mac   = "02:00:00:00:00:aa"
        ports = { admin = { index = 4.5, profile = "access-apollo", name = "cavespace-apollo" } }
      }
    }
  }
  expect_failures = [var.devices]
}

run "reject_nonpositive_port_index" {
  command = plan
  module {
    source = "../modules/unifi/devices"
  }
  variables {
    devices = {
      switch = {
        mac   = "02:00:00:00:00:aa"
        ports = { admin = { index = 0, profile = "access-apollo", name = "cavespace-apollo" } }
      }
    }
  }
  expect_failures = [var.devices]
}

run "reject_invalid_mac" {
  command = plan
  module {
    source = "../modules/unifi/devices"
  }
  variables {
    devices = {
      switch = {
        mac   = "not-a-mac"
        ports = { admin = { index = 4, profile = "access-apollo", name = "cavespace-apollo" } }
      }
    }
  }
  expect_failures = [var.devices]
}

run "management_only_device" {
  command = plan
  module {
    source = "../modules/unifi/devices"
  }
  variables {
    network_ids = { management = "test-management" }
    devices = {
      switch = { mac = "02:00:00:00:00:aa", management_network = "management" }
    }
  }
  assert {
    condition = (
      unifi_device.this["switch"].mgmt_network_id == "test-management" &&
      length(unifi_device.this["switch"].port_override) == 0 &&
      !unifi_device.this["switch"].allow_adoption && !unifi_device.this["switch"].forget_on_destroy
    )
    error_message = "Tagged management must not introduce port overrides, adoption or forgetting."
  }
}

run "ap_port_preserves_power" {
  command = plan
  module {
    source = "../modules/unifi/devices"
  }
  variables {
    port_profile_ids = { ap = "test-ap-profile" }
    devices = {
      gateway = {
        mac = "02:00:00:00:00:aa"
        ports = {
          ap = { index = 4, profile = "ap", name = "cavespace-ap", poe_mode = "auto" }
        }
      }
    }
  }
  assert {
    condition = (
      one(unifi_device.this["gateway"].port_override).index == 4 &&
      one(unifi_device.this["gateway"].port_override).port_profile_id == "test-ap-profile" &&
      one(unifi_device.this["gateway"].port_override).autoneg &&
      one(unifi_device.this["gateway"].port_override).poe_mode == "auto"
    )
    error_message = "The AP port must keep automatic PoE while assigning its VLAN profile."
  }
}

run "reject_unknown_management_network" {
  command = plan
  module {
    source = "../modules/unifi/devices"
  }
  variables {
    devices = {
      switch = { mac = "02:00:00:00:00:aa", management_network = "missing" }
    }
  }
  expect_failures = [var.devices]
}

run "reject_unmanaged_device" {
  command = plan
  module {
    source = "../modules/unifi/devices"
  }
  variables {
    devices = { switch = { mac = "02:00:00:00:00:aa", ports = {} } }
  }
  expect_failures = [var.devices]
}
