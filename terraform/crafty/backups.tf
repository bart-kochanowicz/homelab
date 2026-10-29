resource "crafty_backup_config" "atm10" {
  server_id       = crafty_minecraft_server.atm10_8_3.id
  backup_id       = "0cb658e6-0eb3-4a05-adda-74bbcc1a8133"
  name            = "ATM10 Weekly"
  backup_location = "/crafty/backups/${crafty_minecraft_server.atm10_8_3.id}"
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
  server_id   = crafty_minecraft_server.atm10_8_3.id
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
