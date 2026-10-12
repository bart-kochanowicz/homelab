mock_provider "unifi" {
  mock_resource "unifi_firewall_policy" {
    defaults = { index = 20000 }
  }
}

variables {
  site             = "default"
  zone_network_ids = { orbit = ["test-home"], launchpad = ["test-servers"] }
  builtin_zone_ids = { gateway = "test-gateway", external = "test-wan", internal = "test-default" }
  rules = {
    ha = {
      description = "Home Assistant access."
      protocol    = "tcp"
      source      = { zone = "orbit" }
      destination = { zone = "launchpad", clients = ["02:00:00:00:00:12"], ports = "8123" }
    }
  }
}

run "stateful_services_and_boundaries" {
  command = plan
  module {
    source = "../modules/unifi/firewall"
  }

  assert {
    condition = (
      unifi_firewall_policy.allow["ha"].connection_state_type == "CUSTOM" &&
      unifi_firewall_policy.allow["ha"].connection_states == tolist(["NEW", "ESTABLISHED", "RELATED"]) &&
      !unifi_firewall_policy.allow["ha"].create_allow_respond &&
      unifi_firewall_policy.reply["ha"].connection_state_type == "RESPOND_ONLY" &&
      !unifi_firewall_policy.reply["ha"].create_allow_respond
    )
    error_message = "Service replies must be explicit and must not authorize reverse initiation."
  }
  assert {
    condition = (
      unifi_firewall_policy.reply["ha"].source.port == "8123" &&
      unifi_firewall_policy.reply["ha"].destination.port_matching_type == "ANY" &&
      unifi_firewall_policy.reply["ha"].source.client_macs == tolist(["02:00:00:00:00:12"]) &&
      unifi_firewall_policy.allow["ha"].destination.matching_target == "CLIENT"
    )
    error_message = "Replies must match the server and service source port, not the client destination port."
  }
  assert {
    condition = (
      length(unifi_firewall_policy.deny) == 14 &&
      alltrue([for policy in values(unifi_firewall_policy.deny) : policy.ip_version == "BOTH" && policy.action == "BLOCK"]) &&
      contains(keys(unifi_firewall_policy.deny), "internal/orbit") &&
      contains(keys(unifi_firewall_policy.deny), "gateway/orbit") &&
      contains(keys(unifi_firewall_policy.deny), "external/launchpad") &&
      !contains(keys(unifi_firewall_policy.deny), "internal/gateway") &&
      !contains(keys(unifi_firewall_policy.deny), "orbit/orbit")
    )
    error_message = "Deny both families around managed zones without taking over built-in pairs or same-VLAN traffic."
  }
}

run "dhcp_requires_untracked_return" {
  command = plan
  module {
    source = "../modules/unifi/firewall"
  }
  variables {
    rules = {
      dhcp = {
        description = "DHCP broadcast reply."
        protocol    = "udp"
        ip_version  = "IPV4"
        reply       = false
        track_state = false
        source      = { zone = "gateway", ports = "67" }
        destination = { zone = "orbit", ports = "68" }
      }
    }
  }
  assert {
    condition = (
      unifi_firewall_policy.allow["dhcp"].connection_state_type == "ALL" &&
      unifi_firewall_policy.allow["dhcp"].source.port == "67" &&
      unifi_firewall_policy.allow["dhcp"].destination.port == "68" &&
      length(unifi_firewall_policy.reply) == 0
    )
    error_message = "DHCP offers must not depend on established state for a broadcast exchange."
  }
}

run "reject_unknown_zone" {
  command = plan
  module {
    source = "../modules/unifi/firewall"
  }
  variables {
    rules = { bad = { description = "Unknown destination.", source = { zone = "orbit" }, destination = { zone = "missing" } } }
  }
  expect_failures = [var.rules]
}

run "reject_dual_membership" {
  command = plan
  module {
    source = "../modules/unifi/firewall"
  }
  variables {
    zone_network_ids = { orbit = ["test-home"], launchpad = ["test-home"] }
  }
  expect_failures = [var.zone_network_ids]
}

run "reject_builtin_zone_ownership" {
  command = plan
  module {
    source = "../modules/unifi/firewall"
  }
  variables {
    zone_network_ids = { orbit = ["test-home"], launchpad = ["test-servers"], internal = ["test-default"] }
  }
  expect_failures = [var.zone_network_ids]
}

run "reject_mixed_endpoint_selectors" {
  command = plan
  module {
    source = "../modules/unifi/firewall"
  }
  variables {
    rules = {
      bad = {
        description = "Ambiguous destination."
        source      = { zone = "orbit" }
        destination = { zone = "launchpad", clients = ["02:00:00:00:00:12"], ips = ["10.0.70.12"] }
      }
    }
  }
  expect_failures = [var.rules]
}

run "reject_shadowed_allowance" {
  command   = apply
  state_key = "shadowed-allowance"
  module {
    source = "../modules/unifi/firewall"
  }
  override_resource {
    target = unifi_firewall_policy.allow["ha"]
    values = { index = 20000 }
  }
  override_resource {
    target = unifi_firewall_policy.deny["orbit/launchpad"]
    values = { index = 10000 }
  }
  override_resource {
    target = unifi_firewall_policy.reply["ha"]
    values = { index = 10000 }
  }
  expect_failures = [output.policy_order]
}

run "accept_ordered_policies" {
  command   = apply
  state_key = "ordered-policies"
  module {
    source = "../modules/unifi/firewall"
  }
  override_resource {
    target = unifi_firewall_policy.allow["ha"]
    values = { index = 10000 }
  }
  override_resource {
    target = unifi_firewall_policy.reply["ha"]
    values = { index = 10000 }
  }
}

run "reject_builtin_shadowing_deny" {
  command   = apply
  state_key = "shadowed-deny"
  module {
    source = "../modules/unifi/firewall"
  }
  override_resource {
    target = unifi_firewall_policy.allow["ha"]
    values = { index = 10000 }
  }
  override_resource {
    target = unifi_firewall_policy.reply["ha"]
    values = { index = 10000 }
  }
  override_resource {
    target = unifi_firewall_policy.deny["orbit/gateway"]
    values = { index = 40000 }
  }
  expect_failures = [output.policy_order]
}
