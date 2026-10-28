resource "crafty_backup_config" "atm10" {
  server_id       = crafty_minecraft_server.atm10.id
  backup_id       = "f813a6e2-d7bd-4ee7-8653-30fb18244a84"
  name            = "ATM10 Weekly"
  backup_location = "/crafty/backups/${crafty_minecraft_server.atm10.id}"
  max_backups     = 4
  compress        = true
  shutdown        = true
  before          = ""
  after           = ""
  excluded_dirs   = []

  lifecycle {
    create_before_destroy = true
  }
}

resource "crafty_schedule" "atm10_backup" {
  server_id   = crafty_minecraft_server.atm10.id
  name        = "ATM10 Weekly backup"
  action      = "backup"
  command     = "backup_server"
  backup_id   = crafty_backup_config.atm10.id
  cron_string = "0 3 * * mon"
  enabled     = true

  lifecycle {
    create_before_destroy = true
  }
}
