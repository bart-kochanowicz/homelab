output "terraform_state_backup_bucket" {
  description = "Private Cloudflare R2 bucket for off-site Terraform state snapshots"
  value       = cloudflare_r2_bucket.terraform_state_backups.name
}
