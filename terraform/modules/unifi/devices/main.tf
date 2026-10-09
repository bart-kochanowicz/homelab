resource "unifi_device" "this" {
  for_each = var.devices

  site              = var.site
  mac               = lower(each.value.mac)
  allow_adoption    = false
  forget_on_destroy = false

  dynamic "port_override" {
    for_each = each.value.ports
    content {
      index           = port_override.value.index
      name            = port_override.value.name
      port_profile_id = var.port_profile_ids[port_override.value.profile]
    }
  }

  lifecycle {
    prevent_destroy = true
  }
}
