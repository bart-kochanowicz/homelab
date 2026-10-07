locals {
  network_ids = merge(
    { for key, network in unifi_network.this : key => network.id },
    { for key, network in unifi_network.vlan_only : key => network.id }
  )
  all_network_ids = toset(concat(values(local.network_ids), [for network in values(var.reserved_networks) : network.id]))
}

resource "unifi_port_profile" "this" {
  for_each = var.port_profiles

  site                  = var.site
  name                  = "${var.name_prefix}${each.key}"
  native_networkconf_id = local.network_ids[each.value.native_network]
  forward               = length(each.value.tagged_networks) == 0 ? "native" : "customize"
  tagged_vlan_mgmt      = length(each.value.tagged_networks) == 0 ? "block_all" : "custom"
  setting_preference    = "manual"

  # Provider 0.57.0 does not serialize tagged_networkconf_ids for profiles.
  excluded_networkconf_ids = length(each.value.tagged_networks) == 0 ? null : setsubtract(
    local.all_network_ids,
    toset(concat(
      [local.network_ids[each.value.native_network]],
      [for key in each.value.tagged_networks : local.network_ids[key]]
    ))
  )

  lifecycle {
    prevent_destroy = true
  }
}
