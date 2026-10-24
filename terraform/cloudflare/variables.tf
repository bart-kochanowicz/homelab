variable "cloudflare_api_token" {
  description = "Cloudflare API token with R2 Storage Write, Zone Read and DNS Write permissions for thecavespace.net"
  type        = string
  sensitive   = true
}

variable "cloudflare_account_id" {
  description = "Cloudflare account ID"
  type        = string
  sensitive   = true
}
