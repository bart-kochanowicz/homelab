terraform {
  required_version = "~> 1.16.4"

  backend "s3" {
    key = "prod/unifi/terraform.tfstate"
  }
}
