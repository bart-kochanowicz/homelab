variable "cloudflare_api_token" {
  description = "Cloudflare API token with DNS Edit and Workers R2 Storage Write permissions"
  type        = string
  sensitive   = true
}

variable "cloudflare_account_id" {
  description = "Cloudflare account ID"
  type        = string
}

variable "cloudflare_zone_id" {
  description = "Cloudflare zone ID for your domain"
  type        = string
}

variable "domain" {
  description = "Base domain name (e.g., example.com)"
  type        = string
}

variable "cluster_public_ip" {
  description = "Public IP address of the cluster"
  type        = string
  sensitive   = true
}
