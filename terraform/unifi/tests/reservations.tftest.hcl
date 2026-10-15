mock_provider "unifi" {}

variables {
  site = "default"
  networks = {
    home = {
      subnet = "10.0.40.1/24"
      dhcp   = { start = "10.0.40.100", stop = "10.0.40.199" }
    }
  }
  reservations = {
    receiver-01 = { mac = "02:00:00:00:00:AA", ip = "10.0.40.10", network = "home" }
  }
}

run "reservation_preserves_client_and_membership" {
  command = plan
  module {
    source = "../modules/unifi/reservations"
  }
  assert {
    condition = (
      unifi_client.this["receiver-01"].mac == "02:00:00:00:00:aa" &&
      unifi_client.this["receiver-01"].fixed_ip == "10.0.40.10" &&
      unifi_client.this["receiver-01"].allow_existing &&
      unifi_client.this["receiver-01"].skip_forget_on_destroy
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
    reservations = { receiver-01 = { mac = "02:00:00:00:00:aa", ip = "10.0.40.100", network = "home" } }
  }
  expect_failures = [var.reservations]
}

run "reject_gateway" {
  command = plan
  module {
    source = "../modules/unifi/reservations"
  }
  variables {
    reservations = { receiver-01 = { mac = "02:00:00:00:00:aa", ip = "10.0.40.1", network = "home" } }
  }
  expect_failures = [var.reservations]
}

run "reject_other_subnet" {
  command = plan
  module {
    source = "../modules/unifi/reservations"
  }
  variables {
    reservations = { receiver-01 = { mac = "02:00:00:00:00:aa", ip = "10.0.50.10", network = "home" } }
  }
  expect_failures = [var.reservations]
}

run "reject_unknown_network" {
  command = plan
  module {
    source = "../modules/unifi/reservations"
  }
  variables {
    reservations = { receiver-01 = { mac = "02:00:00:00:00:aa", ip = "10.0.40.10", network = "missing" } }
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
      receiver-01 = { mac = "02:00:00:00:00:aa", ip = "10.0.40.10", network = "home" }
      receiver-02 = { mac = "02:00:00:00:00:AA", ip = "10.0.40.11", network = "home" }
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
      receiver-01 = { mac = "02:00:00:00:00:aa", ip = "10.0.40.10", network = "home" }
      receiver-02 = { mac = "02:00:00:00:00:bb", ip = "10.0.40.10", network = "home" }
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
    reservations = { receiver-01 = { mac = "invalid", ip = "10.0.40.10", network = "home" } }
  }
  expect_failures = [var.reservations]
}
