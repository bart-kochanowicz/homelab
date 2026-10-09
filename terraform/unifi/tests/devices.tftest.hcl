mock_provider "unifi" {}

variables {
  site             = "default"
  port_profile_ids = { access-apollo = "test-admin-profile" }
  devices = {
    operator-switch = {
      mac = "00:11:22:AA:BB:CC"
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
      unifi_device.this["operator-switch"].mac == "00:11:22:aa:bb:cc" &&
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
        mac   = "00:11:22:aa:bb:cc"
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
        mac   = "00:11:22:aa:bb:cc"
        ports = { admin = { index = 4, profile = "access-apollo", name = "cavespace-apollo" } }
      }
      second = {
        mac   = "00:11:22:AA:BB:CC"
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
        mac = "00:11:22:aa:bb:cc"
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
        mac   = "00:11:22:aa:bb:cc"
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
        mac   = "00:11:22:aa:bb:cc"
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

run "reject_empty_ports" {
  command = plan
  module {
    source = "../modules/unifi/devices"
  }
  variables {
    devices = { switch = { mac = "00:11:22:aa:bb:cc", ports = {} } }
  }
  expect_failures = [var.devices]
}
