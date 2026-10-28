resource "crafty_minecraft_server" "atm10" {
  name           = "ATM10 4.14"
  archive_path   = var.atm10_archive_path
  archive_sha256 = "d8985a62529c21ee2cf36882e3f33d9d59f69e56197ee0867b5b99bb5da07a2c"
  executable     = "libraries/net/neoforged/neoforge/21.1.211/neoforge-21.1.211-server.jar"
  host           = "127.0.0.1"
  port           = 30000
  mem_min        = 4
  mem_max        = 12
  auto_start     = false

  # Keep the pack's JVM tuning and reserve memory for native allocations and Crafty.
  execution_command = "/usr/lib/jvm/java-21-openjdk-amd64/bin/java @user_jvm_args.txt -Xmx12G @libraries/net/neoforged/neoforge/21.1.211/unix_args.txt nogui"

  lifecycle {
    prevent_destroy = true
  }

  timeouts {
    create = "30m"
  }
}

resource "crafty_minecraft_server" "atm10_8_3" {
  name           = "ATM10 8.3"
  archive_path   = var.atm10_8_3_archive_path
  archive_sha256 = "9c6b994c334490e85a04ec986c9ef4a903d13d38afb54d5231793540f8449596"
  executable     = "libraries/net/neoforged/neoforge/21.1.259/neoforge-21.1.259-server.jar"
  host           = "127.0.0.1"
  port           = 30000
  mem_min        = 4
  mem_max        = 12
  auto_start     = false

  execution_command = "/usr/lib/jvm/java-21-openjdk-amd64/bin/java @user_jvm_args.txt -Xmx12G @libraries/net/neoforged/neoforge/21.1.259/unix_args.txt nogui"

  lifecycle {
    prevent_destroy = true
  }

  timeouts {
    create = "30m"
  }
}
