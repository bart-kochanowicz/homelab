module "cloudflare" {
  source = "./modules/cloudflare"

  cloudflare_api_token  = var.cloudflare_api_token
  cloudflare_account_id = var.cloudflare_account_id
  cloudflare_zone_id    = var.cloudflare_zone_id
  domain                = var.domain
  cluster_public_ip     = var.cluster_public_ip
}
