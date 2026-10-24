data "cloudflare_zones" "cavespace" {
  name = "thecavespace.net"
  account = {
    id = var.cloudflare_account_id
  }

  lifecycle {
    postcondition {
      condition     = length(self.result) == 1
      error_message = "Expected exactly one thecavespace.net zone in the configured Cloudflare account."
    }
  }
}

locals {
  brevo_dns_records = {
    verification = {
      name    = "thecavespace.net"
      type    = "TXT"
      content = "brevo-code:3ef18543a32b89847d49e485fa3526a1"
    }
    dkim_1 = {
      name    = "brevo1._domainkey.thecavespace.net"
      type    = "CNAME"
      content = "b1.thecavespace-net.dkim.brevo.com"
    }
    dkim_2 = {
      name    = "brevo2._domainkey.thecavespace.net"
      type    = "CNAME"
      content = "b2.thecavespace-net.dkim.brevo.com"
    }
    dmarc = {
      name    = "_dmarc.thecavespace.net"
      type    = "TXT"
      content = "v=DMARC1; p=none; rua=mailto:rua@dmarc.brevo.com"
    }
  }
}

resource "cloudflare_dns_record" "brevo" {
  for_each = local.brevo_dns_records

  zone_id = one(data.cloudflare_zones.cavespace.result).id
  name    = each.value.name
  type    = each.value.type
  content = each.value.content
  ttl     = 300
  proxied = false
}
