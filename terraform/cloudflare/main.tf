module "cloudflare" {
  source = "../modules/cloudflare"

  cloudflare_api_token  = var.cloudflare_api_token
  cloudflare_account_id = var.cloudflare_account_id
}
