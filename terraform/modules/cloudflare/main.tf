# Generate a random secret for the tunnel
resource "random_id" "tunnel_secret" {
  byte_length = 32
}

# Create the Cloudflare Tunnel
resource "cloudflare_zero_trust_tunnel_cloudflared" "homelab" {
  account_id    = var.cloudflare_account_id
  name          = var.tunnel_name
  tunnel_secret = random_id.tunnel_secret.b64_std
}

# Generate tunnel token for cloudflared
data "cloudflare_zero_trust_tunnel_cloudflared_token" "homelab" {
  account_id = var.cloudflare_account_id
  tunnel_id  = cloudflare_zero_trust_tunnel_cloudflared.homelab.id
}

# Configure the tunnel with ingress rules
resource "cloudflare_zero_trust_tunnel_cloudflared_config" "homelab" {
  account_id = var.cloudflare_account_id
  tunnel_id  = cloudflare_zero_trust_tunnel_cloudflared.homelab.id

  config = {
    warp_routing_enabled = true
    ingress = [
      {
        hostname = "${var.argocd_subdomain}.${var.domain}"
        service  = var.argocd_service_url
        origin_request = {
          no_tls_verify = true
        }
      },
      {
        hostname = "${var.crafty_controller_subdomain}.${var.domain}"
        service  = "${var.crafty_controller_service_url}"
        origin_request = {
          no_tls_verify = true
        }
      },
      {
        hostname = "grafana.${var.domain}"
        service  = "${var.grafana_service_url}"
        origin_request = {
          no_tls_verify = true
        }
      },
      {
        hostname = "${var.home_assistant_subdomain}.${var.domain}"
        service  = "${var.home_assistant_service_url}"
        origin_request = {
          no_tls_verify = true
        }
      },
      {
        service = "http_status:404"
      }
    ]
  }
}

resource "cloudflare_zero_trust_list" "allow_emails_list" {
  account_id = var.cloudflare_account_id
  name       = "Allowed emails list for homelab"
  type       = "EMAIL"
  items      = [for email in var.allowed_emails : { value = email }]
}

# Create Access Policy - Allow specific emails
resource "cloudflare_zero_trust_access_policy" "allow_emails_policy" {
  account_id = var.cloudflare_account_id
  name       = "Allow specific emails to ArgoCD"
  decision   = "allow"

  include = [{
    email_list = {
      id = cloudflare_zero_trust_list.allow_emails_list.id
    }
  }]
}

# Create DNS record for ArgoCD pointing to the tunnel
resource "cloudflare_dns_record" "argocd" {
  zone_id = var.cloudflare_zone_id
  name    = var.argocd_subdomain
  content = "${cloudflare_zero_trust_tunnel_cloudflared.homelab.id}.cfargotunnel.com"
  type    = "CNAME"
  proxied = true
  comment = "Managed by Terraform - ArgoCD via Cloudflare Tunnel"
  ttl     = 1 # Automatic
}

# Create DNS record for Crafty Controller pointing to the tunnel
resource "cloudflare_dns_record" "crafty" {
  zone_id = var.cloudflare_zone_id
  name    = var.crafty_controller_subdomain
  content = "${cloudflare_zero_trust_tunnel_cloudflared.homelab.id}.cfargotunnel.com"
  type    = "CNAME"
  proxied = true
  comment = "Managed by Terraform - Crafty Controller via Cloudflare Tunnel"
  ttl     = 1 # Automatic
}

resource "cloudflare_dns_record" "mc_a" {
  zone_id = var.cloudflare_zone_id
  name    = "mc"
  content = var.cluster_public_ip
  type    = "A"
  proxied = false
  comment = "Managed by Terraform - Minecraft Server"
  ttl     = 1 # Automatic
}

# Create Cloudflare Access Application for ArgoCD
resource "cloudflare_zero_trust_access_application" "argocd" {
  account_id                = var.cloudflare_account_id
  name                      = "ArgoCD - Homelab"
  domain                    = "${var.argocd_subdomain}.${var.domain}"
  type                      = "self_hosted"
  session_duration          = "72h"
  auto_redirect_to_identity = true
  policies = [{
    id = cloudflare_zero_trust_access_policy.allow_emails_policy.id
  }]
}

# Create Cloudflare Access Application for Crafty Controller
resource "cloudflare_zero_trust_access_application" "crafty" {
  account_id                = var.cloudflare_account_id
  name                      = "Crafty Controller - Homelab"
  domain                    = "${var.crafty_controller_subdomain}.${var.domain}"
  type                      = "self_hosted"
  session_duration          = "72h"
  auto_redirect_to_identity = true
  policies = [{
    id = cloudflare_zero_trust_access_policy.allow_emails_policy.id
  }]
}

# Create DNS record for Grafana pointing to the tunnel
resource "cloudflare_dns_record" "grafana" {
  zone_id = var.cloudflare_zone_id
  name    = "grafana"
  content = "${cloudflare_zero_trust_tunnel_cloudflared.homelab.id}.cfargotunnel.com"
  type    = "CNAME"
  proxied = true
  comment = "Managed by Terraform - Grafana via Cloudflare Tunnel"
  ttl     = 1 # Automatic
}

# Create Cloudflare Access Application for Grafana
resource "cloudflare_zero_trust_access_application" "grafana" {
  account_id                = var.cloudflare_account_id
  name                      = "Grafana - Homelab"
  domain                    = "grafana.${var.domain}"
  type                      = "self_hosted"
  session_duration          = "72h"
  auto_redirect_to_identity = true
  policies = [{
    id = cloudflare_zero_trust_access_policy.allow_emails_policy.id
  }]
}

# Create DNS record for Home Assistant pointing to the tunnel
resource "cloudflare_dns_record" "home_assistant" {
  zone_id = var.cloudflare_zone_id
  name    = var.home_assistant_subdomain
  content = "${cloudflare_zero_trust_tunnel_cloudflared.homelab.id}.cfargotunnel.com"
  type    = "CNAME"
  proxied = true
  comment = "Managed by Terraform - Home Assistant via Cloudflare Tunnel"
  ttl     = 1 # Automatic
}

# Create Cloudflare Access Application for Home Assistant
resource "cloudflare_zero_trust_access_application" "home_assistant" {
  account_id                = var.cloudflare_account_id
  name                      = "Home Assistant - Homelab"
  domain                    = "${var.home_assistant_subdomain}.${var.domain}"
  type                      = "self_hosted"
  session_duration          = "72h"
  auto_redirect_to_identity = true
  policies = [{
    id = cloudflare_zero_trust_access_policy.allow_emails_policy.id
  }]
}
