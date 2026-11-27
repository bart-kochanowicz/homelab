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
      unifi_wlan.this["apollo"].ap_group.mode == "all" &&
      unifi_wlan.this["apollo"].ap_group.ids == toset(["test-default-ap-group"]) &&
      unifi_wlan.this["apollo"].user_group_id == "test-default-qos-group"
    )
    error_message = "Admin WiFi must map to its managed network and existing AP/QoS groups."
  }

  assert {
    condition = (
      unifi_wlan.this["apollo"].security == "wpapsk" &&
      unifi_wlan.this["apollo"].wpa3.support &&
      !unifi_wlan.this["apollo"].wpa3.transition &&
      unifi_wlan.this["apollo"].pmf_mode == "required" &&
      unifi_wlan.this["apollo"].passphrase == null &&
      unifi_wlan.this["apollo"].passphrase_wo_version == null &&
      !unifi_wlan.this["apollo"].enhanced_iot
    )
    error_message = "Admin WiFi must require WPA3 and PMF without persisting a passphrase or resending it without a version."
  }

  assert {
    condition = (
      unifi_wlan.this["apollo"].wpa.enc == "ccmp" &&
      unifi_wlan.this["apollo"].group_rekey == 3600 &&
      !unifi_wlan.this["apollo"].bss_transition &&
      !unifi_wlan.this["apollo"].hide_ssid &&
      unifi_wlan.this["apollo"].no2ghz_oui
    )
    error_message = "Admin WiFi creation must preserve encryption, rekey, roaming, visibility and band steering without provider defaults."
  }

  assert {
    condition = (
      unifi_wlan.this["apollo"].wlan_band == "5g" &&
      unifi_wlan.this["apollo"].wlan_bands == toset(["5g"])
    )
    error_message = "Both provider band fields must limit Admin WiFi to 5 GHz."
  }
}

run "home_wifi_boundaries" {
  command = plan
  module {
    source = "../modules/unifi/wifi"
  }
  variables {
    network_ids = { orbit = "test-home-network" }
    wlans       = { orbit = { network = "orbit", bands = ["2g", "5g"] } }
    passphrases = { orbit = "test-home-passphrase" }
  }

  assert {
    condition = (
      unifi_wlan.this["orbit"].network_id == "test-home-network" &&
      unifi_wlan.this["orbit"].wpa3.support &&
      !unifi_wlan.this["orbit"].wpa3.transition &&
      unifi_wlan.this["orbit"].pmf_mode == "required" &&
      !unifi_wlan.this["orbit"].private_preshared_keys_enabled &&
      unifi_wlan.this["orbit"].wlan_bands == toset(["2g", "5g"])
    )
    error_message = "Home must use WPA3-only on both bands with required PMF, its own VLAN and PPSK disabled."
  }
}

run "iot_wifi_boundaries" {
  command = plan
  module {
    source = "../modules/unifi/wifi"
  }
  variables {
    network_ids = { stardust = "test-iot-network" }
    wlans = {
      stardust = { network = "stardust", bands = ["2g"], wpa_mode = "wpa2" }
    }
    passphrases = { stardust = "test-iot-passphrase" }
  }

  assert {
    condition = (
      unifi_wlan.this["stardust"].name == "cavespace-stardust" &&
      unifi_wlan.this["stardust"].network_id == "test-iot-network" &&
      unifi_wlan.this["stardust"].wlan_band == "2g" &&
      unifi_wlan.this["stardust"].wlan_bands == toset(["2g"])
    )
    error_message = "IoT WiFi must use its managed network on 2.4 GHz only."
  }

  assert {
    condition = (
      unifi_wlan.this["stardust"].security == "wpapsk" &&
      !unifi_wlan.this["stardust"].wpa3.support &&
      !unifi_wlan.this["stardust"].wpa3.transition &&
      unifi_wlan.this["stardust"].pmf_mode == "optional" &&
      unifi_wlan.this["stardust"].wpa.enc == "ccmp" &&
      unifi_wlan.this["stardust"].passphrase == null
    )
    error_message = "IoT WiFi must use WPA2-AES with optional PMF and a write-only passphrase."
  }
}

run "reject_unknown_wpa_mode" {
  command = plan
  module {
    source = "../modules/unifi/wifi"
  }
  variables {
    wlans = { apollo = { network = "apollo", bands = ["5g"], wpa_mode = "wpa" } }
  }
  expect_failures = [var.wlans]
}

run "rotate_passphrase_version" {
  command = plan
  module {
    source = "../modules/unifi/wifi"
  }
  variables {
    wlans = { apollo = { network = "apollo", bands = ["5g"], passphrase_version = 2 } }
  }

  assert {
    condition     = unifi_wlan.this["apollo"].passphrase_wo_version == 2
    error_message = "A rotated passphrase must raise the write-only passphrase version."
  }
}

run "reject_fractional_passphrase_version" {
  command = plan
  module {
    source = "../modules/unifi/wifi"
  }
  variables {
    wlans = { apollo = { network = "apollo", bands = ["5g"], passphrase_version = 1.5 } }
  }
  expect_failures = [var.wlans]
}

run "reject_zero_passphrase_version" {
  command = plan
  module {
    source = "../modules/unifi/wifi"
  }
  variables {
    wlans = { apollo = { network = "apollo", bands = ["5g"], passphrase_version = 0 } }
  }
  expect_failures = [var.wlans]
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
