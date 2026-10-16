mock_provider "unifi" {}

variables {
  site = "default"
  networks = {
    servers = {
      subnet = "10.0.70.1/24"
      dhcp   = { start = "10.0.70.100", stop = "10.0.70.199" }
    }
  }
  reservations = {
    server-01 = { mac = "02:00:00:00:00:AA", ip = "10.0.70.10", network = "servers" }
  }
}

run "reservation_preserves_existing_client" {
  command = plan
  module {
    source = "../modules/unifi/reservations"
  }
  assert {
    condition = (
      unifi_client.this["server-01"].mac == "02:00:00:00:00:aa" &&
      unifi_client.this["server-01"].fixed_ip == "10.0.70.10" &&
      unifi_client.this["server-01"].allow_existing &&
      unifi_client.this["server-01"].skip_forget_on_destroy
    )
    error_message = "A reservation must use its declared MAC/address and preserve the existing client."
  }
}

run "reject_dynamic_pool_address" {
  command = plan
  module {
    source = "../modules/unifi/reservations"
  }
  variables {
    reservations = { server-01 = { mac = "02:00:00:00:00:aa", ip = "10.0.70.100", network = "servers" } }
  }
  expect_failures = [var.reservations]
}

run "reject_gateway" {
  command = plan
  module {
    source = "../modules/unifi/reservations"
  }
  variables {
    reservations = { server-01 = { mac = "02:00:00:00:00:aa", ip = "10.0.70.1", network = "servers" } }
  }
  expect_failures = [var.reservations]
}

run "reject_other_subnet" {
  command = plan
  module {
    source = "../modules/unifi/reservations"
  }
  variables {
    reservations = { server-01 = { mac = "02:00:00:00:00:aa", ip = "10.0.50.10", network = "servers" } }
  }
  expect_failures = [var.reservations]
}

run "reject_unknown_network" {
  command = plan
  module {
    source = "../modules/unifi/reservations"
  }
  variables {
    reservations = { server-01 = { mac = "02:00:00:00:00:aa", ip = "10.0.70.10", network = "missing" } }
  }
  expect_failures = [var.reservations]
}

run "reject_duplicate_mac_case_insensitively" {
  command = plan
  module {
    source = "../modules/unifi/reservations"
  }
  variables {
    reservations = {
      server-01 = { mac = "02:00:00:00:00:aa", ip = "10.0.70.10", network = "servers" }
      server-02 = { mac = "02:00:00:00:00:AA", ip = "10.0.70.11", network = "servers" }
    }
  }
  expect_failures = [var.reservations]
}

run "reject_duplicate_ip" {
  command = plan
  module {
    source = "../modules/unifi/reservations"
  }
  variables {
    reservations = {
      server-01 = { mac = "02:00:00:00:00:aa", ip = "10.0.70.10", network = "servers" }
      server-02 = { mac = "02:00:00:00:00:bb", ip = "10.0.70.10", network = "servers" }
    }
  }
  expect_failures = [var.reservations]
}

run "reject_invalid_mac" {
  command = plan
  module {
    source = "../modules/unifi/reservations"
  }
  variables {
    reservations = { server-01 = { mac = "invalid", ip = "10.0.70.10", network = "servers" } }
  }
  expect_failures = [var.reservations]
}
