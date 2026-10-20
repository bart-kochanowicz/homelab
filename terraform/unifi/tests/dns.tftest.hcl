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
