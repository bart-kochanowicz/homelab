output "zone_ids" {
  description = "Managed custom zone IDs keyed by logical name."
  value       = { for key, zone in unifi_firewall_zone.this : key => zone.id }
}

output "policy_order" {
  description = "Controller-assigned indices for allowances, replies and default denies."
  value = {
    allow = { for key, policy in unifi_firewall_policy.allow : key => policy.index }
    reply = { for key, policy in unifi_firewall_policy.reply : key => policy.index }
    deny  = { for key, policy in unifi_firewall_policy.deny : key => policy.index }
  }

  precondition {
    condition = alltrue(concat(
      [for key, policy in unifi_firewall_policy.allow : try(
        policy.index < unifi_firewall_policy.deny["${var.rules[key].source.zone}/${var.rules[key].destination.zone}"].index,
        true
      )],
      [for key, policy in unifi_firewall_policy.reply : try(
        policy.index < unifi_firewall_policy.deny["${var.rules[key].destination.zone}/${var.rules[key].source.zone}"].index,
        true
      )]
    ))
    error_message = "Allow/reply policies must precede their zone-pair deny. Reorder them in UniFi; provider 0.57.0 cannot manage indices."
  }

  precondition {
    condition     = alltrue([for policy in values(unifi_firewall_policy.deny) : policy.index < var.builtin_policy_index])
    error_message = "Custom denies must precede built-in policies. Check controller ordering and builtin_policy_index."
  }
}
