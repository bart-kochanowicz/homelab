terraform {
  required_version = "~> 1.16.4"

  backend "s3" {
    key = "checks/garage-backend/terraform.tfstate"
  }
}

# Built-in state only: no infrastructure or external providers are created.
resource "terraform_data" "backend_check" {
  input = "Garage backend read/write verified"
}

output "backend_check" {
  description = "Marker stored in the isolated Garage backend check state."
  value       = terraform_data.backend_check.output
}
