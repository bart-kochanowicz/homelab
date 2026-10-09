mock_provider "unifi" {}

override_data {
  target = data.unifi_network.default
  values = {
    id      = "test-default-lan"
    purpose = "corporate"
    subnet  = "192.168.1.1/24"
  }
}

override_resource {
  target = module.devices.unifi_device.this["flex-5"]
  values = {
    id  = "74:f9:2c:96:c2:cc"
    mac = "74:f9:2c:96:c2:cc"
  }
}

override_module {
  target = module.port_profiles
  outputs = {
    port_profile_ids = { access-apollo = "test-admin-profile" }
  }
}

variables {
  controller       = { url = "https://unifi.example.internal" }
  unifi_auth       = { username = "test-only", password = "test-only" } # gitleaks:allow -- mock provider input
  wifi_passphrases = { apollo = "test-only-passphrase", endeavour = "test-work-passphrase" }
  wifi_ppsks = {
    "orbit/home"  = "test-home-passphrase"
    "orbit/iot"   = "test-iot-passphrase"
    "orbit/guest" = "test-guest-passphrase"
  }
}

run "local_authentication" {
  command = plan
}

run "api_key_authentication" {
  command = plan
  variables {
    unifi_auth = { api_key = "test-only" }
  }
}

run "reject_http_controller" {
  command = plan
  variables {
    controller = { url = "http://unifi.example.internal" }
  }
  expect_failures = [var.controller]
}

run "reject_credentials_in_url" {
  command = plan
  variables {
    controller = { url = "https://user:password@unifi.example.internal" }
  }
  expect_failures = [var.controller]
}

run "reject_missing_authentication" {
  command = plan
  variables {
    unifi_auth = {}
  }
  expect_failures = [var.unifi_auth]
}

run "reject_mixed_authentication" {
  command = plan
  variables {
    unifi_auth = { username = "test-only", password = "test-only", api_key = "test-only" } # gitleaks:allow -- mock provider input
  }
  expect_failures = [var.unifi_auth]
}

run "reject_wan_named_default" {
  command = plan
  override_data {
    target = data.unifi_network.default
    values = {
      id      = "test-wan"
      purpose = "wan"
      subnet  = "192.168.1.1/24"
    }
  }
  expect_failures = [data.unifi_network.default]
}
