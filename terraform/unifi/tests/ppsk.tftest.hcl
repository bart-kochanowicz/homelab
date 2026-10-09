mock_provider "unifi" {}

variables {
  site                 = "default"
  ap_group_id          = "test-default-ap-group"
  user_group_id        = "test-default-qos-group"
  ppsk_base_network_id = "test-default-network"
  network_ids = {
    endeavour = "test-work-network"
    orbit     = "test-home-network"
    stardust  = "test-iot-network"
    comet     = "test-guest-network"
  }
  wlans = {
    endeavour = { network = "endeavour", bands = ["2g", "5g"] }
  }
  passphrases = { endeavour = "test-work-passphrase" }
  ppsk_wlans = {
    orbit = {
      bands = ["2g", "5g"]
      keys  = { home = "orbit", iot = "stardust", guest = "comet" }
    }
  }
  ppsk_passphrases = {
    "orbit/home"  = "test-home-passphrase"
    "orbit/iot"   = "test-iot-passphrase"
    "orbit/guest" = "test-guest-passphrase"
  }
}

run "work_and_ppsk_boundaries" {
  command = plan
  module {
    source = "../modules/unifi/wifi"
  }

  assert {
    condition = (
      unifi_wlan.this["endeavour"].network_id == "test-work-network" &&
      unifi_wlan.this["endeavour"].wpa3_support &&
      !unifi_wlan.this["endeavour"].wpa3_transition &&
      unifi_wlan.this["endeavour"].pmf_mode == "required" &&
      unifi_wlan.this["endeavour"].wlan_band == "both" &&
      unifi_wlan.this["endeavour"].wlan_bands == toset(["2g", "5g"])
    )
    error_message = "Work WiFi must use WPA3 on both bands and map to Work."
  }

  assert {
    condition = (
      unifi_wlan.ppsk["orbit"].name == "cavespace-orbit" &&
      unifi_wlan.ppsk["orbit"].network_id == "test-default-network" &&
      unifi_wlan.ppsk["orbit"].security == "wpapsk" &&
      unifi_wlan.ppsk["orbit"].private_preshared_keys_enabled &&
      !unifi_wlan.ppsk["orbit"].wpa3_support &&
      !unifi_wlan.ppsk["orbit"].wpa3_transition &&
      unifi_wlan.ppsk["orbit"].pmf_mode == "optional" &&
      !unifi_wlan.ppsk["orbit"].l2_isolation &&
      !unifi_wlan.ppsk["orbit"].is_guest &&
      unifi_wlan.ppsk["orbit"].wlan_band == "both" &&
      unifi_wlan.ppsk["orbit"].wlan_bands == toset(["2g", "5g"])
    )
    error_message = "Orbit must use WPA2 PPSK on 2.4/5 GHz, use controller Default metadata with explicit per-key VLANs and permit local Home device communication."
  }

  assert {
    condition = {
      for key in unifi_wlan.ppsk["orbit"].private_preshared_keys : key.network_id => key.password
      } == {
      test-home-network  = "test-home-passphrase"
      test-iot-network   = "test-iot-passphrase"
      test-guest-network = "test-guest-passphrase"
    }
    error_message = "Each PPSK must select its own Home, IoT or Guest network."
  }
}

run "reject_missing_ppsk" {
  command = plan
  module {
    source = "../modules/unifi/wifi"
  }
  variables {
    ppsk_passphrases = { "orbit/home" = "test-home-passphrase", "orbit/iot" = "test-iot-passphrase" }
  }
  expect_failures = [var.ppsk_passphrases]
}

run "reject_duplicate_ppsk" {
  command = plan
  module {
    source = "../modules/unifi/wifi"
  }
  variables {
    ppsk_passphrases = {
      "orbit/home"  = "test-shared-passphrase"
      "orbit/iot"   = "test-iot-passphrase"
      "orbit/guest" = "test-shared-passphrase"
    }
  }
  expect_failures = [var.ppsk_passphrases]
}

run "reject_ppsk_6ghz" {
  command = plan
  module {
    source = "../modules/unifi/wifi"
  }
  variables {
    ppsk_wlans = { orbit = { bands = ["6g"], keys = { home = "orbit", iot = "stardust", guest = "comet" } } }
  }
  expect_failures = [var.ppsk_wlans]
}

run "reject_missing_base_network" {
  command = plan
  module {
    source = "../modules/unifi/wifi"
  }
  variables {
    ppsk_base_network_id = null
  }
  expect_failures = [var.ppsk_base_network_id]
}

run "reject_unknown_ppsk_network" {
  command = plan
  module {
    source = "../modules/unifi/wifi"
  }
  variables {
    ppsk_wlans = { orbit = { bands = ["2g", "5g"], keys = { home = "missing", iot = "stardust", guest = "comet" } } }
  }
  expect_failures = [var.ppsk_wlans]
}

run "reject_shared_ssid_name" {
  command = plan
  module {
    source = "../modules/unifi/wifi"
  }
  variables {
    wlans       = { orbit = { network = "orbit", bands = ["2g", "5g"] } }
    passphrases = { orbit = "test-home-passphrase" }
  }
  expect_failures = [var.ppsk_wlans]
}
