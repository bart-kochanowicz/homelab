resource "unifi_dns_record" "this" {
  for_each = var.records

  site        = var.site
  name        = lower(trimsuffix(each.value.name, "."))
  record_type = "A"
  value       = each.value.address
  enabled     = true
  ttl         = "5m"
}

# The provider reads zero priority and weight back as null.
resource "unifi_dns_record" "srv" {
  for_each = var.srv_records

  site        = var.site
  name        = lower(trimsuffix(each.value.name, "."))
  record_type = "SRV"
  value       = unifi_dns_record.this[each.value.target_record].name
  port        = each.value.port
  priority    = each.value.priority == 0 ? null : each.value.priority
  weight      = each.value.weight == 0 ? null : each.value.weight
  enabled     = true
  ttl         = "5m"
}
