locals {
  atm10_8_3_mem_min = 4
  atm10_8_3_mem_max = 20
}

resource "crafty_minecraft_server" "atm10_8_3" {
  name           = "ATM10 8.5"
  archive_path   = var.atm10_archive_path
  archive_sha256 = "5eb960515d5fda0474935c2701b6660af0f4373782cf57ff081709b3bc56bbbb"
  executable     = "libraries/net/neoforged/neoforge/21.1.265/neoforge-21.1.265-server.jar"
  host           = "127.0.0.1"
  port           = 30000
  mem_min        = local.atm10_8_3_mem_min
  mem_max        = local.atm10_8_3_mem_max
  manage_memory  = true
  auto_start     = false

  execution_command = "/usr/lib/jvm/java-21-openjdk-amd64/bin/java @user_jvm_args.txt -Xms${local.atm10_8_3_mem_min * 1000}M -Xmx${local.atm10_8_3_mem_max * 1000}M @libraries/net/neoforged/neoforge/21.1.265/unix_args.txt nogui"

  lifecycle {
    prevent_destroy = true

    # Creation inputs seed new installations; pack files are upgraded separately.
    ignore_changes = [archive_path, archive_sha256, executable]
  }

  timeouts {
    create = "30m"
  }
}
