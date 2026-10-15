resource "unifi_client" "this" {
  for_each = var.reservations

  site                   = var.site
  mac                    = lower(each.value.mac)
  fixed_ip               = each.value.ip
  allow_existing         = true
  skip_forget_on_destroy = true

  lifecycle {
    prevent_destroy = true
  }
}
