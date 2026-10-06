mock_provider "unifi" {}

override_data {
  target = data.unifi_network.default
  values = {
    id      = "test-default-lan"
    purpose = "corporate"
    subnet  = "192.168.1.1/24"
  }
}

variables {
  controller = { url = "https://unifi.example.internal" }
  unifi_auth = { username = "test-only", password = "test-only" } # gitleaks:allow -- mock provider input
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

run "reject_default_network_key" {
  command = plan
  variables {
    networks = { default = { vlan = 40, subnet = "10.0.40.1/24" } }
  }
  expect_failures = [var.networks]
}

run "reject_default_network_name" {
  command = plan
  variables {
    networks = { orbit = { name = "Default", vlan = 40, subnet = "10.0.40.1/24" } }
  }
  expect_failures = [var.networks]
}

run "accept_non_overlapping_lan" {
  command = plan
  variables {
    networks = { orbit = { vlan = 40, subnet = "10.0.40.1/24" } }
  }
}

run "reject_default_subnet_overlap" {
  command = plan
  variables {
    networks = { orbit = { vlan = 40, subnet = "192.168.1.2/24" } }
  }
  expect_failures = [var.networks]
}

run "reject_subnet_containing_default" {
  command = plan
  variables {
    networks = { orbit = { vlan = 40, subnet = "192.168.0.1/16" } }
  }
  expect_failures = [var.networks]
}

run "reject_subnet_inside_default" {
  command = plan
  variables {
    networks = { orbit = { vlan = 40, subnet = "192.168.1.129/25" } }
  }
  expect_failures = [var.networks]
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
