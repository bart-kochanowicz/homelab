variable "controller" {
  description = "Local UniFi HTTPS origin and Network site name."
  type = object({
    url  = string
    site = optional(string, "default")
  })
  nullable = false

  validation {
    condition     = can(regex("^https://[a-zA-Z0-9][a-zA-Z0-9.-]*(:[0-9]+)?/?$", var.controller.url))
    error_message = "Use an HTTPS origin without credentials, API paths, queries or fragments."
  }

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9_-]*$", var.controller.site))
    error_message = "The site must be a non-empty lowercase UniFi site name."
  }
}

variable "unifi_auth" {
  description = "Dedicated local UniFi credentials or API key."
  type = object({
    username = optional(string)
    password = optional(string)
    api_key  = optional(string)
  })
  sensitive = true
  ephemeral = true
  nullable  = false

  validation {
    condition = (
      var.unifi_auth.api_key != null
      ? try(length(trimspace(var.unifi_auth.api_key)) > 0, false) && var.unifi_auth.username == null && var.unifi_auth.password == null
      : try(length(trimspace(var.unifi_auth.username)) > 0 && length(var.unifi_auth.password) > 0, false)
    )
    error_message = "Provide either a non-empty API key or a non-empty local username/password pair."
  }
}

variable "name_prefix" {
  description = "Prefix for generated UniFi object names."
  type        = string
  default     = "cavespace-"
  nullable    = false
}

variable "wifi_passphrases" {
  description = "Write-only Wi-Fi passphrases keyed by managed WLAN name."
  type        = map(string)
  sensitive   = true
  ephemeral   = true
  nullable    = false
}

variable "wifi_ppsks" {
  description = "Sensitive PPSK passwords keyed by WLAN/role; stored in Terraform plans and state."
  type        = map(string)
  sensitive   = true
  nullable    = false
}
