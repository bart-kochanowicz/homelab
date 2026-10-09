mock_provider "unifi" {}

variables {
  site          = "default"
  ap_group_id   = "test-default-ap-group"
  user_group_id = "test-default-qos-group"
  network_ids = {
    apollo = "test-admin-network"
  }
  wlans = {
    apollo = { network = "apollo", bands = ["5g"] }
  }
  passphrases = { apollo = "test-only-passphrase" } # gitleaks:allow -- mock provider input
}

run "admin_wifi_boundaries" {
  command = plan
  module {
    source = "../modules/unifi/wifi"
  }

  assert {
    condition = (
      unifi_wlan.this["apollo"].name == "cavespace-apollo" &&
      unifi_wlan.this["apollo"].network_id == "test-admin-network" &&
      unifi_wlan.this["apollo"].ap_group_ids == toset(["test-default-ap-group"]) &&
      unifi_wlan.this["apollo"].user_group_id == "test-default-qos-group"
    )
    error_message = "Admin WiFi must map to its managed network and existing AP/QoS groups."
  }

  assert {
    condition = (
      unifi_wlan.this["apollo"].security == "wpapsk" &&
      unifi_wlan.this["apollo"].wpa3_support &&
      !unifi_wlan.this["apollo"].wpa3_transition &&
      unifi_wlan.this["apollo"].pmf_mode == "required" &&
      unifi_wlan.this["apollo"].passphrase == null &&
      !unifi_wlan.this["apollo"].enhanced_iot
    )
    error_message = "Admin WiFi must require WPA3 and PMF without persisting a passphrase."
  }

  assert {
    condition = (
      unifi_wlan.this["apollo"].wlan_band == "5g" &&
      unifi_wlan.this["apollo"].wlan_bands == toset(["5g"])
    )
    error_message = "Both provider band fields must limit Admin WiFi to 5 GHz."
  }
}

run "reject_unknown_network" {
  command = plan
  module {
    source = "../modules/unifi/wifi"
  }
  variables {
    wlans = { apollo = { network = "missing", bands = ["5g"] } }
  }
  expect_failures = [var.wlans]
}

run "reject_empty_bands" {
  command = plan
  module {
    source = "../modules/unifi/wifi"
  }
  variables {
    wlans = { apollo = { network = "apollo", bands = [] } }
  }
  expect_failures = [var.wlans]
}

run "reject_short_passphrase" {
  command = plan
  module {
    source = "../modules/unifi/wifi"
  }
  variables {
    passphrases = { apollo = "short" }
  }
  expect_failures = [var.passphrases]
}

run "reject_missing_passphrase" {
  command = plan
  module {
    source = "../modules/unifi/wifi"
  }
  variables {
    passphrases = {}
  }
  expect_failures = [var.passphrases]
}

run "reject_extra_passphrase" {
  command = plan
  module {
    source = "../modules/unifi/wifi"
  }
  variables {
    passphrases = { apollo = "test-only-passphrase", other = "test-only-passphrase" } # gitleaks:allow -- mock provider input
  }
  expect_failures = [var.passphrases]
}
