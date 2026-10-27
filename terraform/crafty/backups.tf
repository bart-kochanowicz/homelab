locals {
  atm10_server_id = "4d473593-4914-4167-957e-eb494f80a99b"
  atm10_backups = {
    daily = {
      backup_id   = "39c9d85c-d349-48fd-b61d-5898630cf7b2"
      max_backups = 7
      cron        = "0 3 * * *"
    }
    weekly = {
      backup_id   = "ae0d7dc8-35d1-4593-aa03-88abe09defb4"
      max_backups = 4
      cron        = "0 4 * * sun"
    }
    monthly = {
      backup_id   = "20d5dd61-3624-430b-8889-808934e93d08"
      max_backups = 3
      cron        = "0 5 1 * *"
    }
  }
}

resource "crafty_backup_config" "atm10" {
  for_each = local.atm10_backups

  server_id       = local.atm10_server_id
  backup_id       = each.value.backup_id
  name            = "ATM10 ${title(each.key)}"
  backup_location = "/crafty/backups/${local.atm10_server_id}"
  max_backups     = each.value.max_backups
  compress        = true
  shutdown        = true
  before          = ""
  after           = ""
  excluded_dirs   = []
}

resource "crafty_schedule" "atm10_backups" {
  for_each = local.atm10_backups

  server_id   = local.atm10_server_id
  name        = "ATM10 ${title(each.key)} backup"
  action      = "backup"
  command     = "backup_server"
  backup_id   = crafty_backup_config.atm10[each.key].id
  cron_string = each.value.cron
  enabled     = true
}
