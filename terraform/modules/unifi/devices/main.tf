resource "unifi_device" "this" {
  for_each = var.devices

  site              = var.site
  mac               = lower(each.value.mac)
  allow_adoption    = false
  forget_on_destroy = false
  mgmt_network_id   = each.value.management_network == null ? null : var.network_ids[each.value.management_network]

  dynamic "port_override" {
    for_each = each.value.ports
    content {
      index           = port_override.value.index
      name            = port_override.value.name
      port_profile_id = var.port_profile_ids[port_override.value.profile]
      poe_mode        = port_override.value.poe_mode
      autoneg         = true
    }
  }

  lifecycle {
    prevent_destroy = true
  }
}
