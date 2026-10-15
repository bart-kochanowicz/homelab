resource "unifi_firewall_group" "address" {
  for_each = var.address_groups

  site    = var.site
  name    = "${var.name_prefix}${each.key}"
  type    = "address-group"
  members = each.value
}

resource "unifi_firewall_zone" "this" {
  for_each = var.zone_network_ids

  site        = var.site
  name        = "${var.name_prefix}${each.key}"
  network_ids = sort(tolist(each.value))

  lifecycle {
    prevent_destroy = true
  }
}

locals {
  zone_ids  = merge(var.builtin_zone_ids, { for key, zone in unifi_firewall_zone.this : key => zone.id })
  zone_keys = concat(keys(var.builtin_zone_ids), keys(var.zone_network_ids))

  guarded_pairs = {
    for pair in setproduct(local.zone_keys, local.zone_keys) : "${pair[0]}/${pair[1]}" => pair
    if pair[0] != pair[1] && (
      contains(keys(var.zone_network_ids), pair[0]) || contains(keys(var.zone_network_ids), pair[1]) ||
      contains(var.guarded_builtin_zones, pair[0]) || contains(var.guarded_builtin_zones, pair[1])
    )
  }

  endpoints = {
    for key, rule in var.rules : key => {
      for direction, endpoint in { source = rule.source, destination = rule.destination } : direction => {
        zone_id                           = lookup(local.zone_ids, endpoint.zone, null)
        matching_target                   = length(endpoint.clients) > 0 ? "CLIENT" : length(endpoint.ips) > 0 || endpoint.ip_group != null ? "IP" : "ANY"
        client_macs                       = length(endpoint.clients) > 0 ? sort(tolist(endpoint.clients)) : null
        ips                               = length(endpoint.ips) > 0 ? sort(tolist(endpoint.ips)) : null
        ip_group_id                       = endpoint.ip_group == null ? null : unifi_firewall_group.address[endpoint.ip_group].id
        match_opposite_ips                = endpoint.invert_ips
        port                              = endpoint.ports
        port_matching_type                = endpoint.ports == null ? "ANY" : "SPECIFIC"
      }
    }
  }

  destination_endpoints = {
    for key, rule in var.rules : key => {
      for direction, endpoint in { source = rule.source, destination = rule.destination } : direction => merge(
        local.endpoints[key][direction],
        {
          matching_target = length(endpoint.clients) > 0 ? "IP" : local.endpoints[key][direction].matching_target
          client_macs     = null
          ips             = length(endpoint.clients) > 0 ? sort([for mac in endpoint.clients : lookup(var.client_ipv4_addresses, mac, "")]) : local.endpoints[key][direction].ips
        }
      )
    }
  }
}

resource "unifi_firewall_policy" "allow" {
  for_each = var.rules

  site                  = var.site
  name                  = "${var.name_prefix}allow-${each.key}"
  description           = each.value.description
  action                = "ALLOW"
  enabled               = true
  ip_version            = each.value.ip_version
  protocol              = each.value.protocol
  connection_state_type = each.value.track_state ? "CUSTOM" : "ALL"
  connection_states     = each.value.track_state ? each.value.states : null
  create_allow_respond  = false
  source                = local.endpoints[each.key].source
  destination           = local.destination_endpoints[each.key].destination
}

resource "unifi_firewall_policy" "reply" {
  for_each = { for key, rule in var.rules : key => rule if rule.reply }

  site                  = var.site
  name                  = "${var.name_prefix}reply-${each.key}"
  description           = "Replies: ${each.value.description}"
  action                = "ALLOW"
  enabled               = true
  ip_version            = each.value.ip_version
  protocol              = each.value.protocol
  connection_state_type = "RESPOND_ONLY"
  create_allow_respond  = false
  source                = local.endpoints[each.key].destination
  destination           = local.destination_endpoints[each.key].source
}

resource "unifi_firewall_policy" "deny" {
  for_each = local.guarded_pairs

  site                  = var.site
  name                  = "${var.name_prefix}deny-${each.value[0]}-${each.value[1]}"
  description           = "Deny traffic without an explicit allowance."
  action                = "BLOCK"
  enabled               = true
  logging               = true
  ip_version            = "BOTH"
  protocol              = "all"
  connection_state_type = "ALL"
  create_allow_respond  = false
  source = {
    zone_id         = local.zone_ids[each.value[0]]
    matching_target = "ANY"
  }
  destination = {
    zone_id         = local.zone_ids[each.value[1]]
    matching_target = "ANY"
  }

  depends_on = [unifi_firewall_policy.allow, unifi_firewall_policy.reply]
}
