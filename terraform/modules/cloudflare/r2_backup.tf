# Off-site snapshots of Garage state. The upload and restore steps are separate.
resource "cloudflare_r2_bucket" "terraform_state_backups" {
  account_id    = var.cloudflare_account_id
  name          = "houston-terraform-state-backups"
  location      = "weur"
  storage_class = "Standard"

  lifecycle {
    prevent_destroy = true
  }
}

resource "cloudflare_r2_managed_domain" "terraform_state_backups" {
  account_id  = var.cloudflare_account_id
  bucket_name = cloudflare_r2_bucket.terraform_state_backups.name
  enabled     = false
}

# Bucket Lock prevents overwrite and deletion of snapshots for 90 days.
# A separate object-only upload token cannot change this configuration.
resource "cloudflare_r2_bucket_lock" "terraform_state_backups" {
  account_id  = var.cloudflare_account_id
  bucket_name = cloudflare_r2_bucket.terraform_state_backups.name
  rules = [{
    id      = "terraform-state-backups-90-days"
    enabled = true
    prefix  = "backups/"
    condition = {
      type            = "Age"
      max_age_seconds = 90 * 24 * 60 * 60
    }
  }]

  lifecycle {
    prevent_destroy = true
  }
}
