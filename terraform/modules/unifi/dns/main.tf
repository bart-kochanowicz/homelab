resource "unifi_dns_record" "this" {
  for_each = var.records

  site        = var.site
  name        = lower(trimsuffix(each.value.name, "."))
  record_type = "A"
  value       = each.value.address
  enabled     = true
  ttl         = "5m"
}
