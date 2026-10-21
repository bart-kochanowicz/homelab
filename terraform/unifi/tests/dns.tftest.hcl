mock_provider "unifi" {}

variables {
  site = "default"
  records = {
    ha = { name = "HA.Example.net.", address = "10.0.70.200" }
  }
}

run "exact_private_a_override" {
  command = plan
  module {
    source = "../modules/unifi/dns"
  }
  assert {
    condition = (
      length(unifi_dns_record.this) == 1 &&
      unifi_dns_record.this["ha"].name == "ha.example.net" &&
      unifi_dns_record.this["ha"].value == "10.0.70.200" &&
      unifi_dns_record.this["ha"].record_type == "A" &&
      unifi_dns_record.this["ha"].ttl == "5m" &&
      unifi_dns_record.this["ha"].enabled &&
      unifi_dns_record.this["ha"].site == "default"
    )
    error_message = "DNS overrides must be exact, canonical private A records with a bounded TTL."
  }
}

run "shared_vip_and_private_ranges_are_valid" {
  command = plan
  module {
    source = "../modules/unifi/dns"
  }
  variables {
    records = {
      first  = { name = "first.example.net", address = "172.16.0.20" }
      second = { name = "second.example.net", address = "172.16.0.20" }
      third  = { name = "third.example.net", address = "172.31.255.20" }
      fourth = { name = "fourth.example.net", address = "192.168.1.20" }
    }
  }
}

run "reject_wildcard" {
  command = plan
  module {
    source = "../modules/unifi/dns"
  }
  variables {
    records = { ha = { name = "*.example.net", address = "10.0.70.200" } }
  }
  expect_failures = [var.records]
}

run "reject_duplicate_canonical_name" {
  command = plan
  module {
    source = "../modules/unifi/dns"
  }
  variables {
    records = {
      first  = { name = "HA.Example.net.", address = "10.0.70.200" }
      second = { name = "ha.example.net", address = "10.0.70.201" }
    }
  }
  expect_failures = [var.records]
}

run "reject_fqdn_resource_key" {
  command = plan
  module {
    source = "../modules/unifi/dns"
  }
  variables {
    records = { "ha.example.net" = { name = "ha.example.net", address = "10.0.70.200" } }
  }
  expect_failures = [var.records]
}

run "reject_single_label_name" {
  command = plan
  module {
    source = "../modules/unifi/dns"
  }
  variables {
    records = { ha = { name = "localhost", address = "10.0.70.200" } }
  }
  expect_failures = [var.records]
}

run "reject_invalid_dns_label" {
  command = plan
  module {
    source = "../modules/unifi/dns"
  }
  variables {
    records = { ha = { name = "_ha.example.net", address = "10.0.70.200" } }
  }
  expect_failures = [var.records]
}

run "reject_public_ipv4" {
  command = plan
  module {
    source = "../modules/unifi/dns"
  }
  variables {
    records = { ha = { name = "ha.example.net", address = "172.32.0.20" } }
  }
  expect_failures = [var.records]
}

run "reject_invalid_ipv4" {
  command = plan
  module {
    source = "../modules/unifi/dns"
  }
  variables {
    records = { ha = { name = "ha.example.net", address = "10.0.70.999" } }
  }
  expect_failures = [var.records]
}

run "reject_ipv6" {
  command = plan
  module {
    source = "../modules/unifi/dns"
  }
  variables {
    records = { ha = { name = "ha.example.net", address = "fd00::20" } }
  }
  expect_failures = [var.records]
}

run "srv_resolves_an_owned_canonical_private_target" {
  command = plan
  module {
    source = "../modules/unifi/dns"
  }
  variables {
    srv_records = {
      minecraft = { name = "_Minecraft._TCP.HA.Example.net.", target_record = "ha", port = 30000 }
    }
  }
  assert {
    condition = (
      length(unifi_dns_record.this) == 1 &&
      length(unifi_dns_record.srv) == 1 &&
      unifi_dns_record.srv["minecraft"].name == "_minecraft._tcp.ha.example.net" &&
      unifi_dns_record.srv["minecraft"].value == unifi_dns_record.this["ha"].name &&
      unifi_dns_record.srv["minecraft"].record_type == "SRV" &&
      unifi_dns_record.srv["minecraft"].port == 30000 &&
      unifi_dns_record.srv["minecraft"].priority == null &&
      unifi_dns_record.srv["minecraft"].weight == null &&
      unifi_dns_record.srv["minecraft"].ttl == "5m" &&
      unifi_dns_record.srv["minecraft"].enabled &&
      unifi_dns_record.srv["minecraft"].site == "default"
    )
    error_message = "SRV records must resolve through owned private A records and omit zero priority and weight to match provider readback."
  }
}

run "srv_accepts_explicit_unsigned_16_bit_limits" {
  command = plan
  module {
    source = "../modules/unifi/dns"
  }
  variables {
    srv_records = {
      service = {
        name = "_service._udp.ha.example.net", target_record = "ha", port = 65535, priority = 65535, weight = 65535
      }
    }
  }
  assert {
    condition = (
      unifi_dns_record.srv["service"].port == 65535 &&
      unifi_dns_record.srv["service"].priority == 65535 &&
      unifi_dns_record.srv["service"].weight == 65535
    )
    error_message = "Valid explicit SRV port, priority and weight values must reach the provider unchanged."
  }
}

run "srv_rejects_an_unowned_target" {
  command = plan
  module {
    source = "../modules/unifi/dns"
  }
  variables {
    srv_records = {
      service = { name = "_minecraft._tcp.ha.example.net", target_record = "public.example.net", port = 30000 }
    }
  }
  expect_failures = [var.srv_records]
}

run "srv_rejects_names_without_a_service_prefix" {
  command = plan
  module {
    source = "../modules/unifi/dns"
  }
  variables {
    srv_records = { service = { name = "ha.example.net", target_record = "ha", port = 30000 } }
  }
  expect_failures = [var.srv_records]
}

run "srv_rejects_wildcards" {
  command = plan
  module {
    source = "../modules/unifi/dns"
  }
  variables {
    srv_records = { service = { name = "_minecraft._tcp.*.example.net", target_record = "ha", port = 30000 } }
  }
  expect_failures = [var.srv_records]
}

run "srv_rejects_duplicate_canonical_owners" {
  command = plan
  module {
    source = "../modules/unifi/dns"
  }
  variables {
    srv_records = {
      first  = { name = "_Minecraft._TCP.HA.Example.net.", target_record = "ha", port = 30000 }
      second = { name = "_minecraft._tcp.ha.example.net", target_record = "ha", port = 30001 }
    }
  }
  expect_failures = [var.srv_records]
}

run "srv_rejects_out_of_range_ports" {
  command = plan
  module {
    source = "../modules/unifi/dns"
  }
  variables {
    srv_records = { service = { name = "_minecraft._tcp.ha.example.net", target_record = "ha", port = 65536 } }
  }
  expect_failures = [var.srv_records]
}

run "srv_rejects_fractional_ports" {
  command = plan
  module {
    source = "../modules/unifi/dns"
  }
  variables {
    srv_records = { service = { name = "_minecraft._tcp.ha.example.net", target_record = "ha", port = 1.5 } }
  }
  expect_failures = [var.srv_records]
}

run "srv_rejects_negative_weights" {
  command = plan
  module {
    source = "../modules/unifi/dns"
  }
  variables {
    srv_records = {
      service = { name = "_minecraft._tcp.ha.example.net", target_record = "ha", port = 30000, weight = -1 }
    }
  }
  expect_failures = [var.srv_records]
}
