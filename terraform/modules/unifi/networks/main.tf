resource "unifi_network" "active" {
  for_each = var.networks

  site               = var.site
  name               = coalesce(each.value.name, "${var.name_prefix}${each.key}")
  purpose            = "corporate"
  subnet             = each.value.subnet
  vlan               = each.value.vlan
  setting_preference = "manual"
  auto_scale         = false

  ipv6 = {
    interface_type = "none"
    ra = {
      enabled = false
    }
  }

  dhcp_server = {
    enabled   = each.value.dhcp != null
    start     = try(each.value.dhcp.start, null)
    stop      = try(each.value.dhcp.stop, null)
    leasetime = try(each.value.dhcp.leasetime, null)
    dns = {
      enabled = each.value.dhcp != null
      servers = each.value.dhcp == null ? null : [split("/", each.value.subnet)[0]]
    }
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "unifi_network" "vlan_only" {
  for_each = var.vlan_only_networks

  site                = var.site
  name                = "${var.name_prefix}${each.key}"
  vlan                = each.value
  purpose             = "vlan-only"
  third_party_gateway = true

  lifecycle {
    prevent_destroy = true
  }
}
