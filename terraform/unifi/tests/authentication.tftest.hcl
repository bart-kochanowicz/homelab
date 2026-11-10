mock_provider "unifi" {
  mock_resource "unifi_firewall_policy" {
    defaults = { index = 10000 }
  }
}

override_data {
  target = data.unifi_network.default
  values = {
    id      = "test-default-lan"
    purpose = "corporate"
    subnet  = "192.168.1.1/24"
  }
}

override_module {
  target = module.networks
  outputs = {
    network_ids = {
      endeavour       = "test-work"
      orbit           = "test-home"
      stardust        = "test-iot"
      comet           = "test-guest"
      launchpad       = "test-servers"
      apollo          = "test-admin"
      mission-control = "test-management"
      parking         = "test-parking"
    }
  }
}

override_resource {
  target = module.reservations.unifi_client.this["houston-01"]
  values = { id = "02:00:00:00:00:10", mac = "02:00:00:00:00:10" }
}

override_resource {
  target = module.reservations.unifi_client.this["control-plane-01"]
  values = { id = "02:00:00:00:00:11", mac = "02:00:00:00:00:11" }
}

override_resource {
  target = module.reservations.unifi_client.this["worker-01"]
  values = { id = "02:00:00:00:00:12", mac = "02:00:00:00:00:12" }
}

override_resource {
  target = module.reservations.unifi_client.this["windowspc-01"]
  values = { id = "02:00:00:00:00:80", mac = "02:00:00:00:00:80" }
}

override_resource {
  target = module.reservations.unifi_client.this["tv-ambient"]
  values = { id = "02:00:00:00:00:50", mac = "02:00:00:00:00:50" }
}

override_resource {
  target = module.reservations.unifi_client.this["front-door-camera"]
  values = { id = "02:00:00:00:00:51", mac = "02:00:00:00:00:51" }
}

override_resource {
  target = module.reservations.unifi_client.this["sonoff-zigbee"]
  values = { id = "02:00:00:00:00:52", mac = "02:00:00:00:00:52" }
}

override_resource {
  target = module.reservations.unifi_client.this["lg-tv"]
  values = { id = "02:00:00:00:00:40", mac = "02:00:00:00:00:40" }
}

override_resource {
  target = module.devices.unifi_device.this["flex-5"]
  values = {
    id  = "02:00:00:00:00:05"
    mac = "02:00:00:00:00:05"
  }
}

override_resource {
  target = module.devices.unifi_device.this["flex-8"]
  values = { id = "02:00:00:00:00:07", mac = "02:00:00:00:00:07" }
}

override_resource {
  target = module.devices.unifi_device.this["voyager-01"]
  values = { id = "02:00:00:00:00:06", mac = "02:00:00:00:00:06" }
}

override_module {
  target = module.port_profiles
  outputs = {
    port_profile_ids = { access-apollo = "test-admin-profile", access-orbit = "test-home-profile", access-stardust = "test-iot-profile", access-launchpad = "test-servers-profile", access-parking = "test-parking-profile", switch-trunk = "test-trunk-profile", ap = "test-ap-profile" }
  }
}

variables {
  infrastructure_macs = {
    flex-5            = "02:00:00:00:00:05"
    flex-8            = "02:00:00:00:00:07"
    voyager-01        = "02:00:00:00:00:06"
    houston-01        = "02:00:00:00:00:10"
    control-plane-01  = "02:00:00:00:00:11"
    worker-01         = "02:00:00:00:00:12"
    front-door-camera = "02:00:00:00:00:51"
    lg-tv             = "02:00:00:00:00:40"
    sonoff-zigbee     = "02:00:00:00:00:52"
    tv-ambient        = "02:00:00:00:00:50"
    windowspc-01      = "02:00:00:00:00:80"
  }
  vpn_public_ip = "198.51.100.10"
  vpn_peer_public_keys = {
    macbook-01   = "hSDwCYkwp1R0i33ctD73Wg2/Og0mOBr066SpjqqbTmo="
    iphone-01    = "BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBA="
    windowspc-01 = "CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCA="
  }
  controller       = { url = "https://unifi.example.internal" }
  unifi_auth       = { username = "test-only", password = "test-only" } # gitleaks:allow -- mock provider input
  wifi_passphrases = { apollo = "test-only-passphrase", endeavour = "test-work-passphrase" }
  wifi_ppsks = {
    "orbit/home" = "test-home-passphrase"
    "orbit/iot"  = "test-iot-passphrase"
  }
}

run "local_authentication" {
  command = plan

  assert {
    condition     = toset(keys(module.wifi.wlan_ids)) == toset(["apollo", "endeavour", "orbit", "stardust"])
    error_message = "The root must retain the Admin, Work, Home and IoT WLANs."
  }

  assert {
    condition = (
      issensitive(local.devices["flex-5"].mac) &&
      issensitive(local.server_macs["worker-01"]) &&
      issensitive(output.device_ids) &&
      local.devices["flex-5"].mac == var.infrastructure_macs["flex-5"] &&
      local.server_reservations["worker-01"].mac == var.infrastructure_macs["worker-01"] &&
      issensitive(local.dhcp_reservations["windowspc-01"].mac) &&
      local.dhcp_reservations["windowspc-01"].mac == var.infrastructure_macs["windowspc-01"] &&
      issensitive(local.dhcp_reservations["tv-ambient"].mac) &&
      local.dhcp_reservations["tv-ambient"].mac == var.infrastructure_macs["tv-ambient"] &&
      issensitive(local.dhcp_reservations["front-door-camera"].mac) &&
      local.dhcp_reservations["front-door-camera"].mac == var.infrastructure_macs["front-door-camera"] &&
      issensitive(local.dhcp_reservations["sonoff-zigbee"].mac) &&
      local.dhcp_reservations["sonoff-zigbee"].mac == var.infrastructure_macs["sonoff-zigbee"] &&
      issensitive(local.dhcp_reservations["lg-tv"].mac) &&
      local.dhcp_reservations["lg-tv"].mac == var.infrastructure_macs["lg-tv"]
    )
    error_message = "Private MAC inputs must reach device/client selectors and keep MAC-derived device IDs sensitive."
  }
}

run "reject_duplicate_infrastructure_mac" {
  command = plan
  variables {
    infrastructure_macs = {
      flex-5            = "02:00:00:00:00:05"
      flex-8            = "02:00:00:00:00:07"
      voyager-01        = "02:00:00:00:00:06"
      houston-01        = "02:00:00:00:00:10"
      control-plane-01  = "02:00:00:00:00:11"
      worker-01         = "02:00:00:00:00:11"
      front-door-camera = "02:00:00:00:00:51"
      lg-tv             = "02:00:00:00:00:40"
      sonoff-zigbee     = "02:00:00:00:00:52"
      tv-ambient        = "02:00:00:00:00:50"
      windowspc-01      = "02:00:00:00:00:80"
    }
  }
  expect_failures = [var.infrastructure_macs]
}

run "reject_invalid_infrastructure_mac" {
  command = plan
  variables {
    infrastructure_macs = {
      flex-5            = "02:00:00:00:00:05"
      flex-8            = "02:00:00:00:00:07"
      voyager-01        = "02:00:00:00:00:06"
      houston-01        = "02:00:00:00:00:10"
      control-plane-01  = "02:00:00:00:00:11"
      worker-01         = "not-a-mac"
      front-door-camera = "02:00:00:00:00:51"
      lg-tv             = "02:00:00:00:00:40"
      sonoff-zigbee     = "02:00:00:00:00:52"
      tv-ambient        = "02:00:00:00:00:50"
      windowspc-01      = "02:00:00:00:00:80"
    }
  }
  expect_failures = [var.infrastructure_macs]
}

run "client_output_when_controller_omits_public_key" {
  command   = apply
  state_key = "client-output"
  override_resource {
    target = module.vpn.unifi_vpn_server.this
    values = {
      wireguard = {
        # RFC 7748 section 6.1 Alice test vector; not a deployed key.
        private_key = "dwdtCnMYpX08FsFyUbJmRd9ML4frwJkqsXf7pR25LCo=" # gitleaks:allow
        public_key  = null
        port        = 51820
      }
    }
  }
  override_resource {
    target = module.firewall.unifi_firewall_policy.deny
    values = { index = 20000 }
  }
  assert {
    condition = (
      issensitive(output.wireguard_clients) &&
      issensitive(local.vpn_peers["macbook-01"].public_key) &&
      strcontains(output.wireguard_clients["macbook-01"], "PublicKey = hSDwCYkwp1R0i33ctD73Wg2/Og0mOBr066SpjqqbTmo=") &&
      !strcontains(output.wireguard_clients["macbook-01"], "PrivateKey =") &&
      alltrue([for pair in ["vpn/internal", "internal/vpn", "vpn/gateway", "gateway/vpn", "vpn/external", "external/vpn"] :
        contains(keys(module.firewall.policy_order.deny), pair)
      ])
    )
    error_message = "Client settings require the derived public key without private key assignments; the root must also enable VPN guards."
  }
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
