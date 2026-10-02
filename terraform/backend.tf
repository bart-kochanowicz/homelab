# Garage backend for the Cloudflare root module.
# Shared settings: terraform init -backend-config=garage.s3.tfbackend
# Credentials come from the environment. Use the Houston Terraform wrapper.
terraform {
  required_version = "~> 1.16.4"

  backend "s3" {
    key = "prod/cloudflare/terraform.tfstate"
  }
}
