locals {
  atm10_server_id = "4d473593-4914-4167-957e-eb494f80a99b"
}

resource "crafty_backup_config" "atm10" {
  server_id       = local.atm10_server_id
  backup_id       = "ae0d7dc8-35d1-4593-aa03-88abe09defb4"
  name            = "ATM10 Weekly"
  backup_location = "/crafty/backups/${local.atm10_server_id}"
  max_backups     = 4
  compress        = true
  shutdown        = true
  before          = ""
  after           = ""
  excluded_dirs   = []
}

resource "crafty_schedule" "atm10_backup" {
  server_id   = local.atm10_server_id
  name        = "ATM10 Weekly backup"
  action      = "backup"
  command     = "backup_server"
  backup_id   = crafty_backup_config.atm10.id
  cron_string = "0 3 * * mon"
  enabled     = true
}
