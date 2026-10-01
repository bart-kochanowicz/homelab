output "tunnel_id" {
  description = "The ID of the Cloudflare Tunnel"
  value       = cloudflare_zero_trust_tunnel_cloudflared.homelab.id
}

output "tunnel_token" {
  description = "The tunnel token for cloudflared (sensitive)"
  value       = data.cloudflare_zero_trust_tunnel_cloudflared_token.homelab.token
  sensitive   = true
}

output "argocd_url" {
  description = "Public URL for ArgoCD"
  value       = "https://${var.argocd_subdomain}.${var.domain}"
}

output "tunnel_cname" {
  description = "CNAME record for the tunnel"
  value       = "${cloudflare_zero_trust_tunnel_cloudflared.homelab.id}.cfargotunnel.com"
}

output "access_application_id" {
  description = "Cloudflare Access Application ID"
  value       = cloudflare_zero_trust_access_application.argocd.id
}

output "terraform_state_backup_bucket" {
  description = "Private Cloudflare R2 bucket for off-site Terraform state snapshots"
  value       = cloudflare_r2_bucket.terraform_state_backups.name
}
