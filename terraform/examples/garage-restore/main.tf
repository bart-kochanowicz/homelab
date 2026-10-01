terraform {
  required_version = "~> 1.16.4"

  # The restore script supplies shared settings and a fresh check-only state key.
  backend "s3" {}
}

resource "terraform_data" "backend_check" {
  input = "Garage backend read/write verified"
}

output "backend_check" {
  description = "Marker recovered from the isolated R2 backup snapshot."
  value       = terraform_data.backend_check.output
}
