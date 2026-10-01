# Output values from the Cloudflare module

output "tunnel_id" {
  description = "The ID of the Cloudflare Tunnel"
  value       = module.cloudflare.tunnel_id
}

output "tunnel_token" {
  description = "The tunnel token for cloudflared (sensitive)"
  value       = module.cloudflare.tunnel_token
  sensitive   = true
}

output "argocd_url" {
  description = "Public URL for ArgoCD"
  value       = module.cloudflare.argocd_url
}

output "tunnel_cname" {
  description = "CNAME record for the tunnel"
  value       = module.cloudflare.tunnel_cname
}

output "access_application_id" {
  description = "Cloudflare Access Application ID"
  value       = module.cloudflare.access_application_id
}

output "terraform_state_backup_bucket" {
  description = "Private Cloudflare R2 bucket for off-site Terraform state snapshots"
  value       = module.cloudflare.terraform_state_backup_bucket
}
