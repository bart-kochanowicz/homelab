module "cloudflare" {
  source = "./modules/cloudflare"

  cloudflare_api_token          = var.cloudflare_api_token
  cloudflare_account_id         = var.cloudflare_account_id
  cloudflare_zone_id            = var.cloudflare_zone_id
  domain                        = var.domain
  tunnel_name                   = var.tunnel_name
  argocd_subdomain              = var.argocd_subdomain
  argocd_service_url            = var.argocd_service_url
  allowed_emails                = var.allowed_emails
  cluster_public_ip             = var.cluster_public_ip
  crafty_controller_subdomain   = var.crafty_controller_subdomain
  crafty_controller_service_url = var.crafty_controller_service_url
  grafana_service_url           = var.grafana_service_url
  home_assistant_subdomain      = var.home_assistant_subdomain
  home_assistant_service_url    = var.home_assistant_service_url
}