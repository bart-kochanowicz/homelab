variable "crafty_url" {
  description = "Private Crafty Controller URL with verified TLS."
  type        = string
  default     = "https://crafty-controller.thecavespace.net"
  nullable    = false

  validation {
    condition     = startswith(var.crafty_url, "https://")
    error_message = "Use an HTTPS Crafty endpoint."
  }
}

variable "crafty_token" {
  description = "Dedicated Crafty API token supplied by the private automation."
  type        = string
  sensitive   = true
  nullable    = false

  validation {
    condition     = length(trimspace(var.crafty_token)) > 0
    error_message = "The Crafty API token must not be empty."
  }
}

variable "atm10_archive_path" {
  description = "Private ATM10 4.14 server archive, including the world, available to the Terraform process."
  type        = string
  default     = "/srv/terraform/artifacts/atm10-4.14-d8985a62529c.zip"
  nullable    = false
}

variable "atm10_8_3_archive_path" {
  description = "Private ATM10 8.3 server archive, including the copied world, available to the Terraform process."
  type        = string
  default     = "/srv/terraform/artifacts/atm10-8.3-9c6b994c3344.zip"
  nullable    = false
}
