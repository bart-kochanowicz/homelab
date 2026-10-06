resource "unifi_network" "this" {
  for_each = var.networks

  site                = var.site
  name                = coalesce(each.value.name, "${var.name_prefix}${each.key}")
  purpose             = "corporate"
  subnet              = each.value.subnet
  vlan                = each.value.vlan
  ipv6_interface_type = "none"
  ipv6_ra             = false

  dhcp_server = {
    enabled   = each.value.dhcp != null
    start     = try(each.value.dhcp.start, null)
    stop      = try(each.value.dhcp.stop, null)
    leasetime = try(each.value.dhcp.leasetime, null)
  }

  lifecycle {
    prevent_destroy = true
  }
}
