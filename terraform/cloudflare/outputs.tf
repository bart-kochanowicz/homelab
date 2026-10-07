output "terraform_state_backup_bucket" {
  description = "Private Cloudflare R2 bucket for off-site Terraform state snapshots"
  value       = module.cloudflare.terraform_state_backup_bucket
}
